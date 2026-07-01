"""Pre-flight check: verify all external services are reachable.

Shares the probe logic with ``app.utils.preflight_check`` (used at server
startup). Run standalone with: ``python demo_check.py`` from ``backend/``.
"""

import asyncio

from app.utils import preflight_check


def _print_results(results: dict) -> None:
    icons = {
        "ok": "✅",
        "warn": "⚠️",
    }
    for name, status in results.items():
        icon = icons.get(status.split(":")[0], "❌")
        suffix = "" if status == "ok" else f" — {status}"
        print(f"  {icon} {name}{suffix}")


def main() -> None:
    print("=== AgentX Pre-Flight Check ===\n")
    results = asyncio.run(preflight_check())
    _print_results(results)

    # FastAPI load is cheap and sync — check separately.
    try:
        from main import app  # noqa: F401
        print("  ✅ fastapi: app loads")
        results["fastapi"] = "ok"
    except Exception as e:
        print(f"  ❌ fastapi: {e}")
        results["fastapi"] = f"error: {e}"

    print()
    failed = [k for k, v in results.items() if not v.startswith("ok") and v != "warn"]
    if failed:
        print(f"=== {len(failed)} service(s) need attention ===")
        raise SystemExit(1)
    print("=== All services reachable ===")


if __name__ == "__main__":
    main()
