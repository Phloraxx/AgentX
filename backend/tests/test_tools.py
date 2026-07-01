"""Tests for tool functions: fetch_challenge fallback and inject_bugs tool."""

import pytest
from unittest.mock import patch, MagicMock
from app.tools.fetch_challenge import _fallback_challenge


class TestFallbackChallenge:
    """Tests for the _fallback_challenge function: hardcoded challenge retrieval."""

    def test_arrays_easy(self):
        result = _fallback_challenge("arrays", "easy", "python")
        assert result["ok"] is True
        assert result["challenge_detail"]["title"] == "Two Sum"
        assert "starter_code" in result["challenge_detail"]
        assert "test_cases" in result["challenge_detail"]
        assert len(result["challenge_detail"]["test_cases"]) > 0

    def test_arrays_medium(self):
        result = _fallback_challenge("arrays", "medium", "python")
        assert result["ok"] is True
        assert result["challenge_detail"]["title"] == "Container With Most Water"

    def test_arrays_hard(self):
        result = _fallback_challenge("arrays", "hard", "python")
        assert result["ok"] is True
        assert result["challenge_detail"]["title"] == "Trapping Rain Water"

    def test_strings_easy(self):
        result = _fallback_challenge("strings", "easy", "python")
        assert result["ok"] is True
        assert result["challenge_detail"]["title"] == "Valid Palindrome"

    def test_unknown_topic_generic(self):
        result = _fallback_challenge("unknown_topic", "easy", "python")
        assert result["ok"] is True
        assert "Generic" in result["challenge_detail"]["title"]
        assert result["challenge_detail"]["test_cases"] == []

    def test_starter_code_javascript(self):
        result = _fallback_challenge("arrays", "easy", "javascript")
        assert result["ok"] is True
        assert "javascript" in result["challenge_detail"]["starter_code"]
        assert "function twoSum" in result["challenge_detail"]["starter_code"]["javascript"]

    def test_starter_code_python(self):
        result = _fallback_challenge("arrays", "easy", "python")
        assert result["ok"] is True
        assert "python" in result["challenge_detail"]["starter_code"]
        assert "def two_sum" in result["challenge_detail"]["starter_code"]["python"]

    def test_challenge_detail_has_required_fields(self):
        result = _fallback_challenge("arrays", "easy", "python")
        detail = result["challenge_detail"]
        assert "title" in detail
        assert "description" in detail
        assert "starter_code" in detail
        assert "test_cases" in detail
        assert "constraints" in detail

    def test_challenges_list_structure(self):
        result = _fallback_challenge("arrays", "easy", "python")
        challenges = result["challenges"]
        assert isinstance(challenges, list)
        assert len(challenges) == 1
        ch = challenges[0]
        assert "title" in ch
        assert "url" in ch
        assert "snippet" in ch
        assert ch["source"] == "fallback"

    def test_generic_fallback_has_empty_url(self):
        result = _fallback_challenge("nonexistent", "easy", "python")
        assert result["challenges"][0]["url"] == ""


class TestInjectBugsTool:
    """Tests for the inject_bugs tool: mock LLM + sandbox, verify result structure.

    These tests require app.tools.inject_bugs to exist. They skip if the module
    hasn't been implemented yet (part of Phase C in FIX_PLAN).
    """

    @pytest.fixture(autouse=True)
    def _import_check(self):
        try:
            from app.tools.inject_bugs import inject_bugs_tool  # noqa: F401
            self._has_module = True
        except (ImportError, ModuleNotFoundError):
            self._has_module = False

    @pytest.fixture
    def mock_llm_for_inject(self):
        llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = (
            '{"bugs": [{"line": 2, "type": "logic", '
            '"description": "off by one", '
            '"original": "pass", '
            '"sabotaged": "return None"}], '
            '"test_cases": [{"input": "foo()", "expected": "bar"}]}'
        )
        llm.invoke.return_value = mock_response
        return llm

    def test_inject_bugs_success(self, mock_llm_for_inject):
        if not self._has_module:
            pytest.skip("app.tools.inject_bugs not yet implemented")

        with patch("app.agents.base.make_llm", return_value=mock_llm_for_inject), \
             patch("app.sandbox.manager.get_sandbox") as mock_get_sandbox:
            mock_sandbox = MagicMock()
            mock_sandbox.run.return_value = {
                "stdout": "",
                "stderr": "",
                "exit_code": 0,
                "duration_ms": 10,
                "sandbox": "mock",
            }
            mock_get_sandbox.return_value = mock_sandbox

            from app.tools.inject_bugs import inject_bugs_tool
            result = inject_bugs_tool.invoke({
                "original_code": "def foo():\n    pass",
                "difficulty": "easy",
                "language": "python",
            })

            assert result["ok"] is True
            assert "buggy_code" in result
            assert isinstance(result["bug_manifest"], list)
            assert len(result["bug_manifest"]) == 1
            assert result["bug_manifest"][0]["type"] == "logic"

    def test_inject_bugs_returns_expected_keys(self, mock_llm_for_inject):
        if not self._has_module:
            pytest.skip("app.tools.inject_bugs not yet implemented")

        with patch("app.agents.base.make_llm", return_value=mock_llm_for_inject), \
             patch("app.sandbox.manager.get_sandbox") as mock_get_sandbox:
            mock_sandbox = MagicMock()
            mock_sandbox.run.return_value = {
                "stdout": "",
                "stderr": "",
                "exit_code": 0,
                "duration_ms": 10,
                "sandbox": "mock",
            }
            mock_get_sandbox.return_value = mock_sandbox

            from app.tools.inject_bugs import inject_bugs_tool
            result = inject_bugs_tool.invoke({
                "original_code": "def foo():\n    pass",
                "difficulty": "easy",
                "language": "python",
            })

            expected_keys = {"ok", "buggy_code", "bug_manifest", "test_cases"}
            assert expected_keys.issubset(set(result.keys()))
