"\"\"Test that the LangGraph compiles and nodes execute correctly.\"\""

import pytest
from unittest.mock import patch, MagicMock
from app.graph.builder import build_graph
from app.graph.edges import round_or_done
from app.graph.nodes import adjust


def test_graph_compiles():
    """The graph must compile without errors."""
    graph = build_graph()
    assert graph is not None


def test_stub_round_completes():
    """A full round with mocked LLMs should complete through to 'done' phase.

    Flow (with student_writing):
        host_setup → host_present → [interrupt: saboteur_inject]
        → saboteur_inject → [interrupt: student_fix_await]
        → host_run_fix → evaluator_score → adjust → done
    """
    graph = build_graph()
    config = {"configurable": {"thread_id": "test-thread-002"}}

    # Mock the LLM responses for each agent
    mock_host_response = MagicMock()
    mock_host_response.tool_calls = []
    mock_host_response.content = "Here is your challenge: Two Sum"

    mock_saboteur_response = MagicMock()
    mock_saboteur_response.content = (
        '{"bugs": [], "test_cases": [], "analysis": "No bugs found"}'
    )

    mock_evaluator_response = MagicMock()
    mock_evaluator_response.content = (
        '{"bugs_fixed": 0, "bugs_total": 0, "code_quality": 0.8, '
        '"speed_bonus": 0.5, "total": 50, "feedback": "Good attempt!"}'
    )

    def mock_make_llm(model_key, **kwargs):
        mock_llm = MagicMock()
        if model_key == "host":
            mock_llm.invoke.return_value = mock_host_response
            mock_llm.bind_tools.return_value = mock_llm
        elif model_key == "saboteur":
            mock_llm.invoke.return_value = mock_saboteur_response
        elif model_key == "evaluator":
            mock_llm.invoke.return_value = mock_evaluator_response
        return mock_llm

    # Mock sandbox execution
    mock_sandbox = MagicMock()
    mock_sandbox.run.return_value = {
        "stdout": "4\n",
        "stderr": "",
        "exit_code": 0,
        "duration_ms": 10,
        "sandbox": "mock",
    }

    initial_state = {
        "session_id": "test-001",
        "language": "python",
        "topic": "arrays",
        "difficulty": "easy",
        "round_num": 0,
        "max_rounds": 1,
        "phase": "setup",
        "current_round": {
            "round_num": 0,
            "challenge": "",
            "original_code": "",
            "buggy_code": "",
            "fix_code": "",
            "bug_manifest": [],
            "test_cases": [],
            "original_exec": None,
            "buggy_exec": None,
            "fix_exec": None,
            "score": None,
            "difficulty_in": "easy",
            "difficulty_out": "easy",
        },
        "rounds": [],
        "chat": [],
        "trace": [],
        "error": None,
    }

    with patch("app.agents.base.make_llm", side_effect=mock_make_llm), \
         patch("app.sandbox.manager.get_sandbox", return_value=mock_sandbox):

        # First invocation: runs until the first interrupt point.
        # With two interrupts (saboteur_inject, student_fix_await),
        # graph pauses BEFORE saboteur_inject after host_present completes.
        result = graph.invoke(initial_state, config)

        # After host_present: challenge should be populated
        assert result["current_round"]["challenge"] != ""

        # Phase depends on where the first interrupt fires:
        # - With student_writing flow: "student_writing" (interrupt before saboteur_inject)
        # - Without: "student_fixing" (interrupt before student_fix_await)
        first_phase = result["phase"]
        assert first_phase in ("student_writing", "student_fixing"), (
            f"Expected student_writing or student_fixing after first invoke, got {first_phase}"
        )

        # If paused at student_writing, resume with original code
        if first_phase == "student_writing":
            graph.update_state(config, {
                "current_round": {
                    **result["current_round"],
                    "original_code": (
                        "def two_sum(nums, target):\n"
                        "    for i in range(len(nums)):\n"
                        "        for j in range(i+1, len(nums)):\n"
                        "            if nums[i] + nums[j] == target:\n"
                        "                return [i, j]\n"
                        "    return []"
                    ),
                    "original_code_submitted": True,
                }
            })
            result = graph.invoke(None, config)
            # Now should be paused before student_fix_await
            assert result["phase"] == "student_fixing", (
                f"Expected student_fixing after second invoke, got {result['phase']}"
            )

        # Resume: update state with fix_code
        graph.update_state(config, {
            "current_round": {
                **result["current_round"],
                "fix_code": (
                    "def two_sum(nums, target):\n"
                    "    seen = {}\n"
                    "    for i, num in enumerate(nums):\n"
                    "        complement = target - num\n"
                    "        if complement in seen:\n"
                    "            return [seen[complement], i]\n"
                    "        seen[num] = i\n"
                    "    return []"
                ),
            }
        })
        result_final = graph.invoke(None, config)

        # After full round: should be done (max_rounds=1, so round 0 completion = done)
        assert result_final["phase"] == "done", (
            f"Expected 'done' phase, got {result_final['phase']}"
        )


# ---------------------------------------------------------------------------
# Unit tests for edges and nodes (no graph invocation needed)
# ---------------------------------------------------------------------------


def test_adjust_increments_round():
    """adjust() should increment round_num by 1."""
    state = {
        "round_num": 0,
        "current_round": {"score": {"total": 60}},
        "difficulty": "easy",
    }
    result = adjust(state)
    assert result["round_num"] == 1


def test_adjust_increments_from_nonzero():
    """adjust() increments from any starting round."""
    state = {
        "round_num": 2,
        "current_round": {"score": {"total": 50}},
        "difficulty": "medium",
    }
    result = adjust(state)
    assert result["round_num"] == 3


def test_round_or_done_at_limit():
    """round_or_done returns 'done' when completing this round hits max_rounds."""
    state = {"round_num": 2, "max_rounds": 3}
    # After round 2 completes (round_num=2), 2+1=3 >= 3 → done
    assert round_or_done(state) == "done"


def test_round_or_done_at_exact_limit():
    """round_or_done returns 'done' when current round equals max."""
    state = {"round_num": 3, "max_rounds": 3}
    # 3+1=4 >= 3 → done
    assert round_or_done(state) == "done"


def test_round_or_done_below_limit():
    """round_or_done returns 'adjust' when more rounds remain."""
    state = {"round_num": 0, "max_rounds": 3}
    assert round_or_done(state) == "adjust"


def test_round_or_done_one_before_limit():
    """round_or_done returns 'adjust' when one round remains."""
    state = {"round_num": 1, "max_rounds": 3}
    assert round_or_done(state) == "adjust"


def test_difficulty_adjustment_easy_to_medium():
    """High score (>=80) on easy should bump to medium."""
    state = {"round_num": 0, "difficulty": "easy", "current_round": {"score": {"total": 85}}}
    result = adjust(state)
    assert result["difficulty"] == "medium"


def test_difficulty_adjustment_medium_to_hard():
    """High score (>=80) on medium should bump to hard."""
    state = {"round_num": 0, "difficulty": "medium", "current_round": {"score": {"total": 90}}}
    result = adjust(state)
    assert result["difficulty"] == "hard"


def test_difficulty_adjustment_medium_to_easy():
    """Low score (<40) on medium should drop to easy."""
    state = {"round_num": 0, "difficulty": "medium", "current_round": {"score": {"total": 25}}}
    result = adjust(state)
    assert result["difficulty"] == "easy"


def test_difficulty_adjustment_hard_to_medium():
    """Low score (<40) on hard should drop to medium."""
    state = {"round_num": 0, "difficulty": "hard", "current_round": {"score": {"total": 30}}}
    result = adjust(state)
    assert result["difficulty"] == "medium"


def test_difficulty_stays_easy_on_low_score():
    """Low score on easy should stay easy (no downgrade possible)."""
    state = {"round_num": 0, "difficulty": "easy", "current_round": {"score": {"total": 10}}}
    result = adjust(state)
    assert result["difficulty"] == "easy"


def test_difficulty_stays_hard_on_high_score():
    """High score on hard should stay hard (no upgrade possible)."""
    state = {"round_num": 0, "difficulty": "hard", "current_round": {"score": {"total": 100}}}
    result = adjust(state)
    assert result["difficulty"] == "hard"


def test_adjust_archives_current_round():
    """adjust() should archive the current round into the rounds list."""
    current_round = {
        "round_num": 0,
        "challenge": "Two Sum",
        "score": {"total": 60},
    }
    state = {
        "round_num": 0,
        "difficulty": "easy",
        "current_round": current_round,
    }
    result = adjust(state)
    # rounds is Annotated[list, add] — result provides the delta to append
    assert result["rounds"] == [current_round]


