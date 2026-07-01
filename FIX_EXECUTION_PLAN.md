# AgentX Audit Fix — Execution Plan

**28 findings** across 4 priorities, executed in **3 waves** of **6 parallel tracks**.

---

## Execution Model

| Wave | Tracks | Parallel? | Files |
|------|--------|-----------|-------|
| **Wave 1** | T1 + T2 + T3 + T4 | ✅ 4-way parallel | Disjoint file clusters, no conflicts |
| **Wave 2** | T5 + T6-backend | ✅ 2-way parallel | Frontend files vs test files |
| **Wave 3** | T6-frontend | Sequential | Vitest tests after frontend merges |

## Cross-Track Contracts (Wave 1)

All HTTP responses MUST include: `session_id, phase, language, topic, difficulty, round_num, challenge, original_code, buggy_code, chat[], trace[], score|null`

Frontend store keys: camelCase (`sessionId`, `roundNum`, `originalCode`, etc.)

T1 ↔ T2: T1 exposes `set_emit_callback_for_session(session_id, cb)` in nodes.py; T2 calls it per-session with `loop.call_soon_threadsafe`.

T1 ↔ T3: T3 adds `used: list[str] = None` param to `_fallback_challenge`; T1 calls with 4-arg form for challenge de-dup.

---

## T1 — Backend Graph (P0-1, P0-3, P2-16, P2-17, P2-18)

**Files:** `state.py`, `edges.py`, `builder.py`, `nodes.py`

### P0-1: Finish node — session end invisible
- **state.py**: Add `used_challenges: list[str]` to `SessionState`
- **edges.py**: Delete `has_fix_submitted` (dead code — P2-16)
- **builder.py**: Add `finish` node, wire `round_or_done → finish → END`
- **nodes.py**: Add `finish()` function returning `phase: 'done'` + terminal chat message

### P0-3: Surface LLM/tool failures
- **nodes.py** `saboteur_inject`: On `ok:False` or except → revert to `phase: 'student_writing'` + append `role:'system'` error chat
- **nodes.py** `host_setup`: On no tool call → append system warning chat
- **nodes.py** `evaluator_score`: On failure → append system warning chat

### P2-18: host_setup fallback
- **nodes.py**: When Host LLM doesn't call tool → use `_fallback_challenge()` instead of raw LLM text

### P2-17: Challenge de-dup
- **nodes.py**: Record `used_challenges` in state, pass to fallback selector
- **state.py**: `used_challenges` field (done in P0-1)

### P1-6 (contract): Session-keyed emit
- **nodes.py**: Replace global `_emit_callback` with `_emit_callbacks_by_session` dict; add `set_emit_callback_for_session()`; `_trace_and_emit` resolves callback from `state['session_id']`

---

## T2 — Backend API (P0-2, P1-10, P1-13, P1-14, P1-6, P3-24)

**Files:** `routes.py`, `store.py`

### P0-2: Language/topic in responses
- Add `'language'` and `'topic'` to every endpoint's return dict

### P1-13: Pydantic response models
- Add `SessionResponse`, `FixResponse`, `WriteResponse`, `SessionDetailResponse` models
- Apply `response_model=` to each route decorator

### P1-6: Thread-safe WebSocket streaming
- Replace global `_emit_callback` with per-session `_emit_callbacks` dict
- Use `loop.call_soon_threadsafe()` for cross-thread Queue.put
- Call `set_emit_callback_for_session()` from T1 contract

### P1-14: Lazy queue creation
- Replace `defaultdict(asyncio.Queue)` with plain dict; create Queue in WS handler only

### P1-10: SQLite rehydration on restart
- `get_session`: fallback to `load_session()` from SQLite
- `submit_fix`/`submit_original_code`: return 409 if session from SQLite but graph checkpoint lost
- Document: GET survives restart, resume does not

### P3-24: Bounded session store
- Replace `_sessions` dict with `OrderedDict`, cap at 200 entries
- SQLite: prune rows older than 30 days in `list_sessions()`

---

## T3 — Backend Tools & Sandbox (P1-7, P1-8, P1-11, P1-12, P3-23, P3-25, P3-26)

**Files:** `utils.py`, `run_tests.py`, `inject_bugs.py`, `manager.py`, `base.py`

### P1-7: validate_compiles JS always returns True
- Fix `node -e` to use `process.argv[2]` (or `node --check`)

### P1-12: apply_bugs silent no-op
- After applying, count matched bugs; return `ok:False` if `applied < len(bugs)`

### P3-26: parse_json_response greedy regex
- Tighten `\{.*\}` regex or add early return for structured output

### P1-8: run_tests_tool always 0/N
- Fix test runner to actually call the student's function
- Generate assertion-style tests: `assert two_sum([2,7,11,15],9)==[0,1]`

### P1-11: _docker_available cache never resets
- Set `self._docker_available = None` on exception in `_run_docker`

### P3-23: os.unlink NameError risk
- Wrap in try/except or guard with `if 'path' in locals()`

### P3-25: Sandbox concurrency cap
- Add `threading.Semaphore(4)` around `run()`

### P2-17 (contract): Challenge de-dup selector
- Add optional `used: list[str] = None` param to `_fallback_challenge()`

### P3-24: LLM cache cap
- Cap `_llm_cache` at reasonable size (already bounded in practice)

---

## T4 — Infra (P0-4, P1-5, P2-19, P2-21, P3-27)

**Files:** `Dockerfile`, `docker-compose.yml`, `config.py`, `.gitignore`

### P0-4: Sandbox security (docker.sock + non-root)
- Remove `USER agentx` from Dockerfile (run as root for demo)
- Add sandbox image build services to docker-compose
- Pre-build sandbox images on host

### P1-5: Sandbox images never built
- Add `sandbox-python` and `sandbox-node` services to docker-compose
- Use `target:` in build config

### P2-19: Committed frontend/dist/
- Delete `frontend/dist/` from VCS
- Add to `.gitignore`

### P2-21: CORS for deployed origin
- Add env var `ALLOWED_ORIGINS` to config.py

### P3-27: demo_check.py not wired
- Add startup check or healthcheck improvement

---

## T5 — Frontend (P0-1, P0-2, P0-3, P1-9, P2-15, P2-20)

**Files:** `SessionPage.tsx`, `session.ts`, `CodeEditor.tsx`, `types.ts`, `api.ts`, `ChatPanel.tsx`

### P0-1: Session completion UI + report download
- When `phase === 'done'`: show "Session Complete" banner
- Add `<a href="/api/sessions/{id}/report" download>` button
- Add "Play Again" button

### P0-2: Language reaches editor
- `session.ts`: `init()` sets `language`/`topic` from response
- `SessionPage.tsx`: Pass `language={config.language}` to CodeEditor
- `CodeEditor.tsx`: Read language from store

### P0-3: Surface errors in chat
- `ChatPanel.tsx`: Render `role: 'system'` messages with warning styling
- Add toast/error notification for failures

### P1-9: Stale fixCode across rounds
- `session.ts`: Reset `fixCode: ""` when phase transitions to `student_writing`

### P2-15: Wire diff editor
- Show original-vs-buggy diff during `student_fixing` phase

### P2-20: Loading overlay
- Add spinner during long synchronous calls (`executing_*`, `evaluating`)
- Disable editor during non-editable phases

---

## T6 — Tests

### Wave 2: Backend tests
- Fix `test_stub_round_completes` (remove xfail, assert `phase == 'done'`)
- Delete `test_has_fix_submitted_*` tests
- Update route tests for new response models
- Add SQLite rehydration test

### Wave 3: Frontend tests
- Add vitest tests for `useSessionStore` (init/updateFromResult/reset)
- Add `useWebSocket` reconnect test
- Add `SessionPage` render tests per phase

---

## Dependency Chain

```
Wave 1 (parallel): T1 + T2 + T3 + T4
    ↓
Wave 2 (parallel): T5 (frontend) + T6-backend
    ↓
Wave 3: T6-frontend
```

**Critical path:** T1 (finish node) → T5 (completion UI) → T6-frontend (vitest)
