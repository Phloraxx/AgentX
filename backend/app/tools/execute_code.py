"""Tool: execute code in the Docker sandbox."""

import logging
from langchain_core.tools import tool

logger = logging.getLogger(__name__)


@tool
def execute_code_tool(code: str, language: str) -> dict:
    """Execute code in an isolated sandbox and return results.

    Args:
        code: The code to execute.
        language: Programming language (python, javascript).

    Returns:
        Dict with ok, stdout, stderr, exit_code, duration_ms, sandbox.
    """
    from app.sandbox.manager import get_sandbox
    sandbox = get_sandbox()
    result = sandbox.run(code, language)
    return {"ok": result["exit_code"] == 0, **result}
