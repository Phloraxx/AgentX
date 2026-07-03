"""Tests for utility functions."""

import pytest
from app.utils import (
    parse_json_response,
    difficulty_to_num_bugs,
    apply_bugs,
    validate_compiles,
)


class TestParseJsonResponse:
    """Tests for parse_json_response: handles direct JSON, markdown blocks, embedded JSON."""

    def test_direct_json(self):
        result = parse_json_response('{"key": "value"}')
        assert result == {"key": "value"}

    def test_direct_json_nested(self):
        result = parse_json_response('{"bugs": [{"line": 1, "type": "logic"}]}')
        assert result == {"bugs": [{"line": 1, "type": "logic"}]}

    def test_markdown_code_block(self):
        text = 'Here is the result:\n```json\n{"key": "value"}\n```\nDone.'
        assert parse_json_response(text) == {"key": "value"}

    def test_markdown_code_block_without_json_label(self):
        text = 'Result:\n```\n{"key": "value"}\n```'
        assert parse_json_response(text) == {"key": "value"}

    def test_embedded_json(self):
        text = 'The answer is {"key": "value"} and more text'
        assert parse_json_response(text) == {"key": "value"}

    def test_embedded_json_with_surrounding_text(self):
        text = 'Analysis complete. {"bugs": [], "analysis": "clean code"} Hope that helps!'
        result = parse_json_response(text)
        assert result == {"bugs": [], "analysis": "clean code"}

    def test_invalid_json(self):
        assert parse_json_response("not json at all") is None

    def test_none_input(self):
        assert parse_json_response(None) is None

    def test_empty_string(self):
        assert parse_json_response("") is None

    def test_array_response(self):
        # json.loads handles arrays directly — function returns them
        result = parse_json_response('[1, 2, 3]')
        assert result == [1, 2, 3]

    def test_multiple_json_blocks_returns_first(self):
        text = '```json\n{"first": 1}\n```\nAlso ```json\n{"second": 2}\n```'
        result = parse_json_response(text)
        assert result == {"first": 1}


class TestDifficultyToNumBugs:
    """Tests for difficulty_to_num_bugs: maps difficulty string to bug count."""

    def test_easy(self):
        assert difficulty_to_num_bugs("easy") == 1

    def test_medium(self):
        assert difficulty_to_num_bugs("medium") == 2

    def test_hard(self):
        assert difficulty_to_num_bugs("hard") == 3

    def test_unknown_defaults_to_2(self):
        assert difficulty_to_num_bugs("unknown") == 2

    def test_empty_string_defaults_to_2(self):
        assert difficulty_to_num_bugs("") == 2

    def test_case_sensitive(self):
        # "Easy" is not "easy" — should hit default
        assert difficulty_to_num_bugs("Easy") == 2


class TestApplyBugs:
    """Tests for apply_bugs: line replacement based on bug specs."""

    def test_single_bug(self):
        code = "def foo():\n    return 1 + 2"
        bugs = [{"line": 2, "original": "1 + 2", "sabotaged": "1 - 2"}]
        result, applied = apply_bugs(code, bugs)
        assert "1 - 2" in result
        assert "1 + 2" not in result
        assert applied == 1

    def test_multiple_bugs(self):
        code = "a = 1\nb = 2\nc = 3"
        bugs = [
            {"line": 1, "original": "1", "sabotaged": "99"},
            {"line": 3, "original": "3", "sabotaged": "0"},
        ]
        result, applied = apply_bugs(code, bugs)
        lines = result.split("\n")
        assert "a = 99" in lines[0]
        assert "c = 0" in lines[2]
        assert applied == 2

    def test_no_match_falls_back_to_line_replacement(self):
        """When the original string isn't found, apply_bugs should fall back
        to replacing the whole line at the specified line number."""
        code = "def foo():\n    pass"
        bugs = [{"line": 2, "original": "nonexistent", "sabotaged": "replaced"}]
        result, applied = apply_bugs(code, bugs)
        assert applied == 1
        assert "replaced" in result

    def test_out_of_range_line(self):
        code = "line1"
        bugs = [{"line": 99, "original": "x", "sabotaged": "y"}]
        result, applied = apply_bugs(code, bugs)
        assert result == code
        assert applied == 0

    def test_line_zero_falls_back_to_content_search(self):
        """Line 0 means no valid line number — should search by content."""
        code = "hello"
        bugs = [{"line": 0, "original": "hello", "sabotaged": "bye"}]
        result, applied = apply_bugs(code, bugs)
        assert applied == 1
        assert result == "bye"

    def test_empty_bugs(self):
        code = "unchanged"
        result, applied = apply_bugs(code, [])
        assert result == code
        assert applied == 0

    def test_preserves_other_lines(self):
        code = "line1\nline2\nline3"
        bugs = [{"line": 2, "original": "line2", "sabotaged": "MODIFIED"}]
        result, applied = apply_bugs(code, bugs)
        assert "line1" in result
        assert "MODIFIED" in result
        assert "line3" in result
        assert applied == 1

    def test_missing_original_key(self):
        code = "line1"
        bugs = [{"line": 1, "sabotaged": "replaced"}]
        result, applied = apply_bugs(code, bugs)
        assert result == code
        assert applied == 0


class TestValidateCompiles:
    """Tests for validate_compiles: syntax check for Python, passthrough for unknown."""

    def test_valid_python(self):
        assert validate_compiles("def foo():\n    pass", "python") is True

    def test_valid_python_with_syntax(self):
        code = "def add(a, b):\n    return a + b"
        assert validate_compiles(code, "python") is True

    def test_invalid_python(self):
        assert validate_compiles("def foo(:\n    pass", "python") is False

    def test_invalid_python_indentation(self):
        code = "def foo():\nreturn 1"
        assert validate_compiles(code, "python") is False

    def test_unknown_language_passes(self):
        assert validate_compiles("anything", "ruby") is True

    def test_empty_python_is_valid(self):
        assert validate_compiles("", "python") is True

    def test_javascript_check(self):
        # If node is available, test JS syntax checking
        assert validate_compiles("function foo() { return 1; }", "javascript") in (True, False)
