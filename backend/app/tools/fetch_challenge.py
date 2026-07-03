"""Fetch coding challenges from the web via Exa API + LLM extraction."""

import logging
from langchain_core.tools import tool
from app.config import settings
from app.utils import parse_json_response

logger = logging.getLogger(__name__)


@tool
def fetch_challenge(topic: str, difficulty: str, language: str) -> dict:
    """Fetch a coding challenge from the web matching the topic and difficulty.

    Two-stage pipeline:
    1. Exa search returns raw page text from LeetCode / HackerRank / Codewars.
    2. An LLM extracts a structured challenge (description, starter code, test
       cases) from that raw text.

    Falls back to a hardcoded challenge bank if Exa is unavailable or the LLM
    can't extract a valid problem (JS-heavy SPAs return nav chrome, not content).

    Args:
        topic: The topic to search for (e.g., "arrays", "strings", "trees").
        difficulty: "easy", "medium", or "hard".
        language: "python" or "javascript".

    Returns:
        Dict with ``challenge_detail`` (structured) on success, or fallback.
    """
    try:
        from exa_py import Exa

        exa = Exa(settings.exa_api_key.get_secret_value())

        query = (
            f"{difficulty} {topic} coding problem {language} "
            "site:leetcode.com OR site:hackerrank.com OR site:codewars.com"
        )
        results = exa.search_and_contents(query, num_results=3, text=True)

        if not results.results:
            results = exa.search_and_contents(
                f"{difficulty} {topic} coding challenge", num_results=3, text=True
            )

        if not results.results:
            logger.warning("Exa returned no results, using fallback")
            return _fallback_challenge(topic, difficulty, language)

        # Gather raw page text for LLM extraction
        raw_context = "\n\n---\n\n".join(
            f"Title: {r.title or 'Unknown'}\nURL: {r.url}\nContent:\n{(r.text or '')[:2000]}"
            for r in results.results[:3]
        )
        source_url = results.results[0].url

        # LLM-parse the raw text into a structured challenge
        challenge_detail = _llm_parse_challenge(raw_context, topic, difficulty, language)

        if challenge_detail and _validate_challenge(challenge_detail, language):
            return {
                "ok": True,
                "challenges": [
                    {
                        "title": challenge_detail["title"],
                        "url": source_url,
                        "snippet": challenge_detail["description"][:200],
                        "source": "exa+llm",
                    }
                ],
                "challenge_detail": challenge_detail,
                "query": query,
            }

        logger.warning("LLM challenge parse failed or invalid, using fallback")
        return _fallback_challenge(topic, difficulty, language)

    except ImportError:
        logger.warning("exa-py not installed, using fallback challenge")
        return _fallback_challenge(topic, difficulty, language)
    except Exception as e:
        logger.error(f"fetch_challenge error: {e}")
        return _fallback_challenge(topic, difficulty, language)


# ── LLM extraction ──────────────────────────────────────────────────────────


def _llm_parse_challenge(
    raw_context: str, topic: str, difficulty: str, language: str
) -> dict | None:
    """Use the Host LLM to extract a structured challenge from raw Exa text."""
    from app.agents.base import make_llm
    from langchain_core.messages import SystemMessage, HumanMessage

    llm = make_llm("host", temperature=0.1, max_tokens=2500)

    system = (
        "You extract structured coding challenges from raw web page text.\n"
        "Return ONLY valid JSON — no markdown, no explanation.\n\n"
        "Schema:\n"
        "{\n"
        f'  "title": "<short problem title>",\n'
        '  "description": "<2-4 sentence problem description: what to solve and what to return>",\n'
        '  "starter_code": {\n'
        f'    "{language}": "<starter code with function signature and pass/empty body>"\n'
        "  },\n"
        '  "test_cases": [\n'
        '    {"function_call": "<expression calling the function>", "expected": "<return value as JSON>"}\n'
        "  ],\n"
        '  "constraints": "<constraints or empty string>"\n'
        "}\n\n"
        "Rules:\n"
        "- Extract a REAL coding problem from the text.\n"
        '- If the text is navigation/loading/cookie chrome with no actual problem, return {"error": "no problem found"}.\n'
        "- test_cases MUST have at least 2 entries with concrete function_call expressions.\n"
        f"- function_call must be a valid {language} expression that calls the function "
        '(e.g. "two_sum([2,7,11,15], 9)").\n'
        '- expected must be the correct return value as JSON (e.g. "[0,1]", "3", "true").\n'
        "- starter_code must include a function signature matching the test_calls.\n"
        '- If no real problem exists in the text, return {"error": "no problem found"}.'
    )

    human = (
        f"Extract a {difficulty} {topic} coding challenge for {language} "
        f"from this web content:\n\n{raw_context}\n\nReturn ONLY JSON."
    )

    try:
        response = llm.invoke([SystemMessage(content=system), HumanMessage(content=human)])
        return parse_json_response(response.content)
    except Exception as e:
        logger.error(f"LLM parse error: {e}")
        return None


def _validate_challenge(challenge: dict | None, language: str) -> bool:
    """Validate that a parsed challenge has all required fields."""
    if not challenge or challenge.get("error"):
        return False
    if not challenge.get("title") or not challenge.get("description"):
        return False
    starter = challenge.get("starter_code", {})
    if not starter.get(language):
        return False
    test_cases = challenge.get("test_cases", [])
    if len(test_cases) < 2:
        return False
    for tc in test_cases:
        if not tc.get("function_call") or not tc.get("expected"):
            return False
    return True


# ── Hardcoded fallback bank ──────────────────────────────────────────────────


def _fallback_challenge(topic: str, difficulty: str, language: str, used: list[str] | None = None) -> dict:
    """Return a hardcoded fallback challenge when Exa is unavailable."""
    fallbacks = {
        ("arrays", "easy"): {
            "title": "Two Sum",
            "description": "Given an array of integers nums and an integer target, return indices of the two numbers that add up to target. You may assume exactly one solution exists.",
            "starter_code": {
                "python": "def two_sum(nums, target):\n    # Your code here\n    pass",
                "javascript": "function twoSum(nums, target) {\n    // Your code here\n}",
            },
            "test_cases": [
                {"function_call": "two_sum([2,7,11,15], 9)", "expected": "[0,1]"},
                {"function_call": "two_sum([3,2,4], 6)", "expected": "[1,2]"},
            ],
            "constraints": "1 <= nums.length <= 10^4, -10^9 <= nums[i] <= 10^9",
        },
        ("arrays", "medium"): {
            "title": "Container With Most Water",
            "description": "Given an array of non-negative integers height where each represents a point at coordinate (i, height[i]), find two lines that together with the x-axis form a container holding the most water. Return the maximum area.",
            "starter_code": {
                "python": "def max_area(height):\n    # Your code here\n    pass",
                "javascript": "function maxArea(height) {\n    // Your code here\n}",
            },
            "test_cases": [
                {"function_call": "max_area([1,8,6,2,5,4,8,3,7])", "expected": "49"},
                {"function_call": "max_area([1,1])", "expected": "1"},
            ],
            "constraints": "2 <= height.length <= 10^5, 0 <= height[i] <= 10^4",
        },
        ("arrays", "hard"): {
            "title": "Trapping Rain Water",
            "description": "Given an array of non-negative integers height representing an elevation map where the width of each bar is 1, compute how much water it can trap after raining.",
            "starter_code": {
                "python": "def trap(height):\n    # Your code here\n    pass",
                "javascript": "function trap(height) {\n    // Your code here\n}",
            },
            "test_cases": [
                {"function_call": "trap([0,1,0,2,1,0,1,3,2,1,2,1])", "expected": "6"},
                {"function_call": "trap([4,2,0,3,2,5])", "expected": "9"},
            ],
            "constraints": "1 <= height.length <= 2 * 10^4, 0 <= height[i] <= 10^5",
        },
        ("strings", "easy"): {
            "title": "Valid Palindrome",
            "description": "Given a string s, return true if it is a palindrome considering only alphanumeric characters and ignoring case.",
            "starter_code": {
                "python": "def is_palindrome(s):\n    # Your code here\n    pass",
                "javascript": "function isPalindrome(s) {\n    // Your code here\n}",
            },
            "test_cases": [
                {"function_call": 'is_palindrome("A man, a plan, a canal: Panama")', "expected": "true"},
                {"function_call": 'is_palindrome("race a car")', "expected": "false"},
            ],
            "constraints": "1 <= s.length <= 2 * 10^5, s consists of printable ASCII characters",
        },
        ("strings", "medium"): {
            "title": "Longest Substring Without Repeating Characters",
            "description": "Given a string s, find the length of the longest substring without repeating characters.",
            "starter_code": {
                "python": "def length_of_longest_substring(s):\n    # Your code here\n    pass",
                "javascript": "function lengthOfLongestSubstring(s) {\n    // Your code here\n}",
            },
            "test_cases": [
                {"function_call": 'length_of_longest_substring("abcabcbb")', "expected": "3"},
                {"function_call": 'length_of_longest_substring("bbbbb")', "expected": "1"},
            ],
            "constraints": "0 <= s.length <= 5 * 10^4, s consists of English letters, digits, symbols and spaces",
        },
        ("strings", "hard"): {
            "title": "Minimum Window Substring",
            "description": "Given two strings s and t, return the minimum window substring of s such that every character in t is included in the window. If no such substring exists, return an empty string.",
            "starter_code": {
                "python": "def min_window(s, t):\n    # Your code here\n    pass",
                "javascript": "function minWindow(s, t) {\n    // Your code here\n}",
            },
            "test_cases": [
                {"function_call": 'min_window("ADOBECODEBANC", "ABC")', "expected": '"BANC"'},
                {"function_call": 'min_window("a", "a")', "expected": '"a"'},
            ],
            "constraints": "1 <= s.length, t.length <= 10^5, s and t consist of uppercase and lowercase English letters",
        },
        ("trees", "easy"): {
            "title": "Maximum Depth of Binary Tree",
            "description": "Given the root of a binary tree, return its maximum depth — the number of nodes along the longest path from the root node down to the farthest leaf node.",
            "starter_code": {
                "python": "class TreeNode:\n    def __init__(self, val=0, left=None, right=None):\n        self.val = val\n        self.left = left\n        self.right = right\n\ndef max_depth(root):\n    # Your code here\n    pass",
                "javascript": "class TreeNode {\n    constructor(val, left, right) {\n        this.val = val ?? 0;\n        this.left = left ?? null;\n        this.right = right ?? null;\n    }\n}\n\nfunction maxDepth(root) {\n    // Your code here\n}",
            },
            "test_cases": [
                {"function_call": "max_depth(TreeNode(3, TreeNode(9), TreeNode(20, TreeNode(15), TreeNode(7))))", "expected": "3"},
                {"function_call": "max_depth(TreeNode(1, None, TreeNode(2)))", "expected": "2"},
            ],
            "constraints": "Number of nodes in range [0, 10^4], -100 <= Node.val <= 100",
        },
        ("trees", "medium"): {
            "title": "Level Order Traversal",
            "description": "Given the root of a binary tree, return the level order traversal of its nodes' values (left to right, level by level).",
            "starter_code": {
                "python": "class TreeNode:\n    def __init__(self, val=0, left=None, right=None):\n        self.val = val\n        self.left = left\n        self.right = right\n\ndef level_order(root):\n    # Your code here\n    pass",
                "javascript": "class TreeNode {\n    constructor(val, left, right) {\n        this.val = val ?? 0;\n        this.left = left ?? null;\n        this.right = right ?? null;\n    }\n}\n\nfunction levelOrder(root) {\n    // Your code here\n}",
            },
            "test_cases": [
                {"function_call": "level_order(TreeNode(3, TreeNode(9), TreeNode(20, TreeNode(15), TreeNode(7))))", "expected": "[[3],[9,20],[15,7]]"},
                {"function_call": "level_order(TreeNode(1))", "expected": "[[1]]"},
            ],
            "constraints": "Number of nodes in range [0, 2000], -1000 <= Node.val <= 1000",
        },
        ("trees", "hard"): {
            "title": "Binary Tree Maximum Path Sum",
            "description": "Given the root of a non-empty binary tree, return the maximum path sum of any non-empty path. A path is a sequence of nodes where each pair of adjacent nodes has an edge connecting them, and no node appears more than once.",
            "starter_code": {
                "python": "class TreeNode:\n    def __init__(self, val=0, left=None, right=None):\n        self.val = val\n        self.left = left\n        self.right = right\n\ndef max_path_sum(root):\n    # Your code here\n    pass",
                "javascript": "class TreeNode {\n    constructor(val, left, right) {\n        this.val = val ?? 0;\n        this.left = left ?? null;\n        this.right = right ?? null;\n    }\n}\n\nfunction maxPathSum(root) {\n    // Your code here\n}",
            },
            "test_cases": [
                {"function_call": "max_path_sum(TreeNode(1, TreeNode(2), TreeNode(3)))", "expected": "6"},
                {"function_call": "max_path_sum(TreeNode(-10, TreeNode(9), TreeNode(20, TreeNode(15), TreeNode(7))))", "expected": "42"},
            ],
            "constraints": "Number of nodes in range [1, 3*10^4], -1000 <= Node.val <= 1000",
        },
    }

    if used is None:
        used = []

    key = (topic, difficulty)
    if key in fallbacks:
        challenge = fallbacks[key]
        if challenge["title"] not in used:
            return {
                "ok": True,
                "challenges": [
                    {
                        "title": challenge["title"],
                        "url": f"https://leetcode.com/problems/{challenge['title'].lower().replace(' ', '-')}",
                        "snippet": challenge["description"],
                        "source": "fallback",
                    }
                ],
                "challenge_detail": challenge,
                "query": f"fallback: {topic} {difficulty}",
            }

    # Generic fallback
    return {
        "ok": True,
        "challenges": [
            {
                "title": f"Generic {difficulty} {topic} challenge",
                "url": "",
                "snippet": f"Solve a {difficulty} {topic} problem in {language}.",
                "source": "fallback",
            }
        ],
        "challenge_detail": {
            "title": f"Generic {difficulty} {topic} challenge",
            "description": f"Write a function that solves a {difficulty} {topic} problem.",
            "starter_code": {
                "python": "def solve(input_data):\n    # Your code here\n    pass",
                "javascript": "function solve(inputData) {\n    // Your code here\n}",
            },
            "test_cases": [
                {"function_call": "solve([1,2,3])", "expected": "[1,2,3]"},
                {"function_call": "solve([])", "expected": "[]"},
            ],
            "constraints": "",
        },
        "query": f"fallback: {topic} {difficulty}",
    }
