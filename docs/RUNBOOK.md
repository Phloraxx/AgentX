# AgentX — Runbook

AgentX is a "Write → Sabotage → Fix" debugging trainer. Three LLM agents
(Host, Saboteur, Evaluator) drive a LangGraph loop: the Host fetches a real
coding challenge, the student writes a solution, the Saboteur injects bugs,
the student fixes them, and the Evaluator scores the round. A React + Monaco
frontend streams graph events over WebSocket; SQLite persists sessions; a PDF
report can be downloaded at session end.

---

## 1. Prerequisites

| Requirement | Why |
|---|---|
| Docker (with daemon running) | Isolated sandbox for student code execution |
| Python 3.11+ | Backend |
| Node 20+ | Frontend build |
| OpenCode Go API key | Host / Saboteur / Evaluator LLMs |
| Exa API key | Live challenge fetch (falls back to hardcoded problems if absent) |

Without Docker, the sandbox degrades to a subprocess fallback with resource
limits (Linux only). Without Exa, challenge fetch uses `_fallback_challenge`.

## 2. Configuration

All secrets/env live in `backend/.env` (or Dokploy env vars). Copy
`.env.example` and fill in:

```
OPENCODE_API_KEY=sk-...          # REQUIRED — OpenCode Go
EXA_API_KEY=...                  # REQUIRED for live fetch (fallback otherwise)
ALLOWED_ORIGINS=https://agentx.phloraxx.us.to,http://localhost:5173
# DOCKER_HOST=unix:///var/run/docker.sock   # optional
```

Model IDs and agent params are set in `backend/app/config.py`.

## 3. Local development

```bash
# Backend (from backend/)
poetry install
poetry run uvicorn main:app --reload --port 8000

# Frontend (from frontend/) — Vite proxies /api + /ws to :8000
npm install
npm run dev
```

Open http://localhost:5173.

## 4. Pre-flight check

```bash
# From backend/ — verifies LLM, Exa key, Docker sandbox, LangGraph, FastAPI
poetry run python demo_check.py
```

The same checks run non-blocking at server startup and are exposed at:

```
GET /health         # liveness — always 200
GET /health/ready   # readiness — per-service preflight status
```

## 5. Docker deployment (Dokploy / Compose)

```bash
docker compose up -d --build
```

This builds:
- `agentx-sandbox-python:latest` — Python execution image
- `agentx-sandbox-node:latest` — Node execution image
- `agentx` — FastAPI serving the built frontend on :8000

Set env vars in Dokploy (or `.env`): `OPENCODE_API_KEY`, `EXA_API_KEY`,
`ALLOWED_ORIGINS`. The `docker.sock` is mounted so the app can spawn sandbox
containers.

## 6. The session loop

```
host_setup → host_present → [interrupt: student writes code]
→ saboteur_inject → [interrupt: student submits fix]
→ host_run_fix → evaluator_score → adjust (loop) | finish → END
```

- `POST /api/sessions` — create + run until first interrupt (`student_writing`)
- `POST /api/sessions/{id}/write` — submit original code → run saboteur → interrupt (`student_fixing`)
- `POST /api/sessions/{id}/fix` — submit fix → score → next round or `done`
- `GET  /api/sessions/{id}/report` — PDF report (all rounds, including the final one)
- `WS   /ws/{session_id}` — real-time trace/chat events

On session completion (`phase === 'done'`) the frontend shows a **Download
Report** link and a **Play Again** button.

## 7. Persistence

- In-memory: `OrderedDict` LRU capped at 200 sessions.
- SQLite: `backend/data/sessions.db` — survives restarts for `GET`/report.
- Resume after restart: `GET` works; `fix`/`write` return **409** (graph
  checkpoint is in-memory `MemorySaver`, not restored from SQLite).

## 8. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| LLM calls fail at runtime | placeholder `OPENCODE_API_KEY` | set real key in `.env`/Dokploy |
| Sandbox always "fallback" | Docker not running / sandbox images missing | start Docker, run `docker compose build sandbox-python sandbox-node` |
| `exa-key` warn at boot | placeholder Exa key | live fetch disabled; fallback challenges used |
| `fix`/`write` return 409 | server restarted mid-session | start a new session (checkpoint is in-memory) |
| PDF shows "No rounds completed" | (fixed) finish node now archives the final round | ensure backend is rebuilt |

## 9. Architecture map

```
backend/
  main.py                      FastAPI entry, lifespan preflight, SPA serve
  app/
    config.py                  env + model IDs
    api/routes.py              session CRUD, WebSocket, PDF report
    graph/                     LangGraph: builder, nodes, edges, state
    agents/base.py            LLM factory (3 models, one endpoint)
    tools/                    fetch_challenge, inject_bugs, run_tests,
                              score_round, execute_code (all @tool)
    sandbox/manager.py        Docker SDK sandbox + subprocess fallback
    persistence/store.py      SQLite save/load/update/list
    reports/pdf_generator.py  reportlab PDF
    utils.py                  JSON parse, apply_bugs, validate_compiles, preflight
frontend/
  app/                        React + Zustand + Monaco, Vite
sandbox-images/               python / javascript Dockerfiles
docker-compose.yml            sandbox-python, sandbox-node, agentx
```
