# AgentX Comprehensive Execution Plan

**Date:** 2026-06-29
**Scope:** Every identified issue from P0 through P3 — file-level, function-level, dependency-ordered.

---

## Table of Contents
- [P0 — Blocks Honest Demo](#p0--blocks-honest-demo)
- [P1 — Correctness & Safety](#p1--correctness--safety)
- [P2 — Completeness vs Plan](#p2--completeness-vs-plan)
- [P3 — Testing & Hardening](#p3--testing--hardening)

---

# P0 — Blocks Honest Demo

These issues make the demo fundamentally dishonest about what the product does. Fix first.

---

## Fix 1: Write Phase Missing — Students Never Author Original Code

**Problem:** The graph flow is `host_setup → host_present → saboteur_inject → student_fix_await`. The `host_present` node just sets `phase: "host_present"` and returns — it never pauses to let the student *write* original code. The starter code comes from the challenge's `starter_code` dict, and the saboteur immediately injects bugs into it. The student never experiences the "Write" half of "Write → Sabotage → Fix."

### Files to Modify

#### 1a. `agentx/backend/app/graph/state.py`
**Add** a new `RoundPhase` literal and a state field to hold the student's original submission.

```python
RoundPhase = Literal[
    "setup",
    "student_writing",     # NEW — waiting for student to write original code
    "host_present",        # renamed from old flow; now means "challenge presented"
    "sabotage",
    "executing_original",
    "executing_buggy",
    "student_fixing",
    "executing_fix",
    "evaluating",
    "round_complete",
    "done",
]
```

Add to `SessionState`:
```python
class SessionState(TypedDict):
    # ... existing fields ...
    original_code_submitted: bool  # NEW — gates whether saboteur can proceed
```

#### 1b. `agentx/backend/app/graph/builder.py`
**Change** the flow so `host_present` pauses (interrupt) before advancing to `saboteur_inject`. The student writes code during this pause.

New flow:
```
host_setup → host_present → [INTERRUPT: student_writes_code] → saboteur_inject → student_fix_await → host_run_fix → evaluator_score → adjust / END
```

Specific edits:
- Add `saboteur_inject` node's edge should come from `host_present` (already does), but `host_present` should set `phase: "student_writing"` and the graph should interrupt *after* `host_present` (i.e., `interrupt_before=["saboteur_inject"]`).
- Replace `interrupt_before=["student_fix_await"]` with `interrupt_before=["saboteur_inject", "student_fix_await"]`.

```python
def build_graph():
    g = StateGraph(SessionState)
    g.add_node("host_setup", nodes.host_setup)
    g.add_node("host_present", nodes.host_present)
    g.add_node("saboteur_inject", nodes.saboteur_inject)
    g.add_node("student_fix_await", nodes.student_fix_await)
    g.add_node("host_run_fix", nodes.host_run_fix)
    g.add_node("evaluator_score", nodes.evaluator_score)
    g.add_node("adjust", nodes.adjust)

    g.set_entry_point("host_setup")
    g.add_edge("host_setup", "host_present")
    g.add_edge("host_present", "saboteur_inject")
    g.add_edge("saboteur_inject", "student_fix_await")
    g.add_edge("student_fix_await", "host_run_fix")
    g.add_conditional_edges(
        "evaluator_score",
        edges.round_or_done,
        {"adjust": "adjust", "done": END},
    )
    g.add_edge("adjust", "host_setup")

    return g.compile(
        interrupt_before=["saboteur_inject", "student_fix_await"],
        checkpointer=MemorySaver(),
    )
```

#### 1c. `agentx/backend/app/graph/nodes.py`

**Modify `host_present`:**
- Set `phase: "student_writing"` (not `"host_present"`).
- Include `original_code_submitted: False` in the state.

```python
def host_present(state: SessionState) -> dict:
    return {
        "phase": "student_writing",
        "current_round": {
            **state["current_round"],
            "original_code_submitted": False,
        },
    }
```

**Modify `saboteur_inject`:**
- Before doing anything, verify that `original_code_submitted` is `True` and `original_code` is non-empty. If not, return `phase: "student_writing"` to keep the graph paused (edge case: direct invocation bypass).

#### 1d. `agentx/backend/app/api/routes.py`

**Modify `create_session`:**
- After the initial `graph.invoke()`, the graph will be paused at `interrupt_before=["saboteur_inject"]`.
- The returned state will have `phase: "student_writing"` and the `current_round.original_code` will be the challenge description (not starter code).
- Store as before.

**Add new endpoint** `POST /api/sessions/{session_id}/write`:
```python
class OriginalCodeSubmit(BaseModel):
    original_code: str

@router.post("/api/sessions/{session_id}/write")
def submit_original_code(session_id: str, req: OriginalCodeSubmit):
    """Submit student's original code, then resume graph past saboteur_inject interrupt."""
    if session_id not in _sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    if not req.original_code.strip():
        raise HTTPException(status_code=400, detail="original_code cannot be empty")

    session = _sessions[session_id]
    graph = get_graph()
    config = session["config"]

    current_round = session["state"].get("current_round", {})
    graph.update_state(config, {
        "current_round": {
            **current_round,
            "original_code": req.original_code,
            "original_code_submitted": True,
        }
    })

    # Resume graph — runs saboteur_inject, then interrupts before student_fix_await
    result = graph.invoke(None, config)
    session["state"] = result

    rounds = result.get("rounds", [])
    score = rounds[-1].get("score") if rounds else result.get("current_round", {}).get("score")

    return {
        "session_id": session_id,
        "phase": result.get("phase"),
        "score": score,
        "chat": result.get("chat", []),
        "trace": result.get("trace", []),
        "round_num": result.get("round_num"),
        "difficulty": result.get("difficulty"),
        "challenge": result.get("current_round", {}).get("challenge", ""),
        "original_code": result.get("current_round", {}).get("original_code", ""),
        "buggy_code": result.get("current_round", {}).get("buggy_code", ""),
    }
```

#### 1e. `agentx/frontend/app/lib/types.ts`

Add to `CreateSessionResponse`:
```typescript
export interface CreateSessionResponse {
  session_id: string;
  phase: RoundPhase;
  challenge: string;
  original_code: string;  // This is now the CHALLENGE text, not code
  buggy_code: string;
  chat: ChatMessage[];
  trace: TraceEvent[];
}
```

Add new types:
```typescript
export interface WriteOriginalRequest {
  original_code: string;
}
export interface WriteOriginalResponse {
  session_id: string;
  phase: RoundPhase;
  score: RoundScore | null;
  chat: ChatMessage[];
  trace: TraceEvent[];
  round_num: number;
  difficulty: string;
  challenge: string;
  original_code: string;
  buggy_code: string;
}
```

Update `RoundPhase` to include `"student_writing"`.

#### 1f. `agentx/frontend/app/lib/api.ts`

Add:
```typescript
export function submitOriginalCode(
  sessionId: string,
  req: WriteOriginalRequest,
): Promise<WriteOriginalResponse> {
  return apiFetch<WriteOriginalResponse>(`/api/sessions/${sessionId}/write`, {
    method: "POST",
    body: JSON.stringify(req),
  });
}
```

#### 1g. `agentx/frontend/app/stores/session.ts`

Add to `SessionStore`:
```typescript
interface SessionStore {
  // ... existing ...
  language: string;       // NEW — needed for API calls
  topic: string;          // NEW — needed for API calls
  // ...
  setLanguage: (lang: string) => void;
  setTopic: (topic: string) => void;
}
```

#### 1h. `agentx/frontend/app/components/CodeEditor.tsx`

**Update `PHASE_EDITABLE`:**
```typescript
const PHASE_EDITABLE: Record<string, true> = {
  student_writing: true,   // NEW
  student_fixing: true,
};
```

**Update code display logic:**
- When `phase === "student_writing"`, show a blank editor with a comment `# Write your solution here...` (no starter code — the student writes from scratch, or can look at the challenge).
- When `phase === "host_present"` (which shouldn't normally be visible, but guard), show the challenge.

#### 1i. `agentx/frontend/app/pages/SessionPage.tsx`

**Update `handleSubmitFix` flow:**
- Add a `handleSubmitOriginalCode` function that calls `submitOriginalCode`.
- During `student_writing` phase, the "Submit Code" button calls `handleSubmitOriginalCode`.
- The fix submission button only appears during `student_fixing`.

**Update `useEffect` init:**
- Pass `language`, `topic`, `difficulty` from user selections (see Fix 12) into the `createSession` call.

**Update `handleWSMessage`:**
- Handle `"write_complete"` message type that the backend sends after original code submission.

#### 1j. `agentx/frontend/app/pages/HomePage.tsx`

**Add language/topic/difficulty pickers** (this also addresses Fix 12 — see P2):
- Three dropdowns: Language (Python/JavaScript), Topic (Arrays, Strings, Trees), Difficulty (Easy, Medium, Hard).
- Pass selections up via props to `App.tsx`, which passes them to `SessionPage`.

**Specific UI:**
```tsx
interface HomePageProps {
  onStart: (config: { language: string; topic: string; difficulty: string }) => void;
}
```

#### 1k. `agentx/frontend/app/App.tsx`

Store user config in state:
```tsx
const [sessionConfig, setSessionConfig] = useState({ language: "python", topic: "arrays", difficulty: "easy" });
const startSession = (config) => { setSessionConfig(config); setSessionId("new"); setPage("session"); };
```

Pass config to `SessionPage`.

### Edge Cases & Gotchas
- **LLM might inject bugs into the starter code instead of the student's code.** The `saboteur_inject` node must use `current_round.original_code` (the student's submission), not the challenge's `starter_code`.
- **Student submits empty/whitespace code.** The `/write` endpoint validates non-empty; also the edge function `has_fix_submitted` already handles this for the fix phase.
- **Interrupt resumption idempotency.** If the graph is already past the `saboteur_inject` interrupt, calling `graph.invoke(None, config)` should not re-run `saboteur_inject`. LangGraph's checkpointer handles this — but test it.

### Dependencies
- Fix 1 is the root dependency for the honest demo. Fixes 3 (real tools), 4 (TracePanel args/results), and 12 (pickers) build on top of it.
- Fix 5 (off-by-one) must be done alongside or before Fix 1 because the round counter logic is intertwined.

---

## Fix 2: WebSocket Dead — No Live Trace Streaming

**Problem:** The WebSocket at `/ws/{session_id}` in `routes.py` (lines 182-203) only accepts ping/pong. It never pushes graph events to the frontend. The frontend `useWebSocket` hook connects but never receives real-time updates — all data flows through the synchronous HTTP response of `submit_fix` / `submit_original_code`.

### Files to Modify

#### 2a. `agentx/backend/app/api/routes.py`

**Add an `asyncio.Queue` per session** to buffer events during graph execution:

```python
from collections import defaultdict
import asyncio

_session_queues: dict[str, asyncio.Queue] = defaultdict(asyncio.Queue)
```

**Add an event emitter callback** that nodes call during graph execution:

```python
def _emit_event(session_id: str, event: dict):
    """Thread-safe event emission to the WebSocket queue."""
    if session_id in _session_queues:
        try:
            _session_queues[session_id].put_nowait(event)
        except asyncio.QueueFull:
            pass  # Drop oldest if full
```

**Modify `create_session` and `submit_fix` / `submit_original_code`:**
- Store `session_id` in a module-level variable or pass it through state so nodes can emit events.
- After each graph step, emit a `{"type": "state", "phase": ..., "trace": ...}` message.
- On graph completion, emit `{"type": "result", ...}`.

Specifically, wrap the `graph.invoke()` calls:
```python
async def _run_graph_and_emit(session_id: str, graph, config, initial_state=None):
    """Run graph, emitting events to the session queue after each step."""
    if initial_state:
        result = graph.invoke(initial_state, config)
    else:
        result = graph.invoke(None, config)
    
    # Emit final state
    queue = _session_queues.get(session_id)
    if queue:
        await queue.put({
            "type": "result",
            "phase": result.get("phase"),
            "score": _extract_score(result),
            "round_num": result.get("round_num"),
            "difficulty": result.get("difficulty"),
            "challenge": result.get("current_round", {}).get("challenge", ""),
            "original_code": result.get("current_round", {}).get("original_code", ""),
            "buggy_code": result.get("current_round", {}).get("buggy_code", ""),
            "chat": result.get("chat", []),
            "trace": result.get("trace", []),
        })
    return result
```

**Rewrite the WebSocket handler** to actually push events:

```python
@router.websocket("/ws/{session_id}")
async def websocket_session(websocket: WebSocket, session_id: str):
    await websocket.accept()

    if session_id not in _sessions:
        await websocket.send_json({"type": "error", "message": "Session not found"})
        await websocket.close()
        return

    queue = _session_queues[session_id]

    try:
        # Send current state immediately
        session = _sessions[session_id]
        state = session["state"]
        await websocket.send_json({
            "type": "state",
            "phase": state.get("phase"),
            "round_num": state.get("round_num"),
        })

        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=30)
                await websocket.send_json(event)
                # If this is a terminal event (result/error), break
                if event.get("type") in ("result", "error"):
                    break
            except asyncio.TimeoutError:
                # Send keepalive
                await websocket.send_json({"type": "ping"})
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected: {session_id}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        # Clean up queue
        _session_queues.pop(session_id, None)
```

**Key design:** The HTTP endpoints (`/api/sessions`, `/api/sessions/{id}/fix`, `/api/sessions/{id}/write`) remain synchronous and return the full result. The WebSocket pushes incremental updates. The frontend uses both: HTTP for mutations, WS for real-time phase updates and trace streaming.

#### 2b. `agentx/backend/app/graph/nodes.py`

**Add session_id to trace events.** Every call to `_trace_event` already includes agent/phase/tool/args/result/timestamp. No change needed for the trace structure itself — the queue-based emission from routes.py handles the transport.

However, for the WS to stream intermediate events (not just the final state), add a **callback mechanism**:

```python
# In nodes.py, module-level
_emit_callback = None  # Set by routes.py before graph.invoke()

def set_emit_callback(callback):
    global _emit_callback
    _emit_callback = callback

def _trace_and_emit(phase, agent, tool=None, args=None, result=None):
    """Build trace event and emit it via callback."""
    event = _trace_event(phase, agent, tool, args, result)
    if _emit_callback:
        _emit_callback(event)
    return event
```

Replace all `_trace_event(...)` calls in nodes with `_trace_and_emit(...)`. This ensures every trace event is emitted in real-time, not batched.

#### 2c. `agentx/frontend/app/hooks/useWebSocket.ts`

**Add reconnection logic:**
```typescript
const RECONNECT_DELAY = 2000;
const MAX_RECONNECT = 5;
let reconnectCount = 0;

// In useEffect:
ws.onclose = () => {
  setConnected(false);
  if (reconnectCount < MAX_RECONNECT) {
    setTimeout(() => {
      reconnectCount++;
      // Recreate ws connection
    }, RECONNECT_DELAY);
  }
};
```

**Add keepalive pong handling:**
```typescript
ws.onmessage = (event) => {
  const msg = JSON.parse(event.data);
  if (msg.type === "ping") {
    ws.send(JSON.stringify({ action: "pong" }));
    return;
  }
  setLastMessage(msg);
  onMessageRef.current?.(msg);
};
```

#### 2d. `agentx/frontend/app/pages/SessionPage.tsx`

Update `handleWSMessage` to also handle `"state"` type messages (which carry intermediate phase updates without full data):

```typescript
(msg: WSMessage) => {
  if (msg.type === "result") {
    // Full state update (after graph completes a step)
    updateFromResult({ ... });
  } else if (msg.type === "phase") {
    setPhase(msg.phase as RoundPhase);
  } else if (msg.type === "state") {
    // Incremental: just phase update
    setPhase(msg.phase as RoundPhase);
  } else if (msg.type === "trace_event") {
    // Real-time trace event
    addTraceEvent(msg as TraceEvent);
  }
}
```

### Edge Cases & Gotchas
- **Thread safety:** `graph.invoke()` runs synchronously in a sync endpoint, but `asyncio.Queue.put_nowait()` is thread-safe in Python's asyncio when called from a sync context within the event loop. However, since `create_session` is a sync `def` (not `async def`), the queue put must happen in the sync handler. Use a `janus` queue or `asyncio.run_coroutine_threadsafe` if needed, or switch to a thread-safe `queue.Queue` for the buffer.
- **Queue cleanup:** If the WS disconnects before the graph finishes, the queue must be drained to prevent memory leaks.
- **Backpressure:** If the consumer (WS) is slow, the queue fills up. Set `maxsize=100` and drop oldest.

### Dependencies
- Fix 2 depends on Fix 1 (the new `/write` endpoint must also emit events).
- Fix 2 is independent of Fixes 3-4 but should ship together for a coherent demo.

---

## Fix 3: 7 of 8 Tools Not Real — Synthetic Trace Events

**Problem:** Only `fetch_challenge` is a real `@tool`. The trace events for `inject_bugs`, `execute_code`, `score_round`, `adjust_difficulty` are synthetic strings built by `_trace_event()`. They look like tool calls in the TracePanel but never go through LangChain's tool binding.

### Files to Modify

#### 3a. `agentx/backend/app/tools/__init__.py`

**Register all real tools:**

```python
from collections.abc import Callable
from app.tools.fetch_challenge import fetch_challenge
from app.tools.inject_bugs import inject_bugs_tool
from app.tools.execute_code import execute_code_tool
from app.tools.score_round import score_round_tool
from app.tools.run_tests import run_tests_tool  # Fix 8

TOOL_REGISTRY: dict[str, Callable] = {
    "fetch_challenge": fetch_challenge,
    "inject_bugs": inject_bugs_tool,
    "execute_code": execute_code_tool,
    "score_round": score_round_tool,
    "run_tests": run_tests_tool,
}

def get_tool(name: str):
    return TOOL_REGISTRY.get(name)

def get_all_tools():
    return list(TOOL_REGISTRY.values())
```

#### 3b. `agentx/backend/app/tools/inject_bugs.py` (NEW FILE)

```python
"""Tool: inject bugs into student code via Saboteur LLM analysis."""

import logging
from langchain_core.tools import tool
from app.utils import parse_json_response, difficulty_to_num_bugs, apply_bugs, validate_compiles

logger = logging.getLogger(__name__)

@tool
def inject_bugs(original_code: str, difficulty: str, language: str) -> dict:
    """Analyze student code and inject realistic bugs.

    Args:
        original_code: The student's original code.
        difficulty: Difficulty level (easy, medium, hard).
        language: Programming language (python, javascript).

    Returns:
        Dict with buggy_code, bug_manifest, original_exec, buggy_exec.
    """
    from app.agents.base import make_llm
    from app.prompts.saboteur import SABOTEUR_SYSTEM_PROMPT
    from langchain_core.messages import SystemMessage, HumanMessage
    from app.sandbox.manager import get_sandbox

    llm = make_llm("saboteur", temperature=0.7)
    num_bugs = difficulty_to_num_bugs(difficulty)

    messages = [
        SystemMessage(content=SABOTEUR_SYSTEM_PROMPT),
        HumanMessage(content=f"""Analyze this {language} code and inject {difficulty}-level bugs.

```{language}
{original_code}
```

Inject {num_bugs} realistic bugs. Each bug must be a different type.
The code MUST still compile. Provide test cases that expose each bug.

Respond with ONLY valid JSON."""),
    ]

    response = llm.invoke(messages)
    parsed = parse_json_response(response.content)

    if not parsed or "bugs" not in parsed:
        return {"ok": False, "error": "Failed to parse bug injection response"}

    bugs = parsed["bugs"]
    test_cases = parsed.get("test_cases", [])
    buggy_code = apply_bugs(original_code, bugs)

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
```

#### 3c. `agentx/backend/app/tools/execute_code.py` (NEW FILE)

```python
"""Tool: execute code in the Docker sandbox."""

import logging
from langchain_core.tools import tool

logger = logging.getLogger(__name__)

@tool
def execute_code(code: str, language: str) -> dict:
    """Execute code in an isolated sandbox and return results.

    Args:
        code: The code to execute.
        language: Programming language (python, javascript).

    Returns:
        Dict with stdout, stderr, exit_code, duration_ms, sandbox.
    """
    from app.sandbox.manager import get_sandbox
    sandbox = get_sandbox()
    result = sandbox.run(code, language)
    return {"ok": result["exit_code"] == 0, **result}
```

#### 3d. `agentx/backend/app/tools/score_round.py` (NEW FILE)

```python
"""Tool: evaluate and score a student's fix."""

import logging
from langchain_core.tools import tool

logger = logging.getLogger(__name__)

@tool
def score_round(
    original_code: str,
    buggy_code: str,
    fix_code: str,
    bug_manifest: list[dict],
    fix_exec: dict,
    language: str,
) -> dict:
    """Compare original, buggy, and fixed code to score the student's fix.

    Args:
        original_code: The student's original code.
        buggy_code: The code after sabotage.
        fix_code: The student's fix attempt.
        bug_manifest: List of injected bugs.
        fix_exec: Execution result of the fix.
        language: Programming language.

    Returns:
        Dict with score breakdown and feedback.
    """
    from app.agents.base import make_llm
    from app.prompts.evaluator import EVALUATOR_SYSTEM_PROMPT
    from langchain_core.messages import SystemMessage, HumanMessage
    from app.utils import parse_json_response

    llm = make_llm("evaluator", temperature=0.2)

    bugs_summary = "\n".join([
        f"- Line {b.get('line')}: {b.get('type')} — {b.get('description')}"
        for b in bug_manifest
    ]) or "No bugs were injected."

    prompt = f"""Evaluate the student's fix:

## Original Code ({language}):
```{language}
{original_code}
```

## Buggy Code:
```{language}
{buggy_code}
```

## Student's Fix:
```{language}
{fix_code}
```

## Injected Bugs:
{bugs_summary}

## Execution Results:
- Fix exit code: {fix_exec.get('exit_code', 'N/A')}
- Fix output: {fix_exec.get('stdout', '')[:200]}

Score (0-100): Bugs Fixed (40), Code Quality (30), Correctness (20), Speed Bonus (10).
Respond with ONLY valid JSON."""

    messages = [
        SystemMessage(content=EVALUATOR_SYSTEM_PROMPT),
        HumanMessage(content=prompt),
    ]

    response = llm.invoke(messages)
    parsed = parse_json_response(response.content)

    if not parsed:
        return {"ok": False, "error": "Failed to parse evaluation"}

    return {
        "ok": True,
        "score": {
            "bugs_fixed": parsed.get("bugs_fixed", 0),
            "bugs_total": parsed.get("bugs_total", len(bug_manifest)),
            "code_quality": parsed.get("code_quality", 0.0),
            "speed_bonus": parsed.get("speed_bonus", 0.0),
            "total": parsed.get("total", 0),
        },
        "feedback": parsed.get("feedback", ""),
        "remaining_bugs": parsed.get("remaining_bugs", []),
        "new_issues": parsed.get("new_issues", []),
    }
```

#### 3e. `agentx/backend/app/graph/nodes.py`

**Refactor `saboteur_inject`** to use the `inject_bugs` tool:
```python
def saboteur_inject(state: SessionState) -> dict:
    from app.tools.inject_bugs import inject_bugs_tool
    # ... validation ...
    result = inject_bugs_tool.invoke({
        "original_code": original_code,
        "difficulty": difficulty,
        "language": language,
    })
    # Build state update from result
```

**Refactor `host_run_fix`** to use `execute_code` tool.

**Refactor `evaluator_score`** to use `score_round` tool.

Each node still wraps the tool call and builds state updates, but the trace events are now emitted by the tools themselves (real `@tool` invocations show up in LangChain's callback system).

#### 3f. `agentx/backend/app/agents/base.py`

**Add `@lru_cache` to `make_llm`:**
```python
from functools import lru_cache

@lru_cache(maxsize=8)
def make_llm(model_key: str, *, temperature: float | None = None, max_tokens: int | None = None) -> ChatOpenAI:
    # ... same implementation ...
```

Note: `lru_cache` doesn't work with `**kwargs` directly. Use a frozen dataclass or a custom cache key:
```python
_llm_cache: dict[str, ChatOpenAI] = {}

def make_llm(model_key: str, *, temperature: float | None = None, max_tokens: int | None = None) -> ChatOpenAI:
    cache_key = f"{model_key}:{temperature}:{max_tokens}"
    if cache_key not in _llm_cache:
        # ... create ChatOpenAI ...
        _llm_cache[cache_key] = llm
    return _llm_cache[cache_key]
```

### Edge Cases & Gotchas
- **Tool calls in LangChain:** When tools are bound to an LLM, the LLM decides whether to call them. In the current architecture, the *nodes* decide what to do — the LLM just generates bug analysis. Using `@tool` makes the functions available for tracing but the nodes still call them directly via `.invoke()`. This is the correct pattern for this architecture.
- **Tool argument validation:** LangChain `@tool` validates argument types. The `bug_manifest` argument is `list[dict]` — LangChain handles this, but ensure the LLM response parses correctly.
- **Circular imports:** `inject_bugs.py` imports from `agents.base` and `sandbox.manager`. These import chains must not circle back to `tools/__init__.py`. Currently they don't — verify after implementation.

### Dependencies
- Fix 3 depends on Fix 1 (saboteur flow is restructured).
- Fix 3 is prerequisite for Fix 4 (TracePanel showing args/results) because real tool invocations produce structured trace data.

---

## Fix 4: TracePanel Doesn't Show Args/Result

**Problem:** `TracePanel.tsx` displays `event.agent`, `event.phase`, `event.tool`, and a ✓/✗ from `event.result?.ok`. It never shows `event.args` or `event.result` details. Judges can't verify what tools did.

### Files to Modify

#### 4a. `agentx/frontend/app/components/TracePanel.tsx`

**Redesign `TraceRow`** to be expandable:

```tsx
import { useState } from "react";

function TraceRow({ event }: { event: TraceEvent }) {
  const [expanded, setExpanded] = useState(false);
  const color = agentColors[event.agent] ?? "text-zinc-400";
  const icon = agentIcons[event.agent] ?? "⚡";
  const tool = event.tool ? ` → ${event.tool}` : "";
  const resultOk = event.result?.ok;

  return (
    <div className="rounded px-2 py-1 hover:bg-zinc-800/50">
      <div
        className="flex cursor-pointer items-start gap-2 text-xs"
        onClick={() => setExpanded(!expanded)}
      >
        <span className="shrink-0">{icon}</span>
        <span className={`shrink-0 font-mono ${color}`}>{event.agent}</span>
        <span className="shrink-0 text-zinc-600">{event.phase}</span>
        <span className="shrink-0 text-zinc-500">{tool}</span>
        {resultOk !== undefined && (
          <span className={resultOk ? "text-green-500" : "text-red-500"}>
            {resultOk ? "✓" : "✗"}
          </span>
        )}
        <span className="ml-auto shrink-0 text-zinc-700">
          {new Date(event.ts).toLocaleTimeString()}
        </span>
        <span className="shrink-0 text-zinc-600">{expanded ? "▼" : "▶"}</span>
      </div>

      {expanded && (
        <div className="mt-2 space-y-2 pl-6 text-xs">
          {Object.keys(event.args).length > 0 && (
            <div>
              <div className="mb-1 font-semibold text-zinc-400">Arguments</div>
              <pre className="overflow-x-auto rounded bg-zinc-950 p-2 text-zinc-300">
                {JSON.stringify(event.args, null, 2)}
              </pre>
            </div>
          )}
          {event.result && (
            <div>
              <div className="mb-1 font-semibold text-zinc-400">Result</div>
              <pre className="overflow-x-auto rounded bg-zinc-950 p-2 text-zinc-300">
                {JSON.stringify(event.result, null, 2)}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
```

#### 4b. `agentx/frontend/app/lib/types.ts`

Ensure `TraceEvent` has `args: Record<string, unknown>` and `result: Record<string, unknown> | null` — this already exists (lines 33-40). No change needed.

### Edge Cases & Gotchas
- **Large payloads:** `args` and `result` can be large (e.g., full code strings). Truncate display to first 500 chars with a "show more" toggle.
- **Null args:** The `_trace_event` helper defaults to `{}`, so `Object.keys(event.args).length > 0` guard is correct.

### Dependencies
- Fix 4 requires Fix 3 (real tools produce meaningful args/result).
- Fix 2 (WebSocket) streams these events in real-time.

---

# P1 — Correctness & Safety

---

## Fix 5: Off-By-One Round Counter

**Problem:** `adjust()` increments `round_num` and the condition in `round_or_done` checks `state["round_num"] >= state["max_rounds"]`. With `max_rounds=3`:
- Round 0 → adjust → round_num becomes 1
- Round 1 → adjust → round_num becomes 2
- Round 2 → adjust → round_num becomes 3
- Now `3 >= 3` → done.

That's rounds 0, 1, 2 = 3 rounds. Correct! BUT `adjust()` returns `phase: "host_present"`, which means after round 2's adjust, the graph loops back to `host_setup → host_present → [interrupt]`. The interrupt means the session pauses at `host_present` with `phase: "student_writing"` before `saboteur_inject`. So the student sees "Round 3 starting!" but the graph has already decided to go to adjust→host_setup.

Wait — actually, let me re-read the edge:

```python
def round_or_done(state: SessionState) -> str:
    if state.get("round_num", 0) >= state.get("max_rounds", 3):
        return "done"
    return "adjust"
```

And `adjust()` sets `"round_num": next_round` where `next_round = state["round_num"] + 1`.

The issue is that `round_or_done` is called AFTER `evaluator_score`. At that point `round_num` hasn't been incremented yet (adjust hasn't run). So:
- Initial: round_num=0, max_rounds=3
- After eval: round_or_done checks `0 >= 3` → False → adjust → round_num=1
- After eval: round_or_done checks `1 >= 3` → False → adjust → round_num=2
- After eval: round_or_done checks `2 >= 3` → False → adjust → round_num=3
- `adjust` runs, sets round_num=3, returns phase="host_present"
- Graph loops: host_setup → host_present → [interrupt]
- Student writes code, submits
- saboteur_inject → student_fix_await → host_run_fix → evaluator_score
- round_or_done checks `3 >= 3` → True → done

So actually it runs 4 rounds (0,1,2,3), not 3! The issue is that `adjust` increments round_num AND returns `phase: "host_present"` which causes another round to start, but `round_or_done` doesn't check until after the next round completes.

**The fix:** `round_or_done` should check `state["round_num"] + 1 >= state["max_rounds"]` OR `adjust` should not loop back after the last round. The cleanest fix: check in `adjust` itself.

### Files to Modify

#### 5a. `agentx/backend/app/graph/edges.py`

```python
def round_or_done(state: SessionState) -> str:
    """After evaluation: continue to next round or finish session.
    
    round_num is 0-indexed. After N rounds complete, round_num == N.
    If round_num >= max_rounds, all rounds are done.
    """
    if state.get("round_num", 0) >= state.get("max_rounds", 3):
        return "done"
    return "adjust"
```

The current logic IS correct for the number of rounds. The off-by-one is actually in the `adjust` node: it increments round_num even when `round_or_done` says "done" — wait, no, it doesn't. `round_or_done` and `adjust` are mutually exclusive paths.

Let me re-trace carefully:
1. `create_session`: round_num=0. Graph runs host_setup→host_present→saboteur_inject→[interrupt]. Pauses. Phase = "student_writing" or "student_fixing".
2. `submit_original_code`: resumes. saboteur_inject→[interrupt at student_fix_await]. Phase = "student_fixing".
3. `submit_fix`: resumes. host_run_fix→evaluator_score→round_or_done.
   - round_num=0, max_rounds=3: 0>=3? No → adjust.
   - adjust: round_num=1, phase="host_present". Loop back.
4. Next round: host_setup→host_present→[interrupt]. Phase = "student_writing".
5. Write→saboteur_inject→[interrupt]. Phase = "student_fixing".
6. Fix→host_run_fix→evaluator_score→round_or_done.
   - round_num=1, max_rounds=3: 1>=3? No → adjust.
   - adjust: round_num=2.
7. Same for round 2.
   - round_num=2, max_rounds=3: 2>=3? No → adjust.
   - adjust: round_num=3.
8. Round 3:
   - host_setup→host_present→[interrupt].
   - Write→saboteur_inject→[interrupt].
   - Fix→host_run_fix→evaluator_score→round_or_done.
   - round_num=3, max_rounds=3: 3>=3? Yes → done.

So it runs rounds 0,1,2,3 = **4 rounds** when `max_rounds=3`. That's the off-by-one!

**The fix:** Change the check to use `>= max_rounds - 1` or change adjust to not increment past the limit:

Option A (cleanest): In `adjust`, only loop if the *next* round is within bounds:
```python
def adjust(state: SessionState) -> dict:
    next_round = state["round_num"] + 1
    # ... difficulty adjustment ...
    # Archive current round
    return {
        "round_num": next_round,
        "difficulty": difficulty,
        "phase": "host_present",
        "rounds": [current_round],
        ...
    }
```

And in `round_or_done`, the check should be `> max_rounds`:
```python
def round_or_done(state: SessionState) -> str:
    if state.get("round_num", 0) >= state.get("max_rounds", 3):
        return "done"
    return "adjust"
```

Wait, the issue is that `adjust` increments `round_num` AND the graph loops. But `round_or_done` runs BEFORE `adjust`. So the sequence is:

evaluator_score → round_or_done → (if "adjust") → adjust (increments round_num) → host_setup → ...

The `round_or_done` check sees the OLD round_num. After adjust increments it, the graph loops back and does another full round. So:

- Start: round_num=0
- After round 0 eval: round_or_done sees 0, adjust makes it 1
- After round 1 eval: round_or_done sees 1, adjust makes it 2
- After round 2 eval: round_or_done sees 2, adjust makes it 3
- After round 3 eval: round_or_done sees 3, 3>=3 → done

That's 4 rounds (0,1,2,3). **Confirmed off-by-one.**

**Fix:** Change `round_or_done` to check AFTER the increment conceptually:

```python
def round_or_done(state: SessionState) -> str:
    """After evaluation: should we do another round?
    
    state['round_num'] is the CURRENT round (0-indexed, not yet incremented).
    If we've completed round_num+1 rounds already, that's >= max_rounds, so done.
    """
    current_round_num = state.get("round_num", 0)
    max_rounds = state.get("max_rounds", 3)
    if current_round_num + 1 >= max_rounds:
        return "done"
    return "adjust"
```

This way: round_num=0, max_rounds=3: 0+1=1 >= 3? No → adjust → round_num=1.
round_num=1: 1+1=2 >= 3? No → adjust → round_num=2.
round_num=2: 2+1=3 >= 3? Yes → done.

Rounds: 0, 1, 2 = 3 rounds. ✓

### Edge Cases
- **max_rounds=1:** round_num=0: 0+1=1 >= 1? Yes → done. One round. ✓
- **max_rounds=0:** Should be invalid; add validation in `SessionCreate`.
- **Test update:** `test_graph.py` sets `max_rounds=1` and expects the graph to reach certain phases. Update the assertion.

### Dependencies
- Fix 5 is independent but should be done before Fix 1 (the new write flow) to avoid compounding bugs.

---

## Fix 6: Subprocess Fallback Has No Resource Limits

**Problem:** `_run_fallback` in `sandbox/manager.py` runs `subprocess.run()` with only a `timeout`. It doesn't set `mem_limit`, `cpu_quota`, or `pids_limit` — unlike the Docker path. A malicious or buggy student code could fork-bomb or consume all memory.

### Files to Modify

#### 6a. `agentx/backend/app/sandbox/manager.py`

**Add resource limits to `_run_fallback`:**

```python
import resource  # Linux only — graceful skip on Windows/macOS

def _run_fallback(self, code: str, language: str) -> dict:
    import subprocess, tempfile, os, platform

    suffix = ".py" if language == "python" else ".js"
    interp = "python" if language == "python" else "node"

    t0 = time.time()
    with tempfile.NamedTemporaryFile("w", suffix=suffix, delete=False) as f:
        f.write(code)
        path = f.name

    def _set_limits():
        """Pre-exec hook to set resource limits (Linux only)."""
        if platform.system() == "Linux":
            # Memory limit
            mem_bytes = settings.sandbox_mem_limit_mb * 1024 * 1024
            resource.setrlimit(resource.RLIMIT_AS, (mem_bytes, mem_bytes))
            # CPU time limit
            resource.setrlimit(resource.RLIMIT_CPU, (settings.docker_timeout_s, settings.docker_timeout_s))
            # Process count limit (no fork bombs)
            resource.setrlimit(resource.RLIMIT_NPROC, (64, 64))
            # File size limit
            resource.setrlimit(resource.RLIMIT_FSIZE, (10 * 1024 * 1024, 10 * 1024 * 1024))

    try:
        proc = subprocess.run(
            [interp, path],
            capture_output=True,
            timeout=settings.docker_timeout_s,
            preexec_fn=_set_limits if platform.system() == "Linux" else None,
        )
        # ... rest unchanged ...
```

**Edge case:** `resource` module doesn't exist on Windows. Use `platform.system()` guard. On Windows, fallback to just timeout (the existing behavior). On Linux, add all limits.

**Additional:** Set `RLIMIT_NOFILE` to prevent the child from opening too many file descriptors:
```python
resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
```

### Dependencies
- Independent of other fixes. Can be done in parallel.

---

## Fix 7: Sandbox Uses Public Docker Images Instead of Pre-Built Local Tags

**Problem:** `_run_docker` in `sandbox/manager.py` pulls `python:3.11-slim` and `node:20-alpine` from Docker Hub on first run. This is slow and may fail in air-gapped environments.

### Files to Modify

#### 7a. `agentx/backend/app/sandbox/manager.py`

**Change image map to use local pre-built tags:**

```python
image_map = {
    "python": "agentx-sandbox-python:latest",
    "javascript": "agentx-sandbox-node:latest",
}
```

#### 7b. `agentx/Dockerfile`

**Add sandbox base images as build targets:**

```dockerfile
# ── Sandbox: Python runner ──
FROM python:3.11-slim AS sandbox-python
# Minimal, no pip, no extras — just the interpreter

# ── Sandbox: Node runner ──
FROM node:20-alpine AS sandbox-node
# Minimal, no npm — just the runtime
```

#### 7c. `agentx/docker-compose.yml`

**Build sandbox images:**
```yaml
services:
  agentx:
    # ... existing config ...
    depends_on:
      - sandbox-python
      - sandbox-node

  sandbox-python:
    build:
      context: .
      dockerfile: Dockerfile
      target: sandbox-python
    image: agentx-sandbox-python:latest
    # No command — just needs to exist as an image

  sandbox-node:
    build:
      context: .
      dockerfile: Dockerfile
      target: sandbox-node
    image: agentx-sandbox-node:latest
```

**Alternative (simpler):** Use a multi-stage `docker-compose build` with named images. Or use a `Makefile`:
```makefile
build-sandbox:
	docker build --target sandbox-python -t agentx-sandbox-python:latest .
	docker build --target sandbox-node -t agentx-sandbox-node:latest .
```

#### 7d. `agentx/backend/app/config.py`

**Add config for sandbox image names:**
```python
sandbox_python_image: str = "agentx-sandbox-python:latest"
sandbox_node_image: str = "agentx-sandbox-node:latest"
```

### Edge Cases
- **Image not found:** If the pre-built image doesn't exist, `docker.from_env().containers.run()` will fail. Add a fallback that tries the public image, or raise a clear error.
- **Docker-in-Docker:** In Dokploy, the `docker.sock` mount means the agentx container shares the host's Docker daemon. Sandbox images must be built on the host first.

### Dependencies
- Independent. Can be done in parallel with other P1 items.

---

## Fix 8: No `run_tests` Tool

**Problem:** The saboteur generates `test_cases` (line 39 of `saboteur.py` prompt, line 197 of `nodes.py`), but the evaluator never *executes* them. The evaluator just compares code textually and asks the LLM to score. Hidden test cases can't be verified.

### Files to Modify

#### 8a. `agentx/backend/app/tools/run_tests.py` (NEW FILE)

```python
"""Tool: execute test cases against student code in the sandbox."""

import logging
from langchain_core.tools import tool

logger = logging.getLogger(__name__)

@tool
def run_tests(code: str, test_cases: list[dict], language: str) -> dict:
    """Run test cases against student code and return pass/fail results.

    Args:
        code: The student's code to test.
        test_cases: List of dicts with 'input', 'expected', and optional 'description'.
        language: Programming language (python, javascript).

    Returns:
        Dict with results: list of {input, expected, actual, passed, description}.
    """
    from app.sandbox.manager import get_sandbox
    sandbox = get_sandbox()

    results = []
    for i, tc in enumerate(test_cases):
        input_val = tc.get("input", "")
        expected = tc.get("expected", "")
        description = tc.get("description", f"Test {i+1}")

        # Wrap code with test execution
        if language == "python":
            test_wrapper = f"""
{code}

# --- Test runner ---
import json
try:
    result = two_sum(*json.loads('{input_val}')) if '{input_val}' else None
    print(json.dumps(result))
except Exception as e:
    print(json.dumps({{"error": str(e)}}), end="")
"""
        elif language == "javascript":
            test_wrapper = f"""
{code}

// --- Test runner ---
try {{
    const result = twoSum(...JSON.parse('{input_val}'));
    console.log(JSON.stringify(result));
}} catch(e) {{
    process.stdout.write(JSON.stringify({{error: e.message}}));
}}
"""
        else:
            results.append({
                "input": input_val,
                "expected": expected,
                "actual": "",
                "passed": False,
                "description": description,
                "error": f"Unsupported language: {language}",
            })
            continue

        exec_result = sandbox.run(test_wrapper, language)
        actual = exec_result.get("stdout", "").strip()
        passed = actual == expected

        results.append({
            "input": input_val,
            "expected": expected,
            "actual": actual,
            "passed": passed,
            "description": description,
        })

    total = len(results)
    passed_count = sum(1 for r in results if r["passed"])

    return {
        "ok": True,
        "total": total,
        "passed": passed_count,
        "failed": total - passed_count,
        "results": results,
    }
```

**Critical design issue:** The test wrapper approach above is fragile — it assumes specific function names (`two_sum`, `twoSum`). A more robust approach:

```python
@tool
def run_tests(code: str, test_cases: list[dict], language: str) -> dict:
    """Run test cases against student code."""
    from app.sandbox.manager import get_sandbox
    import json

    sandbox = get_sandbox()
    results = []

    for i, tc in enumerate(test_cases):
        input_val = tc.get("input", "")
        expected = tc.get("expected", "")
        description = tc.get("description", f"Test {i+1}")

        # Build test wrapper that evaluates the code and runs the test
        if language == "python":
            test_code = f"""\
import json, sys
{code}

# --- Test ---
try:
    _input = json.loads('{json.dumps(input_val)}')
    if isinstance(_input, dict):
        _result = two_sum(**_input)
    elif isinstance(_input, list):
        _result = two_sum(*_input)
    else:
        _result = two_sum(_input)
    print(json.dumps(_result))
except Exception as e:
    print(json.dumps({{"__error__": str(e)}}))
"""
        else:
            test_code = f"""\
{code}

try {{
    const _input = JSON.parse('{json.dumps(input_val)}');
    const _result = Array.isArray(_input) ? twoSum(..._input) : twoSum(_input);
    console.log(JSON.stringify(_result));
}} catch(e) {{
    process.stdout.write(JSON.stringify({{__error__: e.message}}));
}}
"""

        exec_result = sandbox.run(test_code, language)
        stdout = exec_result.get("stdout", "").strip()
        
        try:
            actual = json.loads(stdout)
            if isinstance(actual, dict) and "__error__" in actual:
                actual = f"ERROR: {actual['__error__']}"
                passed = False
            else:
                # Compare as strings for simplicity
                passed = str(actual) == str(expected) or stdout == expected
        except json.JSONDecodeError:
            actual = stdout
            passed = stdout == expected

        results.append({
            "input": input_val,
            "expected": expected,
            "actual": actual,
            "passed": passed,
            "description": description,
        })

    total = len(results)
    return {
        "ok": True,
        "total": total,
        "passed": sum(1 for r in results if r["passed"]),
        "failed": total - sum(1 for r in results if r["passed"]),
        "results": results,
    }
```

#### 8b. `agentx/backend/app/graph/nodes.py`

**Integrate `run_tests` into `evaluator_score`:**

After the evaluator LLM generates the score, run the test cases:
```python
def evaluator_score(state: SessionState) -> dict:
    # ... existing code ...
    
    # After getting the fix_code, run the test cases
    test_cases = current.get("test_cases", [])
    if test_cases and fix_code:
        from app.tools.run_tests import run_tests_tool
        test_results = run_tests_tool.invoke({
            "code": fix_code,
            "test_cases": test_cases,
            "language": language,
        })
        # Incorporate test results into the score
        if test_results.get("ok"):
            # Adjust score based on actual test pass rate
            pass_rate = test_results["passed"] / max(test_results["total"], 1)
            # ... adjust score accordingly ...
```

**Add `test_cases` to `RoundRecord` and state:**

In `state.py`, add to `RoundRecord`:
```python
class RoundRecord(TypedDict):
    # ... existing fields ...
    test_cases: list[dict]  # NEW — test cases from saboteur
```

In `saboteur_inject`, store the test cases:
```python
return {
    "current_round": {
        **state["current_round"],
        "buggy_code": buggy_code,
        "bug_manifest": bugs,
        "test_cases": test_cases,  # NEW
        "original_exec": original_exec,
        "buggy_exec": buggy_exec,
    },
    ...
}
```

#### 8c. `agentx/frontend/app/lib/types.ts`

Add to `RoundRecord`:
```typescript
export interface RoundRecord {
  // ... existing ...
  test_cases: Array<{
    input: string;
    expected: string;
    description?: string;
  }>;
}
```

### Edge Cases & Gotchas
- **Function name mismatch:** The test wrapper assumes `two_sum`/`twoSum`. The saboteur prompt should instruct the LLM to also output the function name, or the tool should detect it. For MVP, add a `function_name` parameter to `run_tests`.
- **Infinite loops:** Tests that hang are caught by the sandbox timeout. The `run_tests` tool should set a per-test timeout.
- **Non-deterministic output:** If the code has randomness, tests may fail. Not a concern for most coding challenges.

### Dependencies
- Fix 8 depends on Fix 3 (tools infrastructure).
- Fix 8 feeds into Fix 4 (test results show in TracePanel).
- Fix 8 needs the `test_cases` field in `RoundRecord` — add to `state.py`.

---

## Fix 9: Bug-Count Constants Disagree Across 3 Sources

**Problem:** Three places define how many bugs to inject, and they disagree:

| Source | easy | medium | hard |
|--------|------|--------|------|
| `config.py` `max_bugs_*` | 2 | 2 | 3 |
| `utils.py` `difficulty_to_num_bugs()` | 1 | 2 | 3 |
| `prompts/saboteur.py` | 1 | 2 | 3 |

`config.py` says easy=2, but `utils.py` (which is actually called in `saboteur_inject`) says easy=1. The config values are never used anywhere.

### Files to Modify

#### 9a. `agentx/backend/app/config.py`

**Remove the unused `max_bugs_*` constants** or align them:

```python
# Remove these — they're never referenced:
# max_bugs_easy: int = 2
# max_bugs_medium: int = 2
# max_bugs_hard: int = 3
```

Or, make `utils.py` reference the config:

```python
# config.py
max_bugs_per_difficulty: dict[str, int] = {
    "easy": 1,
    "medium": 2,
    "hard": 3,
}
```

```python
# utils.py
def difficulty_to_num_bugs(difficulty: str) -> int:
    return settings.max_bugs_per_difficulty.get(difficulty, 2)
```

#### 9b. `agentx/backend/app/prompts/saboteur.py`

Keep the prompt text aligned: "easy=1, medium=2, hard=3". This matches the corrected `utils.py`.

### Dependencies
- Independent. Quick fix.

---

# P2 — Completeness vs Plan

---

## Fix 10: No PDF Report

**Problem:** The implementation plan calls for a PDF summary report at session end. Nothing generates one.

### Files to Modify

#### 10a. `agentx/backend/app/reports/pdf_generator.py` (NEW FILE)

```python
"""Generate PDF session report using reportlab."""

import logging
from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors

logger = logging.getLogger(__name__)

def generate_session_report(state: dict) -> bytes:
    """Generate a PDF report for a completed training session.
    
    Args:
        state: Final SessionState dict.
    
    Returns:
        PDF file bytes.
    """
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    story = []

    # Title
    story.append(Paragraph("AgentX Training Report", styles["Title"]))
    story.append(Spacer(1, 12))

    # Session info
    story.append(Paragraph(f"Session: {state.get('session_id', 'N/A')}", styles["Normal"]))
    story.append(Paragraph(f"Difficulty: {state.get('difficulty', 'N/A')}", styles["Normal"]))
    story.append(Paragraph(f"Language: {state.get('language', 'N/A')}", styles["Normal"]))
    story.append(Spacer(1, 12))

    # Round summaries
    rounds = state.get("rounds", [])
    for i, rd in enumerate(rounds):
        story.append(Paragraph(f"Round {i+1}", styles["Heading2"]))
        
        score = rd.get("score", {})
        if score:
            story.append(Paragraph(f"Score: {score.get('total', 0)}/100", styles["Normal"]))
            story.append(Paragraph(f"Bugs Fixed: {score.get('bugs_fixed', 0)}/{score.get('bugs_total', 0)}", styles["Normal"]))
            story.append(Paragraph(f"Code Quality: {score.get('code_quality', 0):.1%}", styles["Normal"]))
        
        # Bug manifest
        bugs = rd.get("bug_manifest", [])
        if bugs:
            story.append(Paragraph("Bugs Injected:", styles["Normal"]))
            for bug in bugs:
                story.append(Paragraph(
                    f"  - Line {bug.get('line')}: {bug.get('type')} — {bug.get('description')}",
                    styles["Normal"]
                ))
        
        # Test results
        test_cases = rd.get("test_cases", [])
        if test_cases:
            story.append(Paragraph(f"Test Cases: {len(test_cases)}", styles["Normal"]))
        
        story.append(Spacer(1, 8))

    # Overall stats
    if rounds:
        total_score = sum(r.get("score", {}).get("total", 0) for r in rounds if r.get("score"))
        avg_score = total_score / len(rounds)
        story.append(Paragraph(f"Overall Average: {avg_score:.0f}/100", styles["Heading2"]))

    doc.build(story)
    return buffer.getvalue()
```

#### 10b. `agentx/backend/app/api/routes.py`

**Add endpoint:**
```python
from fastapi.responses import Response

@router.get("/api/sessions/{session_id}/report")
def get_session_report(session_id: str):
    """Generate and download a PDF session report."""
    if session_id not in _sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session = _sessions[session_id]
    state = session["state"]
    
    if state.get("phase") != "done":
        raise HTTPException(status_code=400, detail="Session not completed yet")
    
    from app.reports.pdf_generator import generate_session_report
    pdf_bytes = generate_session_report(state)
    
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=agentx-report-{session_id}.pdf"},
    )
```

#### 10c. `agentx/backend/pyproject.toml`

Add dependency:
```toml
[tool.poetry.dependencies]
reportlab = "^4.0.0"
```

#### 10d. `agentx/frontend/app/pages/SessionPage.tsx`

**Add download button** when `phase === "done"`:
```tsx
{phase === "done" && (
  <a
    href={`/api/sessions/${currentSessionId}/report`}
    download
    className="rounded-lg bg-green-500 px-4 py-1.5 text-sm font-semibold text-black"
  >
    Download Report
  </a>
)}
```

### Edge Cases
- **Empty rounds:** If all rounds had LLM failures, rounds may be empty. Handle gracefully.
- **Large sessions:** PDF generation should be fast (< 1s) since it's just text.
- **No reportlab in Docker:** The `pip install .` in Dockerfile will install it from pyproject.toml.

### Dependencies
- Depends on Fix 8 (test_cases in RoundRecord) for test results in the report.
- Independent of frontend fixes.

---

## Fix 11: No Persistence — In-Memory `_sessions` Dict

**Problem:** `_sessions: dict[str, dict] = {}` loses all data on server restart. For a hackathon demo this is acceptable, but the plan calls for basic persistence.

### Files to Modify

#### 11a. `agentx/backend/app/persistence/store.py` (NEW FILE)

**SQLite-based persistence using ajson for serialization:**

```python
"""SQLite-backed session persistence."""

import json
import sqlite3
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent.parent.parent.parent / "data" / "sessions.db"

def _get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            session_id TEXT PRIMARY KEY,
            state_json TEXT NOT NULL,
            config_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    conn.commit()
    return conn

def save_session(session_id: str, state: dict, config: dict, created_at: str):
    conn = _get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO sessions (session_id, state_json, config_json, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
        (session_id, json.dumps(state), json.dumps(config), created_at, created_at),
    )
    conn.commit()
    conn.close()

def load_session(session_id: str) -> dict | None:
    conn = _get_conn()
    row = conn.execute("SELECT state_json, config_json, created_at FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
    conn.close()
    if not row:
        return None
    return {
        "state": json.loads(row[0]),
        "config": json.loads(row[1]),
        "created_at": row[2],
    }

def update_session(session_id: str, state: dict):
    conn = _get_conn()
    from datetime import datetime, timezone
    conn.execute(
        "UPDATE sessions SET state_json = ?, updated_at = ? WHERE session_id = ?",
        (json.dumps(state), datetime.now(timezone.utc).isoformat(), session_id),
    )
    conn.commit()
    conn.close()

def list_sessions() -> list[dict]:
    conn = _get_conn()
    rows = conn.execute("SELECT session_id, created_at, updated_at FROM sessions ORDER BY updated_at DESC").fetchall()
    conn.close()
    return [{"session_id": r[0], "created_at": r[1], "updated_at": r[2]} for r in rows]
```

#### 11b. `agentx/backend/app/api/routes.py`

**Replace `_sessions` dict with persistence calls:**

```python
from app.persistence.store import save_session, load_session, update_session

# In create_session:
save_session(session_id, result, config, created_at)

# In submit_fix / submit_original_code:
update_session(session_id, result)

# In get_session:
session = load_session(session_id)
```

**Keep `_sessions` as a runtime cache** for performance:
```python
_sessions: dict[str, dict] = {}  # Runtime cache

def _get_session(session_id: str) -> dict | None:
    if session_id in _sessions:
        return _sessions[session_id]
    loaded = load_session(session_id)
    if loaded:
        _sessions[session_id] = loaded
    return loaded
```

#### 11c. `agentx/Dockerfile`

Add data volume mount point:
```dockerfile
RUN mkdir -p /app/data && chown agentx:agentx /app/data
VOLUME /app/data
```

#### 11d. `agentx/docker-compose.yml`

The `agentx-sessions` volume is already mounted at `/app/data`. Verify the SQLite DB path aligns.

### Edge Cases
- **Concurrent writes:** SQLite handles this with its internal locking. Fine for single-server.
- **State serialization:** LangGraph's state contains TypedDict objects. `json.dumps` handles dicts, but `datetime` objects in trace events need `isoformat()` strings (they already are).
- **Session size:** Each session state with code + trace could be 50-100KB. SQLite handles this easily.

### Dependencies
- Independent. Can be done in parallel.

---

## Fix 12: No Language/Topic Pickers (Hardcoded python/arrays/easy)

**Problem:** `SessionPage.tsx` line 63-67 hardcodes `language: "python"`, `topic: "arrays"`, `difficulty: "easy"`. Students can't choose.

### Files to Modify

This is partially addressed in Fix 1 (HomePage.tsx changes). The full implementation:

#### 12a. `agentx/frontend/app/pages/HomePage.tsx`

Full redesign with pickers:

```tsx
import { useState } from "react";

interface HomePageProps {
  onStart: (config: { language: string; topic: string; difficulty: string }) => void;
}

const LANGUAGES = [
  { value: "python", label: "Python" },
  { value: "javascript", label: "JavaScript" },
];

const TOPICS = [
  { value: "arrays", label: "Arrays" },
  { value: "strings", label: "Strings" },
  { value: "trees", label: "Trees" },
];

const DIFFICULTIES = [
  { value: "easy", label: "Easy", color: "text-green-400" },
  { value: "medium", label: "Medium", color: "text-amber-400" },
  { value: "hard", label: "Hard", color: "text-red-400" },
];

export function HomePage({ onStart }: HomePageProps) {
  const [language, setLanguage] = useState("python");
  const [topic, setTopic] = useState("arrays");
  const [difficulty, setDifficulty] = useState("easy");

  return (
    <div className="flex flex-col items-center justify-center gap-8 py-20">
      {/* ... existing title and description ... */}

      {/* Config pickers */}
      <div className="flex flex-col items-center gap-4">
        <div className="flex gap-4">
          <PickerGroup label="Language">
            {LANGUAGES.map(l => (
              <button
                key={l.value}
                onClick={() => setLanguage(l.value)}
                className={`rounded-lg px-4 py-2 text-sm ${language === l.value ? "bg-amber-500 text-black" : "bg-zinc-800 text-zinc-300 hover:bg-zinc-700"}`}
              >
                {l.label}
              </button>
            ))}
          </PickerGroup>

          <PickerGroup label="Topic">
            {TOPICS.map(t => (
              <button
                key={t.value}
                onClick={() => setTopic(t.value)}
                className={`rounded-lg px-4 py-2 text-sm ${topic === t.value ? "bg-amber-500 text-black" : "bg-zinc-800 text-zinc-300 hover:bg-zinc-700"}`}
              >
                {t.label}
              </button>
            ))}
          </PickerGroup>

          <PickerGroup label="Difficulty">
            {DIFFICULTIES.map(d => (
              <button
                key={d.value}
                onClick={() => setDifficulty(d.value)}
                className={`rounded-lg px-4 py-2 text-sm ${difficulty === d.value ? "bg-amber-500 text-black" : "bg-zinc-800 text-zinc-300 hover:bg-zinc-700"}`}
              >
                <span className={d.color}>{d.label}</span>
              </button>
            ))}
          </PickerGroup>
        </div>

        <button
          onClick={() => onStart({ language, topic, difficulty })}
          className="rounded-lg bg-amber-500 px-6 py-3 font-semibold text-black transition-colors hover:bg-amber-400"
        >
          Start Training
        </button>
      </div>

      {/* ... existing agent cards ... */}
    </div>
  );
}

function PickerGroup({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-2">
      <span className="text-xs text-zinc-500">{label}</span>
      <div className="flex gap-2">{children}</div>
    </div>
  );
}
```

#### 12b. `agentx/frontend/app/App.tsx`

```tsx
const [sessionConfig, setSessionConfig] = useState({
  language: "python",
  topic: "arrays",
  difficulty: "easy",
});

const startSession = (config: { language: string; topic: string; difficulty: string }) => {
  setSessionConfig(config);
  setSessionId("new");
  setPage("session");
};

// Pass to SessionPage:
<SessionPage sessionId={sessionId} onBack={goHome} config={sessionConfig} />
```

#### 12c. `agentx/frontend/app/pages/SessionPage.tsx`

Accept `config` prop and use it:
```tsx
interface SessionPageProps {
  sessionId: string;
  onBack: () => void;
  config: { language: string; topic: string; difficulty: string };
}

// In useEffect:
const req: CreateSessionRequest = {
  language: config.language,
  topic: config.topic,
  difficulty: config.difficulty,
  max_rounds: 3,
};
```

### Dependencies
- Fix 12 is partially implemented in Fix 1. This section adds the full UI.

---

## Fix 13: Monaco Not Using Diff Editor

**Problem:** After sabotage, the student should see their original code vs the buggy code side-by-side (diff view). Currently, Monaco shows a single editor that swaps content based on phase.

### Files to Modify

#### 13a. `agentx/frontend/app/components/CodeEditor.tsx`

**Add diff mode when showing buggy vs original:**

```tsx
import { DiffEditor } from "@monaco-editor/react";

interface CodeEditorProps {
  readOnly?: boolean;
  language?: string;
  onChange?: (value: string) => void;
  mode?: "single" | "diff";  // NEW
  originalCode?: string;      // NEW — for diff view
  modifiedCode?: string;      // NEW — for diff view
}

export function CodeEditor({
  readOnly = false,
  language = "python",
  onChange,
  mode = "single",
  originalCode,
  modifiedCode,
}: CodeEditorProps) {
  // ... existing state ...

  if (mode === "diff" && originalCode && modifiedCode) {
    return (
      <div className="flex h-full flex-col">
        <div className="flex items-center justify-between border-b border-zinc-800 px-3 py-2">
          <span className="text-xs text-zinc-500">📖 Diff: Original vs Buggy</span>
          <span className="text-xs text-zinc-600">{language}</span>
        </div>
        <div className="flex-1">
          <DiffEditor
            language={language}
            original={originalCode}
            modified={modifiedCode}
            theme="vs-dark"
            options={{
              readOnly: true,
              renderSideBySide: true,
              minimap: { enabled: false },
              fontSize: 13,
              automaticLayout: true,
            }}
          />
        </div>
      </div>
    );
  }

  // ... existing single-editor JSX ...
}
```

#### 13b. `agentx/frontend/app/pages/SessionPage.tsx`

**Use diff mode during sabotage/executing phases:**

```tsx
const showDiff = ["sabotage", "executing_original", "executing_buggy"].includes(phase);

<CodeEditor
  language={config.language}
  readOnly={phase !== "student_fixing" && phase !== "student_writing"}
  mode={showDiff ? "diff" : "single"}
  originalCode={originalCode}
  modifiedCode={buggyCode}
/>
```

### Edge Cases
- **Empty codes:** If `originalCode` or `buggyCode` is empty, fall back to single mode.
- **Large diffs:** Monaco's diff editor handles large files well.
- **@monaco-editor/react version:** The `DiffEditor` component is available in `@monaco-editor/react` v4.7+. The project uses `^4.7.0` — confirmed.

### Dependencies
- Depends on Fix 1 (the write phase establishes original code).

---

## Fix 14: No Per-Agent Context Projection

**Problem:** Each agent (Host, Saboteur, Evaluator) receives the full state or constructs its own prompt. There's no formal context projection — each agent should only see what it needs.

### Files to Modify

#### 14a. `agentx/backend/app/agents/context.py` (NEW FILE)

```python
"""Per-agent context projection — builds minimal prompts for each agent."""

from app.graph.state import SessionState


def project_host_context(state: SessionState) -> dict:
    """What the Host agent needs to see."""
    return {
        "session_id": state["session_id"],
        "language": state["language"],
        "topic": state["topic"],
        "difficulty": state["difficulty"],
        "round_num": state["round_num"],
        "chat_history": state.get("chat", [])[-5:],  # Last 5 messages
    }


def project_saboteur_context(state: SessionState) -> dict:
    """What the Saboteur agent needs to see."""
    current = state.get("current_round", {})
    return {
        "original_code": current.get("original_code", ""),
        "language": state["language"],
        "difficulty": state["difficulty"],
        "round_num": state["round_num"],
    }


def project_evaluator_context(state: SessionState) -> dict:
    """What the Evaluator agent needs to see."""
    current = state.get("current_round", {})
    return {
        "original_code": current.get("original_code", ""),
        "buggy_code": current.get("buggy_code", ""),
        "fix_code": current.get("fix_code", ""),
        "bug_manifest": current.get("bug_manifest", []),
        "fix_exec": current.get("fix_exec"),
        "test_cases": current.get("test_cases", []),
        "language": state["language"],
        "round_num": state["round_num"],
    }
```

#### 14b. `agentx/backend/app/graph/nodes.py`

**Use context projection in each node:**

```python
def host_setup(state: SessionState) -> dict:
    from app.agents.context import project_host_context
    ctx = project_host_context(state)
    # Use ctx instead of raw state
    ...

def saboteur_inject(state: SessionState) -> dict:
    from app.agents.context import project_saboteur_context
    ctx = project_saboteur_context(state)
    # Use ctx["original_code"] etc.
    ...

def evaluator_score(state: SessionState) -> dict:
    from app.agents.context import project_evaluator_context
    ctx = project_evaluator_context(state)
    # Use ctx fields
    ...
```

### Edge Cases
- **Missing fields:** All projections should use `.get()` with defaults.
- **Performance:** Minimal impact — just dict construction.

### Dependencies
- Independent. Can be done after Fix 3 (tools refactor).

---

# P3 — Testing & Hardening

---

## Fix 15: No conftest.py, Near-Zero Test Coverage

**Problem:** No `conftest.py` exists. Only `test_graph.py` with 2 tests (one is a loose assertion). No tests for tools, sandbox, utils, routes, or frontend.

### Files to Create

#### 15a. `agentx/backend/tests/conftest.py` (NEW FILE)

```python
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
        "buggy_code": "def two_sum(nums, target):\n    for i in range(len(nums)):\n        for j in range(i, len(nums)):\n            if nums[i] + nums[j] == target:\n                return [i, j]\n    return []",
        "bug_manifest": [
            {"line": 3, "type": "off_by_one", "description": "Inner loop starts at i instead of i+1",
             "original": "range(i+1", "sabotaged": "range(i"}
        ],
        "original_exec": {"stdout": "", "stderr": "", "exit_code": 0, "duration_ms": 10, "sandbox": "mock"},
        "buggy_exec": {"stdout": "", "stderr": "", "exit_code": 0, "duration_ms": 10, "sandbox": "mock"},
    }
    return state
```

#### 15b. `agentx/backend/tests/test_utils.py` (NEW FILE)

```python
"""Tests for utility functions."""

import pytest
from app.utils import parse_json_response, difficulty_to_num_bugs, apply_bugs, validate_compiles


class TestParseJsonResponse:
    def test_direct_json(self):
        assert parse_json_response('{"key": "value"}') == {"key": "value"}

    def test_markdown_code_block(self):
        text = 'Here is the result:\n```json\n{"key": "value"}\n```\nDone.'
        assert parse_json_response(text) == {"key": "value"}

    def test_embedded_json(self):
        text = 'The answer is {"key": "value"} and more text'
        assert parse_json_response(text) == {"key": "value"}

    def test_invalid_json(self):
        assert parse_json_response("not json at all") is None

    def test_none_input(self):
        assert parse_json_response(None) is None

    def test_empty_string(self):
        assert parse_json_response("") is None


class TestDifficultyToNumBugs:
    def test_easy(self):
        assert difficulty_to_num_bugs("easy") == 1

    def test_medium(self):
        assert difficulty_to_num_bugs("medium") == 2

    def test_hard(self):
        assert difficulty_to_num_bugs("hard") == 3

    def test_unknown_defaults_to_2(self):
        assert difficulty_to_num_bugs("unknown") == 2


class TestApplyBugs:
    def test_single_bug(self):
        code = "def foo():\n    return 1 + 2"
        bugs = [{"line": 2, "original": "1 + 2", "sabotaged": "1 - 2"}]
        result = apply_bugs(code, bugs)
        assert "1 - 2" in result
        assert "1 + 2" not in result

    def test_no_match_is_noop(self):
        code = "def foo():\n    pass"
        bugs = [{"line": 2, "original": "nonexistent", "sabotaged": "replaced"}]
        result = apply_bugs(code, bugs)
        assert result == code

    def test_out_of_range_line(self):
        code = "line1"
        bugs = [{"line": 99, "original": "x", "sabotaged": "y"}]
        result = apply_bugs(code, bugs)
        assert result == code

    def test_empty_bugs(self):
        code = "unchanged"
        assert apply_bugs(code, []) == code


class TestValidateCompiles:
    def test_valid_python(self):
        assert validate_compiles("def foo():\n    pass", "python") is True

    def test_invalid_python(self):
        assert validate_compiles("def foo(:\n    pass", "python") is False

    def test_unknown_language_passes(self):
        assert validate_compiles("anything", "ruby") is True
```

#### 15c. `agentx/backend/tests/test_tools.py` (NEW FILE)

```python
"""Tests for tool functions."""

import pytest
from unittest.mock import patch, MagicMock
from app.tools.fetch_challenge import _fallback_challenge


class TestFallbackChallenge:
    def test_arrays_easy(self):
        result = _fallback_challenge("arrays", "easy", "python")
        assert result["ok"] is True
        assert result["challenge_detail"]["title"] == "Two Sum"
        assert "starter_code" in result["challenge_detail"]

    def test_unknown_topic_generic(self):
        result = _fallback_challenge("unknown_topic", "easy", "python")
        assert result["ok"] is True
        assert "Generic" in result["challenge_detail"]["title"]

    def test_starter_code_language(self):
        result = _fallback_challenge("arrays", "easy", "javascript")
        assert "javascript" in result["challenge_detail"]["starter_code"]


class TestInjectBugsTool:
    @patch("app.tools.inject_bugs.make_llm")
    def test_inject_bugs_success(self, mock_make_llm):
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = '{"bugs": [{"line": 2, "type": "logic", "description": "test", "original": "pass", "sabotaged": "return None"}], "test_cases": []}'
        mock_llm.invoke.return_value = mock_response
        mock_make_llm.return_value = mock_llm

        with patch("app.tools.inject_bugs.get_sandbox") as mock_get_sandbox:
            mock_sandbox = MagicMock()
            mock_sandbox.run.return_value = {"stdout": "", "stderr": "", "exit_code": 0, "duration_ms": 10, "sandbox": "mock"}
            mock_get_sandbox.return_value = mock_sandbox

            from app.tools.inject_bugs import inject_bugs_tool
            result = inject_bugs_tool.invoke({
                "original_code": "def foo():\n    pass",
                "difficulty": "easy",
                "language": "python",
            })
            assert result["ok"] is True
            assert "buggy_code" in result
            assert len(result["bug_manifest"]) == 1
```

#### 15d. `agentx/backend/tests/test_routes.py` (NEW FILE)

```python
"""Tests for API routes."""

import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


class TestHealth:
    def test_health_endpoint(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["service"] == "agentx"


class TestCreateSession:
    @patch("app.api.routes.get_graph")
    def test_create_session(self, mock_get_graph, client):
        mock_graph = MagicMock()
        mock_graph.invoke.return_value = {
            "session_id": "test-001",
            "phase": "student_writing",
            "round_num": 0,
            "difficulty": "easy",
            "current_round": {
                "challenge": "Two Sum",
                "original_code": "",
            },
            "rounds": [],
            "chat": [],
            "trace": [],
        }
        mock_get_graph.return_value = mock_graph

        response = client.post("/api/sessions", json={
            "language": "python",
            "topic": "arrays",
            "difficulty": "easy",
            "max_rounds": 3,
        })
        assert response.status_code == 200
        data = response.json()
        assert "session_id" in data
        assert data["phase"] == "student_writing"

    def test_create_session_invalid_body(self, client):
        response = client.post("/api/sessions", json={})
        # Should use defaults — still succeeds
        assert response.status_code == 200


class TestGetSession:
    def test_get_nonexistent_session(self, client):
        response = client.get("/api/sessions/nonexistent")
        assert response.status_code == 404


class TestSubmitFix:
    def test_submit_fix_nonexistent_session(self, client):
        response = client.post("/api/sessions/nonexistent/fix", json={"fix_code": "pass"})
        assert response.status_code == 404

    def test_submit_fix_empty_code(self, client):
        response = client.post("/api/sessions/nonexistent/fix", json={"fix_code": ""})
        assert response.status_code == 404  # Session not found comes first
```

### Dependencies
- Fix 15 should be done early (P3 but foundational for verifying all other fixes).
- Tests for Fix 1 (write phase), Fix 3 (tools), Fix 8 (run_tests) should be added as those fixes land.

---

## Fix 16: Loose Test Assertions

**Problem:** `test_graph.py` line 83: `assert result["phase"] == "student_fixing"` — after the graph interrupt, the phase should be `"student_writing"` (with Fix 1). Line 89: `assert result2["phase"] in ("evaluating", "round_complete", "done", "host_present")` — accepts too many phases.

### Files to Modify

#### 16a. `agentx/backend/tests/test_graph.py`

**Update test_stub_round_completes:**

```python
def test_stub_round_completes():
    graph = build_graph()
    config = {"configurable": {"thread_id": "test-thread-002"}}

    # ... same mock setup ...

    initial_state = { ... }  # Updated with test_cases field

    with patch("app.agents.base.make_llm", side_effect=mock_make_llm), \
         patch("app.sandbox.manager.get_sandbox", return_value=mock_sandbox):
        
        # First invocation: host_setup → host_present → [interrupt before saboteur_inject]
        result = graph.invoke(initial_state, config)
        assert result["phase"] == "student_writing"
        assert result["current_round"]["challenge"] != ""

        # Simulate student submitting original code
        graph.update_state(config, {
            "current_round": {
                **result["current_round"],
                "original_code": "def two_sum(nums, target):\n    for i in range(len(nums)):\n        for j in range(i+1, len(nums)):\n            if nums[i] + nums[j] == target:\n                return [i, j]\n    return []",
                "original_code_submitted": True,
            }
        })
        result2 = graph.invoke(None, config)
        # Now paused before student_fix_await
        assert result2["phase"] == "student_fixing"
        assert result2["current_round"]["buggy_code"] != ""

        # Simulate student submitting fix
        graph.update_state(config, {
            "current_round": {**result2["current_round"], "fix_code": "def two_sum(nums, target):\n    seen = {}\n    for i, num in enumerate(nums):\n        complement = target - num\n        if complement in seen:\n            return [seen[complement], i]\n        seen[num] = i\n    return []"}
        })
        result3 = graph.invoke(None, config)
        # Should complete all the way through
        assert result3["phase"] == "done"
```

**Add targeted unit tests:**

```python
def test_adjust_increments_round():
    """adjust() should increment round_num by 1."""
    from app.graph.nodes import adjust
    state = {
        "round_num": 0,
        "current_round": {"score": {"total": 60}},
        "difficulty": "easy",
    }
    result = adjust(state)
    assert result["round_num"] == 1

def test_round_or_done_at_limit():
    """round_or_done returns 'done' when max rounds reached."""
    from app.graph.edges import round_or_done
    state = {"round_num": 2, "max_rounds": 3}
    # After round 2 completes (round_num=2), 2+1=3 >= 3 → done
    assert round_or_done(state) == "done"

def test_round_or_done_below_limit():
    from app.graph.edges import round_or_done
    state = {"round_num": 0, "max_rounds": 3}
    assert round_or_done(state) == "adjust"

def test_difficulty_adjustment():
    """High score should increase difficulty."""
    from app.graph.nodes import adjust
    state = {"round_num": 0, "difficulty": "easy", "current_round": {"score": {"total": 85}}}
    result = adjust(state)
    assert result["difficulty"] == "medium"
```

### Dependencies
- Depends on Fix 5 (off-by-one fix) and Fix 1 (write phase).

---

## Fix 17: No Frontend Tests

**Problem:** No `.test.*` files exist in the frontend. Vitest is configured (`"test": "vitest"` in package.json) but never used.

### Files to Create

#### 17a. `agentx/frontend/app/stores/__tests__/session.test.ts` (NEW FILE)

```typescript
import { describe, it, expect, beforeEach } from "vitest";
import { useSessionStore } from "../session";

describe("SessionStore", () => {
  beforeEach(() => {
    useSessionStore.getState().reset();
  });

  it("starts with default state", () => {
    const state = useSessionStore.getState();
    expect(state.phase).toBe("setup");
    expect(state.roundNum).toBe(0);
    expect(state.chat).toEqual([]);
    expect(state.trace).toEqual([]);
  });

  it("init sets session data", () => {
    useSessionStore.getState().init({
      session_id: "test-123",
      phase: "student_writing",
      round_num: 0,
      difficulty: "easy",
      challenge: "Two Sum",
      original_code: "",
      buggy_code: "",
      chat: [],
      trace: [],
      score: null,
    });
    const state = useSessionStore.getState();
    expect(state.sessionId).toBe("test-123");
    expect(state.phase).toBe("student_writing");
  });

  it("addChatMessage appends to chat", () => {
    useSessionStore.getState().addChatMessage({
      role: "host",
      content: "Hello!",
      ts: new Date().toISOString(),
    });
    expect(useSessionStore.getState().chat).toHaveLength(1);
  });

  it("addTraceEvent appends to trace", () => {
    useSessionStore.getState().addTraceEvent({
      phase: "setup",
      agent: "host",
      tool: "fetch_challenge",
      args: {},
      result: { ok: true },
      ts: new Date().toISOString(),
    });
    expect(useSessionStore.getState().trace).toHaveLength(1);
  });

  it("setPhase updates phase", () => {
    useSessionStore.getState().setPhase("student_fixing");
    expect(useSessionStore.getState().phase).toBe("student_fixing");
  });

  it("reset restores initial state", () => {
    useSessionStore.getState().setPhase("done");
    useSessionStore.getState().reset();
    expect(useSessionStore.getState().phase).toBe("setup");
  });
});
```

#### 17b. `agentx/frontend/app/lib/__tests__/api.test.ts` (NEW FILE)

```typescript
import { describe, it, expect, vi, beforeEach } from "vitest";

// Mock fetch globally
const mockFetch = vi.fn();
vi.stubGlobal("fetch", mockFetch);

import { createSession, submitFix, getSession } from "../api";

describe("API client", () => {
  beforeEach(() => {
    mockFetch.mockReset();
  });

  it("createSession sends POST with correct body", async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ session_id: "abc", phase: "setup" }),
    });

    const result = await createSession({
      language: "python",
      topic: "arrays",
      difficulty: "easy",
      max_rounds: 3,
    });

    expect(mockFetch).toHaveBeenCalledWith(
      "/api/sessions",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          language: "python",
          topic: "arrays",
          difficulty: "easy",
          max_rounds: 3,
        }),
      })
    );
    expect(result.session_id).toBe("abc");
  });

  it("submitFix sends POST with fix_code", async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ session_id: "abc", phase: "done" }),
    });

    await submitFix("abc", { fix_code: "def fixed(): pass" });

    expect(mockFetch).toHaveBeenCalledWith(
      "/api/sessions/abc/fix",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ fix_code: "def fixed(): pass" }),
      })
    );
  });

  it("throws on non-ok response", async () => {
    mockFetch.mockResolvedValue({
      ok: false,
      status: 404,
      text: () => Promise.resolve("Not found"),
    });

    await expect(getSession("nonexistent")).rejects.toThrow("API 404");
  });
});
```

#### 17c. `agentx/frontend/app/components/__tests__/TracePanel.test.tsx` (NEW FILE)

```tsx
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { TracePanel } from "../TracePanel";
import { useSessionStore } from "../../stores/session";

// Need to wrap in a test provider or mock the store
describe("TracePanel", () => {
  it("shows empty state when no trace", () => {
    useSessionStore.getState().reset();
    render(<TracePanel />);
    expect(screen.getByText("Waiting for agent activity...")).toBeTruthy();
  });

  it("renders trace events", () => {
    useSessionStore.getState().reset();
    useSessionStore.getState().addTraceEvent({
      phase: "setup",
      agent: "host",
      tool: "fetch_challenge",
      args: { topic: "arrays" },
      result: { ok: true },
      ts: "2026-01-01T00:00:00Z",
    });
    render(<TracePanel />);
    expect(screen.getByText("host")).toBeTruthy();
    expect(screen.getByText("fetch_challenge")).toBeTruthy();
  });
});
```

#### 17d. `agentx/frontend/vitest.config.ts` (NEW FILE, if not existing)

```typescript
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
  },
});
```

#### 17e. `agentx/frontend/package.json`

Add test dependencies:
```json
{
  "devDependencies": {
    "@testing-library/react": "^16.0.0",
    "@testing-library/jest-dom": "^6.0.0",
    "jsdom": "^25.0.0"
  }
}
```

### Dependencies
- Fix 17 is independent. Can be done in parallel with backend fixes.

---

## Fix 18: CORS Not Tightened, `make_llm` Not Cached

### Files to Modify

#### 18a. `agentx/backend/app/main.py`

**Tighten CORS:**

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,  # From config
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)
```

#### 18b. `agentx/backend/app/config.py`

**Add CORS config:**

```python
class Settings(BaseSettings):
    # ... existing ...
    
    # CORS
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]
```

#### 18c. `agentx/backend/app/agents/base.py`

**Cache LLM instances** (this was also mentioned in Fix 3):

```python
_llm_cache: dict[str, ChatOpenAI] = {}

def make_llm(
    model_key: str,
    *,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> ChatOpenAI:
    """Create or return cached ChatOpenAI instance."""
    # Build cache key — temperature affects behavior so include it
    cache_key = f"{model_key}:{temperature}:{max_tokens}"
    
    if cache_key not in _llm_cache:
        model_id = settings.models[model_key]
        temp_map = {
            "host": settings.host_temperature,
            "saboteur": settings.saboteur_temperature,
            "evaluator": settings.evaluator_temperature,
        }
        tokens_map = {
            "host": settings.host_max_tokens,
            "saboteur": settings.saboteur_max_tokens,
            "evaluator": settings.evaluator_max_tokens,
        }
        
        _llm_cache[cache_key] = ChatOpenAI(
            model=model_id,
            api_key=settings.opencode_api_key,
            base_url=settings.opencode_base_url,
            temperature=temperature or temp_map.get(model_key, 0.4),
            max_tokens=max_tokens or tokens_map.get(model_key, 1500),
            timeout=60,
            max_retries=2,
        )
    
    return _llm_cache[cache_key]
```

### Dependencies
- Independent. Quick fixes.

---

# Implementation Order (Dependency-Driven)

| Phase | Fixes | Rationale |
|-------|-------|-----------|
| **Phase A: Foundation** | 5, 9, 18, 6, 7 | Quick fixes, no cross-dependencies. Fix the off-by-one, bug constants, CORS, sandbox limits, Docker images. |
| **Phase B: Write Flow** | 1 (all sub-items) | Core demo fix. Must come before trace/tool work because the flow changes. |
| **Phase C: Tools & Trace** | 3, 4, 8, 2 | Real tools, TracePanel args/results, run_tests, WebSocket streaming. These build on the new flow from Phase B. |
| **Phase D: UI Polish** | 12, 13, 14 | Pickers, diff editor, context projection. These are UX enhancements that build on the working flow. |
| **Phase E: Completeness** | 10, 11 | PDF report, persistence. These round out the feature set. |
| **Phase F: Testing** | 15, 16, 17 | Tests should be written alongside each phase, but bulk test coverage comes here. Update existing tests for new flow. |

---

# Summary of All Files

## New Files (14)
| File | Purpose |
|------|---------|
| `backend/app/tools/inject_bugs.py` | Real tool: bug injection |
| `backend/app/tools/execute_code.py` | Real tool: code execution |
| `backend/app/tools/score_round.py` | Real tool: round scoring |
| `backend/app/tools/run_tests.py` | Real tool: test case execution |
| `backend/app/agents/context.py` | Per-agent context projection |
| `backend/app/reports/pdf_generator.py` | PDF report generation |
| `backend/app/persistence/store.py` | SQLite session persistence |
| `backend/tests/conftest.py` | Shared test fixtures |
| `backend/tests/test_utils.py` | Utility function tests |
| `backend/tests/test_tools.py` | Tool function tests |
| `backend/tests/test_routes.py` | API route tests |
| `frontend/app/stores/__tests__/session.test.ts` | Store tests |
| `frontend/app/lib/__tests__/api.test.ts` | API client tests |
| `frontend/vitest.config.ts` | Vitest configuration |

## Modified Files (18)
| File | Changes |
|------|---------|
| `backend/app/graph/state.py` | Add `student_writing` phase, `original_code_submitted`, `test_cases` |
| `backend/app/graph/builder.py` | Two interrupts, new flow |
| `backend/app/graph/nodes.py` | Write phase, use tools, use context projection |
| `backend/app/graph/edges.py` | Fix off-by-one |
| `backend/app/api/routes.py` | `/write` endpoint, WS streaming, persistence, PDF endpoint |
| `backend/app/tools/__init__.py` | Register all tools |
| `backend/app/sandbox/manager.py` | Subprocess limits, local Docker images |
| `backend/app/utils.py` | Bug count alignment |
| `backend/app/agents/base.py` | LLM caching |
| `backend/app/config.py` | Remove unused bug constants, add CORS, sandbox images |
| `backend/app/main.py` | Tighten CORS |
| `backend/app/prompts/saboteur.py` | Align bug count text (already correct) |
| `frontend/app/App.tsx` | Config state, pass to SessionPage |
| `frontend/app/pages/SessionPage.tsx` | Write flow, config props, diff view, WS handling |
| `frontend/app/pages/HomePage.tsx` | Language/topic/difficulty pickers |
| `frontend/app/components/CodeEditor.tsx` | Diff mode, student_writing phase |
| `frontend/app/components/TracePanel.tsx` | Expandable args/result display |
| `frontend/app/lib/types.ts` | New types for write flow |
| `frontend/app/lib/api.ts` | New API functions |
| `frontend/app/stores/session.ts` | Language/topic state, new setters |
| `frontend/app/hooks/useWebSocket.ts` | Reconnection, keepalive |
| `backend/tests/test_graph.py` | Update for new flow, tighter assertions |
| `backend/pyproject.toml` | Add reportlab |
| `frontend/package.json` | Add test deps |
| `Dockerfile` | Sandbox build targets |
| `docker-compose.yml` | Sandbox services |
