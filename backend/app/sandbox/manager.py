"""Docker sandbox manager — runs student code in ephemeral, isolated containers."""

import time
import logging
import threading
from app.config import settings

logger = logging.getLogger(__name__)

# Cap concurrent sandbox executions to prevent resource exhaustion
_sandbox_semaphore = threading.Semaphore(4)


class DockerSDKClient:
    """Manages ephemeral Docker containers for code execution."""

    def __init__(self):
        self._client = None
        self._docker_available: bool | None = None  # cached

    def _get_client(self):
        if self._client is None:
            import docker
            self._client = docker.from_env()
        return self._client

    def _is_available(self) -> bool:
        if self._docker_available is not None:
            return self._docker_available
        try:
            self._get_client().ping()
            self._docker_available = True
            return True
        except Exception:
            self._docker_available = False
            return False

    def run(self, code: str, language: str = "python") -> dict:
        """Execute code in Docker sandbox, or fallback to subprocess."""
        with _sandbox_semaphore:
            if self._is_available():
                return self._run_docker(code, language)
            return self._run_fallback(code, language)

    def _run_docker(self, code: str, language: str) -> dict:
        """Execute code in an ephemeral Docker container."""
        image_map = {
            "python": settings.sandbox_python_image,
            "javascript": settings.sandbox_node_image,
        }
        cmd_map = {
            "python": ["python", "-c", code],
            "javascript": ["node", "-e", code],
        }
        img = image_map.get(language)
        cmd = cmd_map.get(language)
        if not img:
            return {"stdout": "", "stderr": f"Unsupported language: {language}",
                    "exit_code": -1, "duration_ms": 0, "sandbox": "error"}

        client = self._get_client()
        t0 = time.time()
        container = None
        try:
            container = client.containers.run(
                img,
                command=cmd,
                detach=True,
                network_disabled=True,
                mem_limit=f"{settings.sandbox_mem_limit_mb}m",
                cpu_quota=int(settings.sandbox_cpu_quota * 100_000),
                pids_limit=64,
                read_only=True,
                tmpfs={"/tmp": "rw,size=16m"},
                user="nobody",
            )
            result = container.wait(timeout=settings.docker_timeout_s)
            exit_code = result.get("StatusCode", -1)
            stdout = container.logs(stdout=True, stderr=False).decode(errors="replace")
            stderr = container.logs(stdout=False, stderr=True).decode(errors="replace")
            duration_ms = int((time.time() - t0) * 1000)
            return {"stdout": stdout, "stderr": stderr, "exit_code": exit_code,
                    "duration_ms": duration_ms, "sandbox": "docker"}
        except Exception as e:
            # Reset cached availability so the next call re-pings Docker
            self._docker_available = None
            duration_ms = int((time.time() - t0) * 1000)
            return {"stdout": "", "stderr": str(e), "exit_code": -1,
                    "duration_ms": duration_ms, "sandbox": "docker_error"}
        finally:
            if container:
                try:
                    container.remove(force=True)
                except Exception:
                    pass

    def _run_fallback(self, code: str, language: str) -> dict:
        """Fallback: run code via subprocess with resource limits."""
        import subprocess
        import tempfile
        import os
        import platform

        suffix = ".py" if language == "python" else ".js"
        interp = "python" if language == "python" else "node"

        t0 = time.time()
        with tempfile.NamedTemporaryFile("w", suffix=suffix, delete=False) as f:
            f.write(code)
            path = f.name

        def _set_limits():
            """Pre-exec hook to set resource limits (Linux only)."""
            if platform.system() == "Linux":
                try:
                    import resource
                    mem_bytes = settings.sandbox_mem_limit_mb * 1024 * 1024
                    resource.setrlimit(resource.RLIMIT_AS, (mem_bytes, mem_bytes))
                    resource.setrlimit(resource.RLIMIT_CPU, (settings.docker_timeout_s, settings.docker_timeout_s))
                    resource.setrlimit(resource.RLIMIT_NPROC, (64, 64))
                    resource.setrlimit(resource.RLIMIT_FSIZE, (10 * 1024 * 1024, 10 * 1024 * 1024))
                    resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
                except (ImportError, ValueError):
                    pass  # Windows or restricted env

        preexec = _set_limits if platform.system() == "Linux" else None

        try:
            proc = subprocess.run(
                [interp, path],
                capture_output=True,
                timeout=settings.docker_timeout_s,
                preexec_fn=preexec,
            )
            duration_ms = int((time.time() - t0) * 1000)
            return {
                "stdout": proc.stdout.decode(errors="replace"),
                "stderr": proc.stderr.decode(errors="replace"),
                "exit_code": proc.returncode,
                "duration_ms": duration_ms,
                "sandbox": "fallback",
            }
        except subprocess.TimeoutExpired as e:
            duration_ms = int((time.time() - t0) * 1000)
            return {
                "stdout": (e.stdout or b"").decode(errors="replace"),
                "stderr": "Execution timed out",
                "exit_code": 124,
                "duration_ms": duration_ms,
                "sandbox": "fallback",
            }
        except Exception as e:
            duration_ms = int((time.time() - t0) * 1000)
            return {"stdout": "", "stderr": str(e), "exit_code": -1,
                    "duration_ms": duration_ms, "sandbox": "fallback_error"}
        finally:
            try:
                os.unlink(path)
            except Exception:
                pass


# Singleton
_sandbox: DockerSDKClient | None = None


def get_sandbox() -> DockerSDKClient:
    global _sandbox
    if _sandbox is None:
        _sandbox = DockerSDKClient()
    return _sandbox
