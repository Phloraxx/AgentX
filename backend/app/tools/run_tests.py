"""Tool: run test cases against student code in the sandbox."""

import logging
from langchain_core.tools import tool

logger = logging.getLogger(__name__)


@tool
def run_tests_tool(code: str, test_cases: list[dict], language: str) -> dict:
    """Run test cases against student code in the sandbox.

    Args:
        code: The student's code to test.
        test_cases: List of test case dicts with 'input', 'expected', 'description'.
        language: Programming language (python, javascript).

    Returns:
        Dict with ok, results list, pass_count, fail_count.
    """
    from app.sandbox.manager import get_sandbox

    sandbox = get_sandbox()
    results = []

    for i, tc in enumerate(test_cases):
        test_input = tc.get("input", "")
        expected = tc.get("expected", "")
        description = tc.get("description", f"Test {i + 1}")

        # Wrap code with test runner that compares output
        if language == "python":
            runner = f"""\
{code}

# --- Test runner (auto-generated) ---
if __name__ == "__main__":
    import sys, io, json
    _stdout = sys.stdout
    sys.stdout = io.StringIO()
    try:
        _result = eval("{_escape_for_exec(test_input)}")
    except Exception as e:
        sys.stdout = _stdout
        print(f"ERROR: {{e}}")
        sys.exit(1)
    output = sys.stdout.getvalue().strip()
    sys.stdout = _stdout
    if output:
        print(output)
    else:
        # If no stdout, print the return value
        print(json.dumps(_result) if _result is not None else "")
"""
        else:
            runner = f"""\
{code}

// --- Test runner (auto-generated) ---
try {{
    const _result = eval("{_escape_for_exec(test_input)}");
    if (_result !== undefined) console.log(JSON.stringify(_result));
}} catch(e) {{
    console.error("ERROR: " + e.message);
    process.exit(1);
}}
"""

        result = sandbox.run(runner, language)
        actual_output = result.get("stdout", "").strip()

        # Normalize whitespace for comparison
        passed = actual_output.strip() == expected.strip()
        results.append({
            "test_index": i,
            "description": description,
            "input": test_input,
            "expected": expected,
            "actual": actual_output,
            "passed": passed,
            "error": result.get("stderr", "") if not passed else "",
        })

    pass_count = sum(1 for r in results if r["passed"])
    fail_count = len(results) - pass_count

    return {
        "ok": fail_count == 0,
        "results": results,
        "pass_count": pass_count,
        "fail_count": fail_count,
        "total": len(results),
    }


def _escape_for_exec(code: str) -> str:
    """Escape a string for embedding in an exec() call."""
    return code.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
