"""Graph nodes — each returns a partial state update dict.

Real LLM-backed implementations for the agent loop.
"""

import logging
from datetime import datetime, timezone
from app.graph.state import SessionState
from app.utils import parse_json_response

logger = logging.getLogger(__name__)

# --- Emit callback for WebSocket real-time streaming ---

_emit_callbacks: dict[str, callable] = {}  # Session-keyed, set by routes.py


def set_emit_callback_for_session(session_id: str, callback):
    """Set the event emission callback for a specific session."""
    if callback is None:
        _emit_callbacks.pop(session_id, None)
    else:
        _emit_callbacks[session_id] = callback


def _trace_event(phase: str, agent: str, tool: str | None = None,
                 args: dict | None = None, result: dict | None = None) -> dict:
    """Build a trace event for the frontend TracePanel."""
    return {
        "type": "trace_event",
        "phase": phase,
        "agent": agent,
        "tool": tool,
        "args": args or {},
        "result": result,
        "ts": datetime.now(timezone.utc).isoformat(),
    }


def _trace_and_emit(phase: str, agent: str, tool: str | None = None,
                    args: dict | None = None, result: dict | None = None,
                    session_id: str | None = None) -> dict:
    """Build trace event and emit it via callback for real-time streaming."""
    event = _trace_event(phase, agent, tool, args, result)
    cb = _emit_callbacks.get(session_id) if session_id else None
    if cb:
        try:
            cb(event)
        except Exception:
            pass  # Don't let emit errors break the graph
    return event


# --- Real nodes with LLM calls ---


def host_setup(state: SessionState) -> dict:
    """Fetch challenge and initialize the round.

    Calls Host LLM with fetch_challenge tool to find a real coding problem.
    """
    from app.agents.base import make_llm
    from app.prompts import HOST_SYSTEM_PROMPT
    from app.tools.fetch_challenge import fetch_challenge

    llm = make_llm("host", temperature=0.4)
    topic = state.get("topic", "arrays")
    difficulty = state.get("difficulty", "easy")
    language = state.get("language", "python")
    session_id = state.get("session_id", "")

    # Call Host LLM to fetch and present a challenge
    from langchain_core.messages import SystemMessage, HumanMessage

    messages = [
        SystemMessage(content=HOST_SYSTEM_PROMPT),
        HumanMessage(content=f"""\
Find a {difficulty} {topic} coding challenge for a student learning {language}.

Use the fetch_challenge tool to search for a real problem.
Return the challenge details including title, description, starter code, and test cases."""),
    ]

    # Bind the tool and invoke
    llm_with_tools = llm.bind_tools([fetch_challenge])

    fallback_chat = []
    try:
        response = llm_with_tools.invoke(messages)

        # Check if the model called the tool
        if response.tool_calls:
            tool_call = response.tool_calls[0]
            tool_args = tool_call["args"]

            # Execute the tool
            tool_result = fetch_challenge.invoke(tool_args)

            # Parse the tool result
            if tool_result.get("ok"):
                challenges = tool_result.get("challenges", [])
                challenge_detail = tool_result.get("challenge_detail", {})

                if challenge_detail:
                    challenge_text = _format_challenge(challenge_detail, language)
                    starter_code = challenge_detail.get("starter_code", {}).get(language, "")
                    challenge_title = challenge_detail.get("title", f"{topic}:{difficulty}")
                elif challenges:
                    ch = challenges[0]
                    challenge_text = f"## {ch['title']}\n\n{ch['snippet']}\n\nSource: {ch['url']}"
                    starter_code = ""
                    challenge_title = ch["title"]
                else:
                    challenge_text = f"Solve a {difficulty} {topic} problem."
                    starter_code = ""
                    challenge_title = f"{topic}:{difficulty}"

                trace = _trace_and_emit("setup", "host", "fetch_challenge",
                                        tool_args, {"ok": True, "source": "llm+tool"},
                                        session_id=session_id)
            else:
                # Tool returned error — fallback
                challenge_title = f"{topic}:{difficulty}"
                challenge_text = f"Solve a {difficulty} {topic} problem."
                starter_code = ""
                fallback_chat = [{'role': 'system',
                                  'content': f'Warning: Challenge fetch failed: {tool_result.get("error", "unknown")}',
                                  'ts': datetime.now(timezone.utc).isoformat()}]
                trace = _trace_and_emit("setup", "host", "fetch_challenge",
                                        tool_args, {"ok": False, "error": tool_result.get("error")},
                                        session_id=session_id)
        else:
            # 4d: Model didn't call the tool — use real fallback
            from app.tools.fetch_challenge import _fallback_challenge
            fb = _fallback_challenge(topic, difficulty, language)
            detail = fb.get("challenge_detail", {})
            challenge_text = _format_challenge(detail, language) if detail else f"Solve a {difficulty} {topic} problem."
            starter_code = detail.get("starter_code", {}).get(language, "") if detail else ""
            challenge_title = detail.get("title", f"{topic}:{difficulty}") if detail else f"{topic}:{difficulty}"
            fallback_chat = [{'role': 'system',
                              'content': 'Warning: Host could not fetch a challenge via tools; using a fallback problem.',
                              'ts': datetime.now(timezone.utc).isoformat()}]
            trace = _trace_and_emit("setup", "host", "fetch_challenge", {},
                                    {"ok": True, "source": "no_tool_call_fallback"},
                                    session_id=session_id)

    except Exception as e:
        logger.error(f"host_setup LLM error: {e}")
        # Fallback to hardcoded challenge
        from app.tools.fetch_challenge import _fallback_challenge
        fb = _fallback_challenge(topic, difficulty, language)
        detail = fb.get("challenge_detail", {})
        challenge_text = _format_challenge(detail, language) if detail else f"Solve a {difficulty} {topic} problem."
        starter_code = detail.get("starter_code", {}).get(language, "") if detail else ""
        challenge_title = detail.get("title", f"{topic}:{difficulty}") if detail else f"{topic}:{difficulty}"
        trace = _trace_and_emit("setup", "host", "fetch_challenge",
                                {}, {"ok": True, "source": "error_fallback"},
                                session_id=session_id)

    return {
        "phase": "host_present",
        "current_round": {
            "round_num": state["round_num"],
            "challenge": challenge_text,
            "original_code": "",
            "buggy_code": "",
            "fix_code": "",
            "bug_manifest": [],
            "test_cases": [],
            "original_exec": None,
            "buggy_exec": None,
            "fix_exec": None,
            "score": None,
            "difficulty_in": difficulty,
            "difficulty_out": difficulty,
        },
        "used_challenges": [*state.get("used_challenges", []), challenge_title],
        "trace": [trace],
        "chat": fallback_chat,
    }


def host_present(state: SessionState) -> dict:
    """Present challenge to student and pause for them to write original code.

    Sets phase to "student_writing" — the graph interrupts before saboteur_inject,
    waiting for the student to submit their code via the /write endpoint.
    """
    challenge = state.get("current_round", {}).get("challenge", "")
    return {
        "phase": "student_writing",
        "current_round": {
            **state["current_round"],
            "original_code_submitted": False,
        },
        "trace": [_trace_and_emit("host_present", "host", "present_challenge",
                                  {"challenge": challenge[:200]},
                                  session_id=state.get("session_id", "")),
                  _trace_and_emit("host_present", "host", "awaiting_student_code",
                                  {}, {"status": "waiting"},
                                  session_id=state.get("session_id", ""))],
    }


def saboteur_inject(state: SessionState) -> dict:
    """Saboteur analyzes code and injects bugs.

    Uses the inject_bugs tool (real @tool) to analyze the student's code
    and inject realistic bugs that test specific concepts.

    If original_code is empty (bypass scenario), returns to student_writing phase.
    """
    original_code = state.get("current_round", {}).get("original_code", "")
    submitted = state.get("current_round", {}).get("original_code_submitted", False)
    difficulty = state.get("difficulty", "easy")
    language = state.get("language", "python")
    session_id = state.get("session_id", "")

    # Guard: if no code submitted, keep graph paused at student_writing
    if not original_code or not submitted:
        return {
            "phase": "student_writing",
            "trace": [_trace_and_emit("sabotage", "saboteur", "inject_bugs",
                                      {"difficulty": difficulty},
                                      {"ok": True, "skipped": True, "reason": "waiting_for_code"},
                                      session_id=session_id)],
        }

    # Call the real inject_bugs tool
    from app.tools.inject_bugs import inject_bugs_tool

    try:
        result = inject_bugs_tool.invoke({
            "original_code": original_code,
            "difficulty": difficulty,
            "language": language,
        })

        if result.get("ok"):
            bugs = result.get("bug_manifest", [])
            test_cases = result.get("test_cases", [])

            trace = _trace_and_emit("sabotage", "saboteur", "inject_bugs",
                                    {"difficulty": difficulty, "language": language},
                                    {"ok": True, "bugs_count": len(bugs),
                                     "bug_types": [b.get("type") for b in bugs]},
                                    session_id=session_id)

            return {
                "phase": "student_fixing",
                "current_round": {
                    **state["current_round"],
                    "buggy_code": result.get("buggy_code", ""),
                    "bug_manifest": bugs,
                    "test_cases": test_cases,
                    "original_exec": result.get("original_exec"),
                    "buggy_exec": result.get("buggy_exec"),
                },
                "chat": [{"role": "saboteur",
                          "content": f"🪲 Injected {len(bugs)} bug(s). Try to find and fix them!",
                          "ts": datetime.now(timezone.utc).isoformat()}],
                "trace": [trace],
            }

        # Tool returned error — surface failure
        return {
            "phase": "student_writing",
            "current_round": {**state["current_round"], "buggy_code": "", "bug_manifest": [], "test_cases": []},
            "chat": [{'role': 'system',
                      'content': 'Warning: Saboteur failed to inject bugs. Please re-submit your code.',
                      'ts': datetime.now(timezone.utc).isoformat()}],
            "trace": [_trace_and_emit("sabotage", "saboteur", "inject_bugs",
                                      {"difficulty": difficulty},
                                      {"ok": False, "error": result.get("error", "unknown")},
                                      session_id=session_id)],
        }

    except Exception as e:
        logger.error(f"saboteur_inject error: {e}")
        return {
            "phase": "student_writing",
            "current_round": {**state["current_round"], "buggy_code": "", "bug_manifest": [], "test_cases": []},
            "chat": [{'role': 'system',
                      'content': 'Warning: Saboteur failed to inject bugs. Please re-submit your code.',
                      'ts': datetime.now(timezone.utc).isoformat()}],
            "trace": [_trace_and_emit("sabotage", "saboteur", "inject_bugs",
                                      {"difficulty": difficulty},
                                      {"ok": False, "error": str(e)},
                                      session_id=session_id)],
        }


def student_fix_await(state: SessionState) -> dict:
    """Graph pauses here — waiting for student to submit fix via WebSocket."""
    return {"phase": "student_fixing"}


def host_run_fix(state: SessionState) -> dict:
    """Run student's fix in sandbox and compare with buggy code.

    Uses the execute_code tool (real @tool) for sandbox execution.
    """
    language = state.get("language", "python")
    fix_code = state.get("current_round", {}).get("fix_code", "")
    buggy_code = state.get("current_round", {}).get("buggy_code", "")
    original_code = state.get("current_round", {}).get("original_code", "")
    session_id = state.get("session_id", "")

    if not fix_code:
        return {
            "phase": "evaluating",
            "trace": [_trace_and_emit("executing_fix", "host", "execute_code",
                                      {"language": language},
                                      {"ok": False, "error": "no_fix_code"},
                                      session_id=session_id)],
        }

    from app.tools.execute_code import execute_code_tool

    try:
        # Execute the student's fix
        fix_result = execute_code_tool.invoke({"code": fix_code, "language": language})
        fix_exec = {
            "stdout": fix_result.get("stdout", ""),
            "stderr": fix_result.get("stderr", ""),
            "exit_code": fix_result.get("exit_code", -1),
            "duration_ms": fix_result.get("duration_ms", 0),
            "sandbox": fix_result.get("sandbox", "unknown"),
        }

        # Also run original and buggy for comparison (if not already done)
        original_exec = state["current_round"].get("original_exec")
        buggy_exec = state["current_round"].get("buggy_exec")

        if not original_exec and original_code:
            orig_result = execute_code_tool.invoke({"code": original_code, "language": language})
            original_exec = {
                "stdout": orig_result.get("stdout", ""),
                "stderr": orig_result.get("stderr", ""),
                "exit_code": orig_result.get("exit_code", -1),
                "duration_ms": orig_result.get("duration_ms", 0),
                "sandbox": orig_result.get("sandbox", "unknown"),
            }

        if not buggy_exec and buggy_code:
            bug_result = execute_code_tool.invoke({"code": buggy_code, "language": language})
            buggy_exec = {
                "stdout": bug_result.get("stdout", ""),
                "stderr": bug_result.get("stderr", ""),
                "exit_code": bug_result.get("exit_code", -1),
                "duration_ms": bug_result.get("duration_ms", 0),
                "sandbox": bug_result.get("sandbox", "unknown"),
            }

        trace = _trace_and_emit("executing_fix", "host", "execute_code",
                                {"language": language, "code_length": len(fix_code)},
                                {"ok": fix_exec["exit_code"] == 0,
                                 "exit_code": fix_exec["exit_code"],
                                 "duration_ms": fix_exec["duration_ms"]},
                                session_id=session_id)

        return {
            "phase": "evaluating",
            "current_round": {
                **state["current_round"],
                "fix_exec": fix_exec,
                "original_exec": original_exec or state["current_round"].get("original_exec"),
                "buggy_exec": buggy_exec or state["current_round"].get("buggy_exec"),
            },
            "trace": [trace],
        }

    except Exception as e:
        logger.error(f"host_run_fix error: {e}")
        return {
            "phase": "evaluating",
            "trace": [_trace_and_emit("executing_fix", "host", "execute_code",
                                      {"language": language},
                                      {"ok": False, "error": str(e)},
                                      session_id=session_id)],
        }


def evaluator_score(state: SessionState) -> dict:
    """Evaluator diffs all three versions and scores the round.

    Uses the score_round tool (real @tool) and optionally run_tests tool
    to evaluate the student's fix.
    """
    current = state.get("current_round", {})
    original_code = current.get("original_code", "")
    buggy_code = current.get("buggy_code", "")
    fix_code = current.get("fix_code", "")
    bugs = current.get("bug_manifest", [])
    test_cases = current.get("test_cases", [])
    fix_exec = current.get("fix_exec", {})
    language = state.get("language", "python")
    session_id = state.get("session_id", "")

    from app.tools.score_round import score_round_tool

    try:
        # Score the round using the real tool
        score_result = score_round_tool.invoke({
            "original_code": original_code,
            "buggy_code": buggy_code,
            "fix_code": fix_code,
            "bug_manifest": bugs,
            "fix_exec": fix_exec or {},
            "language": language,
        })

        if score_result.get("ok"):
            score = score_result.get("score", {})
            feedback = score_result.get("feedback", "")
            remaining = score_result.get("remaining_bugs", [])
            new_issues = score_result.get("new_issues", [])

            # Run test cases if available
            test_summary = ""
            if test_cases and fix_code:
                try:
                    from app.tools.run_tests import run_tests_tool
                    test_result = run_tests_tool.invoke({
                        "code": fix_code,
                        "test_cases": test_cases,
                        "language": language,
                    })
                    pass_count = test_result.get("pass_count", 0)
                    total = test_result.get("total", len(test_cases))
                    test_summary = f"\n\n🧪 Tests: {pass_count}/{total} passed"
                except Exception as te:
                    logger.warning(f"run_tests error: {te}")

            # Add feedback to chat
            chat_msg = {
                "role": "evaluator",
                "content": f"📊 Score: {score.get('total', 0)}/100\n\n{feedback}{test_summary}",
                "ts": datetime.now(timezone.utc).isoformat(),
            }
            if remaining:
                chat_msg["content"] += f"\n\nRemaining bugs: {', '.join(remaining)}"
            if new_issues:
                chat_msg["content"] += f"\n\nNew issues: {', '.join(new_issues)}"

            trace = _trace_and_emit("evaluating", "evaluator", "score_round",
                                    {"bugs_total": len(bugs)},
                                    {"ok": True, "score": score},
                                    session_id=session_id)

            return {
                "phase": "round_complete",
                "current_round": {
                    **current,
                    "score": score,
                },
                "chat": [chat_msg],
                "trace": [trace],
            }

        # Tool returned error — use fallback scoring
        logger.warning(f"score_round_tool returned error: {score_result.get('error')}")
        return {
            "phase": "round_complete",
            "current_round": {
                **current,
                "score": {
                    "bugs_fixed": 0,
                    "bugs_total": len(bugs),
                    "code_quality": 0.0,
                    "speed_bonus": 0.0,
                    "total": 0,
                },
            },
            "chat": [{'role': 'system',
                      'content': 'Warning: Evaluator failed to score; round scored 0.',
                      'ts': datetime.now(timezone.utc).isoformat()}],
            "trace": [_trace_and_emit("evaluating", "evaluator", "score_round",
                                      {}, {"ok": False, "error": score_result.get("error", "unknown")},
                                      session_id=session_id)],
        }

    except Exception as e:
        logger.error(f"evaluator_score error: {e}")
        return {
            "phase": "round_complete",
            "current_round": {
                **current,
                "score": {
                    "bugs_fixed": 0,
                    "bugs_total": len(bugs),
                    "code_quality": 0.0,
                    "speed_bonus": 0.0,
                    "total": 0,
                },
            },
            "chat": [{'role': 'system',
                      'content': 'Warning: Evaluator failed to score; round scored 0.',
                      'ts': datetime.now(timezone.utc).isoformat()}],
            "trace": [_trace_and_emit("evaluating", "evaluator", "score_round",
                                      {}, {"ok": False, "error": str(e)},
                                      session_id=session_id)],
        }


def adjust(state: SessionState) -> dict:
    """Adjust difficulty based on performance and increment round."""
    next_round = state["round_num"] + 1
    current_score = state.get("current_round", {}).get("score", {})
    total = current_score.get("total", 0) if current_score else 0

    # Adjust difficulty based on score
    difficulty = state.get("difficulty", "easy")
    if total >= 80 and difficulty == "easy":
        difficulty = "medium"
    elif total >= 80 and difficulty == "medium":
        difficulty = "hard"
    elif total < 40 and difficulty == "medium":
        difficulty = "easy"
    elif total < 40 and difficulty == "hard":
        difficulty = "medium"

    # Archive current round to history
    current_round = state.get("current_round", {})

    return {
        "round_num": next_round,
        "difficulty": difficulty,
        "phase": "round_complete",  # Will be overridden to 'done' by graph termination
        "rounds": [current_round],
        "chat": [{"role": "host",
                  "content": f"Round {next_round + 1} starting! Difficulty: {difficulty}",
                  "ts": datetime.now(timezone.utc).isoformat()}],
        "trace": [_trace_and_emit("adjust", "evaluator", "adjust_difficulty",
                                  {"round": next_round, "score": total},
                                  {"ok": True, "difficulty": difficulty},
                                  session_id=state.get("session_id", ""))],
    }


# --- Helper functions ---


def _format_challenge(detail: dict, language: str) -> str:
    """Format a challenge detail dict into a readable string."""
    title = detail.get("title", "Coding Challenge")
    description = detail.get("description", "")
    starter = detail.get("starter_code", {}).get(language, "")
    tests = detail.get("test_cases", [])
    constraints = detail.get("constraints", "")

    parts = [f"## {title}\n\n{description}"]

    if starter:
        parts.append(f"\n### Starter Code\n```{language}\n{starter}\n```")

    if tests:
        parts.append("\n### Test Cases")
        for t in tests:
            parts.append(f"- Input: `{t.get('input', '')}` → Expected: `{t.get('expected', '')}`")

    if constraints:
        parts.append(f"\n### Constraints\n{constraints}")

    return "\n".join(parts)


def finish(state: SessionState) -> dict:
    """Terminal node — marks the session complete and archives the final round."""
    rounds = state.get('rounds', [])
    current_round = state.get('current_round', {})
    has_current_score = bool(current_round.get('score'))
    all_rounds = rounds + ([current_round] if has_current_score else [])
    total = sum((r.get('score') or {}).get('total', 0) for r in all_rounds)
    return {
        'phase': 'done',
        # Archive the final round into rounds[] (adjust never runs when
        # round_or_done → "done", so current_round is otherwise lost and the
        # PDF report would render "No rounds completed"). The `rounds` field
        # uses the `add` reducer, so we return only the not-yet-archived final
        # round — returning all_rounds would double-count prior rounds.
        'rounds': [current_round] if has_current_score else [],
        'chat': [{
            'role': 'host',
            'content': f'Session complete! You finished {len(all_rounds)} round(s). Total score: {total}.',
            'ts': datetime.now(timezone.utc).isoformat(),
        }],
        'trace': [_trace_and_emit('done', 'host', 'finish',
                                   {'rounds': len(all_rounds)}, {'ok': True, 'total': total},
                                   session_id=state.get('session_id', ''))],
    }


