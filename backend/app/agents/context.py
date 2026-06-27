"""Per-agent context projection — each agent receives only the state it needs."""

from typing import Any


def project_host_context(state: dict) -> dict[str, Any]:
    """Project state to what the Host agent needs.

    The Host manages the session, presents challenges, and orchestrates
    the overall flow. It needs session metadata and chat history.
    """
    current_round = state.get("current_round", {})
    return {
        "session_id": state.get("session_id"),
        "language": state.get("language"),
        "topic": state.get("topic"),
        "difficulty": state.get("difficulty"),
        "round_num": state.get("round_num"),
        "chat_history": state.get("chat", []),
    }


def project_saboteur_context(state: dict) -> dict[str, Any]:
    """Project state to what the Saboteur agent needs.

    The Saboteur analyzes student code and injects bugs. It needs
    the student's original code, language, difficulty, and round info.
    """
    current_round = state.get("current_round", {})
    return {
        "original_code": current_round.get("original_code", ""),
        "language": state.get("language"),
        "difficulty": state.get("difficulty"),
        "round_num": state.get("round_num"),
    }


def project_evaluator_context(state: dict) -> dict[str, Any]:
    """Project state to what the Evaluator agent needs.

    The Evaluator diffs all three code versions (original, buggy, fix),
    scores the round, and produces feedback. It needs the full round data
    including execution results and test cases.
    """
    current_round = state.get("current_round", {})
    return {
        "original_code": current_round.get("original_code", ""),
        "buggy_code": current_round.get("buggy_code", ""),
        "fix_code": current_round.get("fix_code", ""),
        "bug_manifest": current_round.get("bug_manifest", []),
        "fix_exec": current_round.get("fix_exec"),
        "test_cases": current_round.get("test_cases", []),
        "language": state.get("language"),
        "round_num": state.get("round_num"),
    }
