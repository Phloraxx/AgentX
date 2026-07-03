"""Shared utility functions used across the codebase."""

import json
import logging
import re

logger = logging.getLogger(__name__)


def parse_json_response(content: str) -> dict | None:
    """Parse JSON from LLM response, handling markdown code blocks.

    Tries:
    1. Direct JSON parse
    2. Strip ```json ... ``` fences then parse
    3. Find outermost { } via brace-counting and parse that slice
    """
    if not content:
        return None

    # 1. Direct parse
    try:
        return json.loads(content)
    except (json.JSONDecodeError, TypeError):
        pass

    # 2. Strip markdown fences
    stripped = re.sub(r"^```(?:json)?\s*", "", content.strip(), flags=re.IGNORECASE)
    stripped = re.sub(r"\s*```$", "", stripped.strip())
    try:
        return json.loads(stripped)
    except (json.JSONDecodeError, TypeError):
        pass

    # 3. Find outermost { } by brace-counting (handles any nesting depth)
    start = content.find("{")
    if start == -1:
        return None
    depth = 0
    for i, ch in enumerate(content[start:], start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(content[start : i + 1])
                except json.JSONDecodeError:
                    return None
    return None

def extract_json_array(content: str, key: str) -> list | None:
    """Extract a JSON array value for `key` from `content` using bracket-counting.
    Handles truncated JSON where the outer object is incomplete.
    """
    import re as _re
    pattern = f'"{key}"\\s*:\\s*\\['
    m = _re.search(pattern, content)
    if not m:
        return None
    start = m.end() - 1  # position of '['
    depth = 0
    for i, ch in enumerate(content[start:], start):
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(content[start : i + 1])
                except json.JSONDecodeError:
                    return None
    return None


def difficulty_to_num_bugs(difficulty: str) -> int:
    """Map difficulty to number of bugs to inject."""
    from app.config import settings
    return settings.max_bugs_per_difficulty.get(difficulty, 2)


def apply_bugs(code: str, bugs: list[dict]) -> tuple[str, int]:
    """Apply bugs to code by line replacement.

    Each bug dict must have: line (int), original (str), sabotaged (str).
    Returns (code, applied_count).
    """
    lines = code.split("\n")
    applied = 0

    for bug in bugs:
        line_num = bug.get("line", 0)
        original = bug.get("original", "").strip()
        sabotaged = bug.get("sabotaged", "").strip()

        # Skip bugs with empty original — would match everything
        if not original:
            continue

        if 0 < line_num <= len(lines):
            # Strategy 1: exact match at the specified line
            if original in lines[line_num - 1]:
                lines[line_num - 1] = lines[line_num - 1].replace(original, sabotaged)
                applied += 1
                continue
            # Strategy 2: search all lines for the original string
            found = False
            for i, line in enumerate(lines):
                if original in line:
                    lines[i] = line.replace(original, sabotaged)
                    applied += 1
                    found = True
                    break
            if found:
                continue
            # Strategy 3: LLM hallucinated the original — replace the whole
            # line at the specified line number with the sabotaged version
            if sabotaged:
                lines[line_num - 1] = sabotaged
                applied += 1
                continue
        elif original:
            # No valid line number — search by content
            for i, line in enumerate(lines):
                if original in line:
                    lines[i] = line.replace(original, sabotaged)
                    applied += 1
                    break

    if bugs and applied == 0:
        logger.warning("Bug injection no-op: LLM original strings not found in code")
    elif applied < len(bugs):
        logger.warning(f"Only {applied}/{len(bugs)} bugs applied (some line numbers out of range or originals not found)")

    return "\n".join(lines), applied


def validate_compiles(code: str, language: str) -> bool:
    """Check if code at least parses/compiles (no syntax errors)."""
    try:
        if language == "python":
            import ast
            ast.parse(code)
            return True
        elif language == "javascript":
            import subprocess
            result = subprocess.run(
                ["node", "-e", "try { new Function(process.argv[1]) } catch(e) { process.exit(1) }",
                 code],
                capture_output=True,
                timeout=5,
            )
            return result.returncode == 0
        return True
    except Exception:
        return False


async def preflight_check() -> dict:
    """Non-blocking pre-flight: probe each external service and log status.

    Returns a dict of service -> "ok" | "warn" | "<error message>".
    Never raises — failures degrade to warnings so the app still boots.
    Shared by ``main.lifespan`` and ``demo_check.py``.
    """
    import asyncio

    results: dict[str, str] = {}

    async def _probe(name: str, fn):
        try:
            ok = await asyncio.to_thread(fn)
            status = "ok" if ok else "warn"
        except Exception as e:
            status = f"error: {e}"
        results[name] = status
        logger.info(f"[preflight] {name}: {status}")

    async def _probe_silent(name: str, fn):
        try:
            await asyncio.to_thread(fn)
            results[name] = "ok"
            logger.info(f"[preflight] {name}: ok")
        except Exception as e:
            results[name] = f"error: {e}"
            logger.warning(f"[preflight] {name}: {e}")

    # OpenCode Go models (guarded against placeholder keys)
    def _check_llm():
        from app.config import settings
        from app.agents.base import get_host_llm
        from langchain_core.messages import HumanMessage
        key = settings.opencode_api_key.get_secret_value()
        if not key or "placeholder" in key or key.startswith("your-"):
            raise RuntimeError("OpenCode Go API key not set (placeholder value)")
        get_host_llm().invoke([HumanMessage(content="Say OK")])
        return True

    # Exa (key presence only — avoids billable search at boot)
    def _check_exa():
        from app.config import settings
        key = settings.exa_api_key.get_secret_value()
        if not key or key.startswith("dummy") or key.startswith("exa-placeholder"):
            raise RuntimeError("Exa API key not set")
        return True

    # Docker sandbox
    def _check_docker():
        from app.sandbox.manager import get_sandbox
        r = get_sandbox().run("print('hello')", "python")
        return r["exit_code"] == 0 and "hello" in r.get("stdout", "")

    # LangGraph compiles
    def _check_graph():
        from app.graph.builder import build_graph
        build_graph()
        return True

    # Run probes concurrently (each is to_thread, so non-blocking for the loop)
    await asyncio.gather(
        _probe_silent("opencode-go", _check_llm),
        _probe_silent("exa-key", _check_exa),
        _probe_silent("docker-sandbox", _check_docker),
        _probe_silent("langgraph", _check_graph),
    )
    return results
