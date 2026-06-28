"""Conditional edges for the LangGraph state machine."""

from app.graph.state import SessionState


def round_or_done(state: SessionState) -> str:
    """After evaluation: continue to next round or finish session.

    round_num is 0-indexed and not yet incremented when this runs.
    If completing this round means we've done max_rounds total, finish.
    """
    current_round_num = state.get("round_num", 0)
    max_rounds = state.get("max_rounds", 3)
    if current_round_num + 1 >= max_rounds:
        return "done"
    return "adjust"
