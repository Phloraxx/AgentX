"""Shared fixtures for AgentX backend tests."""

import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture
def mock_llm():
    """Create a mock LLM that returns configurable responses."""
    llm = MagicMock()
    llm.bind_tools.return_value = llm
    return llm


@pytest.fixture
def mock_sandbox():
    """Create a mock sandbox that returns success."""
    sandbox = MagicMock()
    sandbox.run.return_value = {
        "stdout": "4\n",
        "stderr": "",
        "exit_code": 0,
        "duration_ms": 10,
        "sandbox": "mock",
    }
    return sandbox


@pytest.fixture
def sample_state():
    """Minimal valid SessionState for testing."""
    return {
        "session_id": "test-001",
        "language": "python",
        "topic": "arrays",
        "difficulty": "easy",
        "round_num": 0,
        "max_rounds": 3,
        "phase": "setup",
        "current_round": {
            "round_num": 0,
            "challenge": "Two Sum",
            "original_code": "def two_sum(nums, target):\n    pass",
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


@pytest.fixture
def sample_buggy_state(sample_state):
    """State after sabotage, ready for student fix."""
    state = {**sample_state}
    state["phase"] = "student_fixing"
    state["current_round"] = {
        **state["current_round"],
        "buggy_code": (
            "def two_sum(nums, target):\n"
            "    for i in range(len(nums)):\n"
            "        for j in range(i, len(nums)):\n"
            "            if nums[i] + nums[j] == target:\n"
            "                return [i, j]\n"
            "    return []"
        ),
        "bug_manifest": [
            {
                "line": 3,
                "type": "off_by_one",
                "description": "Inner loop starts at i instead of i+1",
                "original": "range(i+1",
                "sabotaged": "range(i",
            }
        ],
        "original_exec": {
            "stdout": "",
            "stderr": "",
            "exit_code": 0,
            "duration_ms": 10,
            "sandbox": "mock",
        },
        "buggy_exec": {
            "stdout": "",
            "stderr": "",
            "exit_code": 0,
            "duration_ms": 10,
            "sandbox": "mock",
        },
    }
    return state
