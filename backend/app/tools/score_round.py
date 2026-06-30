"""Tool: evaluate and score a student's fix."""

import logging
from langchain_core.tools import tool

logger = logging.getLogger(__name__)


@tool
def score_round_tool(
    original_code: str,
    buggy_code: str,
    fix_code: str,
    bug_manifest: list[dict],
    fix_exec: dict,
    language: str,
) -> dict:
    """Compare original, buggy, and fixed code to score the student's fix.

    Args:
        original_code: The student's original code.
        buggy_code: The code after sabotage.
        fix_code: The student's fix attempt.
        bug_manifest: List of injected bugs.
        fix_exec: Execution result of the fix.
        language: Programming language.

    Returns:
        Dict with ok, score breakdown, and feedback.
    """
    from app.agents.base import make_llm
    from app.prompts.evaluator import EVALUATOR_SYSTEM_PROMPT
    from langchain_core.messages import SystemMessage, HumanMessage
    from app.utils import parse_json_response

    llm = make_llm("evaluator", temperature=0.2)

    bugs_summary = "\n".join([
        f"- Line {b.get('line')}: {b.get('type')} — {b.get('description')}"
        for b in bug_manifest
    ]) or "No bugs were injected."

    prompt = f"""Evaluate the student's fix for this debugging challenge.

## Original Code ({language}):
```{language}
{original_code}
```

## Buggy Code (after sabotage):
```{language}
{buggy_code}
```

## Student's Fix:
```{language}
{fix_code}
```

## Injected Bugs:
{bugs_summary}

## Execution Results:
- Fix exit code: {fix_exec.get('exit_code', 'N/A')}
- Fix output: {fix_exec.get('stdout', '')[:200]}

Score the student's fix on:
1. Bugs Fixed (0-40): How many of the injected bugs were correctly identified and fixed?
2. Code Quality (0-30): Is the code clean, readable, well-structured?
3. Correctness (0-20): Does the fix actually work? Any new bugs introduced?
4. Speed Bonus (0-10): How efficient was the fix?

Respond with ONLY valid JSON (no markdown, no explanation)."""

    messages = [
        SystemMessage(content=EVALUATOR_SYSTEM_PROMPT),
        HumanMessage(content=prompt),
    ]

    try:
        response = llm.invoke(messages)
        parsed = parse_json_response(response.content)

        if not parsed:
            return {"ok": False, "error": "Failed to parse evaluation"}

        return {
            "ok": True,
            "score": {
                "bugs_fixed": parsed.get("bugs_fixed", 0),
                "bugs_total": parsed.get("bugs_total", len(bug_manifest)),
                "code_quality": parsed.get("code_quality", 0.0),
                "speed_bonus": parsed.get("speed_bonus", 0.0),
                "total": parsed.get("total", 0),
            },
            "feedback": parsed.get("feedback", ""),
            "remaining_bugs": parsed.get("remaining_bugs", []),
            "new_issues": parsed.get("new_issues", []),
        }

    except Exception as e:
        logger.error(f"score_round_tool error: {e}")
        return {"ok": False, "error": str(e)}
