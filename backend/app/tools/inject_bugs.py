"""Tool: inject bugs into student code via Saboteur LLM analysis."""

import logging
from langchain_core.tools import tool
from app.utils import parse_json_response, extract_json_array, difficulty_to_num_bugs, apply_bugs, validate_compiles
logger = logging.getLogger(__name__)


@tool
def inject_bugs_tool(original_code: str, difficulty: str, language: str) -> dict:
    """Analyze student code and inject realistic bugs.

    Args:
        original_code: The student's original code.
        difficulty: Difficulty level (easy, medium, hard).
        language: Programming language (python, javascript).

    Returns:
        Dict with ok, buggy_code, bug_manifest, test_cases, original_exec, buggy_exec.
    """
    from app.agents.base import make_llm
    from app.prompts.saboteur import SABOTEUR_SYSTEM_PROMPT
    from langchain_core.messages import SystemMessage, HumanMessage
    from app.sandbox.manager import get_sandbox

    llm = make_llm("saboteur", temperature=0.7)
    num_bugs = difficulty_to_num_bugs(difficulty)

    messages = [
        SystemMessage(content=SABOTEUR_SYSTEM_PROMPT),
        HumanMessage(content=f"""\
Analyze this {language} code and inject {difficulty}-level bugs.

```{language}
{original_code}
```

Inject {num_bugs} realistic bugs. Each bug must be a different type.
The code MUST still compile. Provide test cases that expose each bug.

Respond with ONLY valid JSON (no markdown, no explanation)."""),
    ]

    try:
        response = llm.invoke(messages)
        logger.debug(f"inject_bugs raw response: {response.content[:500]!r}")
        raw = response.content
        parsed = parse_json_response(raw)

        # Truncation fallback: if full parse failed but "bugs" array is present,
        # recover it with bracket-counting and drop test_cases.
        if not parsed or "bugs" not in parsed:
            recovered_bugs = extract_json_array(raw, "bugs")
            if recovered_bugs:
                parsed = {"bugs": recovered_bugs, "test_cases": []}
                logger.warning("inject_bugs: recovered bugs from truncated response, test_cases dropped")

        if not parsed or "bugs" not in parsed:
            logger.error(f"inject_bugs parse failed. Raw: {raw[:300]!r}")
            return {"ok": False, "error": "Failed to parse bug injection response"}

        bugs = parsed["bugs"]
        test_cases = parsed.get("test_cases", [])
        buggy_code, applied = apply_bugs(original_code, bugs)

        if applied < len(bugs):
            return {"ok": False, "error": f"Only {applied}/{len(bugs)} bugs could be applied (line numbers out of range)"}

        if not validate_compiles(buggy_code, language):
            return {"ok": False, "error": "Buggy code does not compile"}

        sandbox = get_sandbox()
        original_exec = sandbox.run(original_code, language)
        buggy_exec = sandbox.run(buggy_code, language)

        return {
            "ok": True,
            "buggy_code": buggy_code,
            "bug_manifest": bugs,
            "test_cases": test_cases,
            "original_exec": original_exec,
            "buggy_exec": buggy_exec,
        }

    except Exception as e:
        logger.error(f"inject_bugs_tool error: {e}")
        return {"ok": False, "error": str(e)}
