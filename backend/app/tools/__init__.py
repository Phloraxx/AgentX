"""Tool registry — maps tool name to callable. Used for bind_tools and tests."""

from collections.abc import Callable
from app.tools.fetch_challenge import fetch_challenge
from app.tools.inject_bugs import inject_bugs_tool
from app.tools.execute_code import execute_code_tool
from app.tools.score_round import score_round_tool
from app.tools.run_tests import run_tests_tool

# Registry of all available tools
TOOL_REGISTRY: dict[str, Callable] = {
    "fetch_challenge": fetch_challenge,
    "inject_bugs": inject_bugs_tool,
    "execute_code": execute_code_tool,
    "score_round": score_round_tool,
    "run_tests": run_tests_tool,
}


def get_tool(name: str):
    """Get a tool by name."""
    return TOOL_REGISTRY.get(name)


def get_all_tools():
    """Return all registered tools as a list."""
    return list(TOOL_REGISTRY.values())
