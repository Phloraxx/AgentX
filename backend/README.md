# AgentX Backend

FastAPI + LangGraph backend for the AgentX debugging trainer.

See [`../docs/RUNBOOK.md`](../docs/RUNBOOK.md) for setup, deployment, and
the session loop.

## Quick start

```bash
poetry install
cp ../.env.example .env   # then fill in OPENCODE_API_KEY + EXA_API_KEY
poetry run uvicorn main:app --reload --port 8000
poetry run python demo_check.py   # pre-flight: LLM, Exa, Docker, graph
```

## Tests

```bash
poetry run pytest
```
