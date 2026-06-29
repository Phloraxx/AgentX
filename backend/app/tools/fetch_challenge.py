"""Fetch coding challenges from the web via Exa API."""

import logging
from langchain_core.tools import tool
from app.config import settings

logger = logging.getLogger(__name__)


@tool
def fetch_challenge(topic: str, difficulty: str, language: str) -> dict:
    """Fetch a coding challenge from the web matching the topic and difficulty.

    Uses Exa API to search for real coding problems from sites like LeetCode,
    HackerRank, and CodeWars.

    Args:
        topic: The topic to search for (e.g., "arrays", "strings", "trees")
        difficulty: The difficulty level ("easy", "medium", "hard")
        language: The programming language ("python", "javascript")

    Returns:
        A dict with the challenge details or an error.
    """
    try:
        from exa_py import Exa

        exa = Exa(settings.exa_api_key.get_secret_value())

        # Build search query
        query = f"{difficulty} {topic} coding problem {language} site:leetcode.com OR site:hackerrank.com OR site:codewars.com"

        results = exa.search_and_contents(
            query,
            num_results=3,
            text=True,
        )

        if not results.results:
            # Fallback: try a broader query
            results = exa.search_and_contents(
                f"{difficulty} {topic} coding challenge",
                num_results=3,
                text=True,
            )

        # Extract and format the best result
        challenges = []
        for r in results.results:
            challenges.append({
                "title": r.title or "Unknown",
                "url": r.url,
                "snippet": (r.text or "")[:500],
                "source": r.url.split("/")[2] if "/" in r.url else "unknown",
            })

        return {
            "ok": True,
            "challenges": challenges,
            "query": query,
        }

    except ImportError:
        logger.warning("exa-py not installed, using fallback challenge")
        return _fallback_challenge(topic, difficulty, language)
    except Exception as e:
        logger.error(f"Exa API error: {e}")
        return _fallback_challenge(topic, difficulty, language)


def _fallback_challenge(topic: str, difficulty: str, language: str, used: list[str] | None = None) -> dict:
    """Return a hardcoded fallback challenge when Exa is unavailable."""
    fallbacks = {
        ("arrays", "easy"): {
            "title": "Two Sum",
            "description": "Given an array of integers and a target, return indices of two numbers that add up to the target.",
            "starter_code": {
                "python": "def two_sum(nums, target):\n    # Your code here\n    pass",
                "javascript": "function twoSum(nums, target) {\n    // Your code here\n}",
            },
            "test_cases": [
                {"input": "nums=[2,7,11,15], target=9", "expected": "[0,1]"},
                {"input": "nums=[3,2,4], target=6", "expected": "[1,2]"},
            ],
            "constraints": "1 <= nums.length <= 10^4, -10^9 <= nums[i] <= 10^9",
        },
        ("arrays", "medium"): {
            "title": "Container With Most Water",
            "description": "Find two lines that together with the x-axis forms a container that holds the most water.",
            "starter_code": {
                "python": "def max_area(height):\n    # Your code here\n    pass",
                "javascript": "function maxArea(height) {\n    // Your code here\n}",
            },
            "test_cases": [
                {"input": "height=[1,8,6,2,5,4,8,3,7]", "expected": "49"},
                {"input": "height=[1,1]", "expected": "1"},
            ],
            "constraints": "2 <= height.length <= 10^5, 0 <= height[i] <= 10^4",
        },
        ("arrays", "hard"): {
            "title": "Trapping Rain Water",
            "description": "Compute how much water it can trap after raining.",
            "starter_code": {
                "python": "def trap(height):\n    # Your code here\n    pass",
                "javascript": "function trap(height) {\n    // Your code here\n}",
            },
            "test_cases": [
                {"input": "height=[0,1,0,2,1,0,1,3,2,1,2,1]", "expected": "6"},
                {"input": "height=[4,2,0,3,2,5]", "expected": "9"},
            ],
            "constraints": "1 <= height.length <= 2 * 10^4, 0 <= height[i] <= 10^5",
        },
        ("strings", "easy"): {
            "title": "Valid Palindrome",
            "description": "Check if a string is a palindrome considering only alphanumeric characters.",
            "starter_code": {
                "python": "def is_palindrome(s):\n    # Your code here\n    pass",
                "javascript": "function isPalindrome(s) {\n    // Your code here\n}",
            },
            "test_cases": [
                {"input": "s = 'A man, a plan, a canal: Panama'", "expected": "True"},
                {"input": "s = 'race a car'", "expected": "False"},
            ],
            "constraints": "1 <= s.length <= 2 * 10^5, s consists of printable ASCII characters",
        },
        ("strings", "medium"): {
            "title": "Longest Substring Without Repeating Characters",
            "description": "Find the length of the longest substring without repeating characters.",
            "starter_code": {
                "python": "def length_of_longest_substring(s):\n    # Your code here\n    pass",
                "javascript": "function lengthOfLongestSubstring(s) {\n    // Your code here\n}",
            },
            "test_cases": [
                {"input": "s = 'abcabcbb'", "expected": "3"},
                {"input": "s = 'bbbbb'", "expected": "1"},
            ],
            "constraints": "0 <= s.length <= 5 * 10^4, s consists of English letters, digits, symbols and spaces",
        },
        ("strings", "hard"): {
            "title": "Minimum Window Substring",
            "description": "Find the minimum window in s which will contain all the characters of t.",
            "starter_code": {
                "python": "def min_window(s, t):\n    # Your code here\n    pass",
                "javascript": "function minWindow(s, t) {\n    // Your code here\n}",
            },
            "test_cases": [
                {"input": "s = 'ADOBECODEBANC', t = 'ABC'", "expected": "'BANC'"},
                {"input": "s = 'a', t = 'a'", "expected": "'a'"},
            ],
            "constraints": "m == s.length, n == t.length, 1 <= m, n <= 10^5, s and t consist of uppercase and lowercase English letters",
        },
        ("trees", "easy"): {
            "title": "Maximum Depth of Binary Tree",
            "description": "Find the maximum depth of a binary tree.",
            "starter_code": {
                "python": "class TreeNode:\n    def __init__(self, val=0, left=None, right=None):\n        self.val = val\n        self.left = left\n        self.right = right\n\ndef max_depth(root):\n    # Your code here\n    pass",
                "javascript": "class TreeNode {\n    constructor(val, left, right) {\n        this.val = val ?? 0;\n        this.left = left ?? null;\n        this.right = right ?? null;\n    }\n}\n\nfunction maxDepth(root) {\n    // Your code here\n}",
            },
            "test_cases": [
                {"input": "root = [3,9,20,null,null,15,7]", "expected": "3"},
                {"input": "root = [1,null,2]", "expected": "2"},
            ],
            "constraints": "The number of nodes is in range [0, 10^4], -100 <= Node.val <= 100",
        },
    }

    if used is None:
        used = []

    # Try to find a matching fallback that hasn't been used yet
    key = (topic, difficulty)
    if key in fallbacks:
        challenge = fallbacks[key]
        if challenge["title"] not in used:
            return {
                "ok": True,
                "challenges": [{
                    "title": challenge["title"],
                    "url": f"https://leetcode.com/problems/{challenge['title'].lower().replace(' ', '-')}",
                    "snippet": challenge["description"],
                    "source": "fallback",
                }],
                "challenge_detail": challenge,
                "query": f"fallback: {topic} {difficulty}",
            }

    # Generic fallback
    return {
        "ok": True,
        "challenges": [{
            "title": f"Generic {difficulty} {topic} challenge",
            "url": "",
            "snippet": f"Solve a {difficulty} {topic} problem in {language}.",
            "source": "fallback",
        }],
        "challenge_detail": {
            "title": f"Generic {difficulty} {topic} challenge",
            "description": f"Write a function that solves a {difficulty} {topic} problem.",
            "starter_code": {
                "python": f"def solve(input_data):\n    # Your code here\n    pass",
                "javascript": f"function solve(inputData) {{\n    // Your code here\n}}",
            },
            "test_cases": [],
            "constraints": "",
        },
        "query": f"fallback: {topic} {difficulty}",
    }
