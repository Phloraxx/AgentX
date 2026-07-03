"""Tool: run test cases against student code in the sandbox.

Test cases use a ``function_call`` schema: each case provides a valid language
expression that calls the student's function, plus the expected return value
as JSON. The harness execs the student code to define the function, then evals
each ``function_call`` and compares the result to ``expected``.
"""

import json
import logging
from langchain_core.tools import tool

logger = logging.getLogger(__name__)


@tool
def run_tests_tool(code: str, test_cases: list[dict], language: str) -> dict:
    """Run test cases against student code in the sandbox.

    Args:
        code: The student's code to test.
        test_cases: List of dicts with ``function_call``, ``expected``, and
            optional ``description``. The ``function_call`` is a valid
            language expression that calls the defined function (e.g.
            ``two_sum([2,7,11,15], 9)``). ``expected`` is the correct return
            value as a JSON literal (e.g. ``[0,1]``, ``3``, ``true``).
        language: Programming language (python, javascript).

    Returns:
        Dict with ok, results list, pass_count, fail_count, total.
    """
    from app.sandbox.manager import get_sandbox

    sandbox = get_sandbox()
    results = []

    for i, tc in enumerate(test_cases):
        function_call = tc.get("function_call", "")
        expected_raw = tc.get("expected", "")
        description = tc.get("description", f"Test {i + 1}")

        if not function_call:
            results.append({
                "test_index": i, "description": description,
                "function_call": "", "expected": expected_raw,
                "actual": "", "passed": False, "error": "missing function_call",
            })
            continue

        # Build a runner that execs the code then evaluates the function call
        if language == "python":
            runner = _build_python_runner(code, function_call)
        else:
            runner = _build_js_runner(code, function_call)

        result = sandbox.run(runner, language)
        stdout = result.get("stdout", "").strip()
        stderr = result.get("stderr", "").strip()
        exit_code = result.get("exit_code", -1)

        # The runner prints json.dumps(result) of the function call
        actual = stdout
        passed = _compare(actual, expected_raw)

        error_msg = ""
        if not passed and (stderr or exit_code != 0):
            error_msg = stderr[:300] if stderr else f"exit code {exit_code}"

        results.append({
            "test_index": i,
            "description": description,
            "function_call": function_call,
            "expected": expected_raw,
            "actual": actual,
            "passed": passed,
            "error": error_msg,
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


# ── Runner builders ──────────────────────────────────────────────────────────


def _build_python_runner(code: str, function_call: str) -> str:
    """Wrap student code + a function_call eval into a runnable script.

    stdout is redirected during eval so print statements inside the student's
    function don't pollute the result line we compare against ``expected``.
    """
    safe_call = function_call.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return f"""\
{code}

# --- Test runner (auto-generated) ---
if __name__ == "__main__":
    import json, sys, io
    _real_stdout = sys.stdout
    try:
        sys.stdout = io.StringIO()
        _result = eval("{safe_call}")
        _captured = sys.stdout.getvalue()
    finally:
        sys.stdout = _real_stdout
    # Print ONLY the return value — not any debug prints from the function
    print(json.dumps(_result, default=str))
"""

def _build_js_runner(code: str, function_call: str) -> str:
    """Wrap student code + a function_call eval into a runnable script.

    console.log is swapped out during eval so debug prints inside the
    student's function don't pollute the result line.
    """
    safe_call = function_call.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return f"""\
{code}

// --- Test runner (auto-generated) ---
const _realLog = console.log;
console.log = () => {{}};
let _result;
try {{
    _result = eval("{safe_call}");
}} finally {{
    console.log = _realLog;
}}
console.log(JSON.stringify(_result));
"""


# ── Comparison ───────────────────────────────────────────────────────────────


def _compare(actual: str, expected: str) -> bool:
    """Compare actual output to expected value.

    Both sides are parsed as JSON when possible, then compared with
    type-coerced equality (so ``true``/``True``, ``3``/``3.0`` match).
    Falls back to string comparison if JSON parse fails.
    """
    if not actual:
        return False

    actual_stripped = actual.strip()
    expected_stripped = expected.strip()

    # Try parsing both as JSON — this handles lists, numbers, booleans, and
    # quoted strings (e.g. '"BANC"' → 'BANC') consistently on both sides.
    try:
        a = json.loads(actual_stripped)
    except (json.JSONDecodeError, TypeError):
        a = actual_stripped

    try:
        e = json.loads(expected_stripped)
    except (json.JSONDecodeError, TypeError):
        e = expected_stripped

    # Direct equality
    if a == e:
        return True

    # Type-coerced equality for bool/int/float/string mismatches
    if isinstance(a, bool) or isinstance(e, bool):
        return str(a).lower() == str(e).lower()
    if isinstance(a, (int, float)) and isinstance(e, (int, float)):
        return float(a) == float(e)
    if isinstance(a, str) and isinstance(e, str):
        return a.strip() == e.strip()

    # Last resort: string representation
    return str(a).strip() == str(e).strip()
