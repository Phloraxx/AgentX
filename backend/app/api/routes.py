"""FastAPI routes — session management and WebSocket streaming."""

import asyncio
import json
import logging
import threading
import uuid
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from app.graph.builder import build_graph
from app.graph.nodes import set_emit_callback_for_session
from app.persistence.store import save_session, load_session, update_session, list_sessions
from app.reports.pdf_generator import generate_session_report

logger = logging.getLogger(__name__)
router = APIRouter()
_session_queues: dict[str, asyncio.Queue] = {}

# Compiled graph (shared across requests)
_graph = None


def get_graph():
    """Get or build the LangGraph."""
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph


class SessionCreate(BaseModel):
    language: str = "python"
    topic: str = "arrays"
    difficulty: str = "easy"
    max_rounds: int = 3


class FixSubmit(BaseModel):
    fix_code: str

class OriginalCodeSubmit(BaseModel):
    original_code: str

class SessionResponse(BaseModel):
    session_id: str
    phase: str = 'setup'
    language: str = 'python'
    topic: str = 'arrays'
    difficulty: str = 'easy'
    round_num: int = 0
    challenge: str = ''
    original_code: str = ''
    buggy_code: str = ''
    chat: list[dict] = []
    trace: list[dict] = []
    score: Optional[dict] = None


# In-memory session store with LRU eviction (would be Appwrite in production)
_sessions: OrderedDict[str, dict] = OrderedDict()
_SESSIONS_MAX = 200

def _touch_session(sid: str):
    if sid in _sessions:
        _sessions.move_to_end(sid)

def _add_session(sid: str, val: dict):
    _sessions[sid] = val
    _sessions.move_to_end(sid)
    while len(_sessions) > _SESSIONS_MAX:
        _sessions.popitem(last=False)


@router.post("/api/sessions", response_model=SessionResponse)
def create_session(req: SessionCreate):
    """Create a new training session and start the graph.

    Sync endpoint — graph.invoke() blocks during LLM calls.
    """
    session_id = str(uuid.uuid4())[:8]
    graph = get_graph()
    config = {"configurable": {"thread_id": session_id}}

    initial_state = {
        "session_id": session_id,
        "language": req.language,
        "topic": req.topic,
        "difficulty": req.difficulty,
        "round_num": 0,
        "max_rounds": req.max_rounds,
        "phase": "setup",
        "original_code_submitted": False,
        "current_round": {
            "round_num": 0,
            "challenge": "",
            "original_code": "",
            "buggy_code": "",
            "fix_code": "",
            "bug_manifest": [],
            "test_cases": [],
            "original_exec": None,
            "buggy_exec": None,
            "fix_exec": None,
            "score": None,
            "difficulty_in": req.difficulty,
            "difficulty_out": req.difficulty,
        },
        "rounds": [],
        "chat": [],
        "trace": [],
        "error": None,
    }

    # Run graph until interrupt (before student_fix_await)
    try:
        result = graph.invoke(initial_state, config)
    except Exception as e:
        logger.error(f"Graph initial invoke error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    # Store session state in memory and persist to SQLite
    created_at = datetime.now(timezone.utc).isoformat()
    _add_session(session_id, {
        "state": result,
        "config": config,
        "created_at": created_at,
    })
    save_session(session_id, result, config, created_at)

    return {
        "session_id": session_id,
        "phase": result.get("phase"),
        "language": result.get("language", ""),
        "topic": result.get("topic", ""),
        "difficulty": req.difficulty,
        "round_num": result.get("round_num", 0),
        "challenge": result.get("current_round", {}).get("challenge", ""),
        "original_code": result.get("current_round", {}).get("original_code", ""),
        "buggy_code": result.get("current_round", {}).get("buggy_code", ""),
        "chat": result.get("chat", []),
        "trace": result.get("trace", []),
        "score": None,
    }


@router.post("/api/sessions/{session_id}/fix", response_model=SessionResponse)
def submit_fix(session_id: str, req: FixSubmit):
    """Submit a student's fix and resume the graph.

    Sync endpoint — graph.invoke() blocks during LLM calls.
    """
    _touch_session(session_id)
    if session_id not in _sessions:
        stored = load_session(session_id)
        if stored is None:
            raise HTTPException(status_code=404, detail='Session not found')
        _sessions[session_id] = {'state': stored['state'], 'config': stored['config'], 'created_at': stored.get('created_at', '')}
        raise HTTPException(status_code=409, detail='Session restored from disk but cannot resume an interrupted round after server restart. Start a new session.')

    if not req.fix_code.strip():
        raise HTTPException(status_code=400, detail="fix_code cannot be empty")

    session = _sessions[session_id]
    graph = get_graph()
    config = session["config"]

    # Update state with the fix
    current_round = session["state"].get("current_round", {})
    graph.update_state(config, {
        "current_round": {**current_round, "fix_code": req.fix_code}
    })

    # Resume graph
    try:
        result = graph.invoke(None, config)
    except Exception as e:
        logger.error(f"Graph resume error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    # Update stored state (memory + SQLite)
    session["state"] = result
    update_session(session_id, result)

    # Score lives in rounds[] after adjust archives it, or in current_round if session ended
    rounds = result.get("rounds", [])
    score = rounds[-1].get("score") if rounds else result.get("current_round", {}).get("score")
    return {
        "session_id": session_id,
        "phase": result.get("phase"),
        "language": result.get("language", ""),
        "topic": result.get("topic", ""),
        "score": score,
        "chat": result.get("chat", []),
        "trace": result.get("trace", []),
        "round_num": result.get("round_num"),
        "difficulty": result.get("difficulty"),
        "challenge": result.get("current_round", {}).get("challenge", ""),
        "original_code": result.get("current_round", {}).get("original_code", ""),
        "buggy_code": result.get("current_round", {}).get("buggy_code", ""),
    }


@router.post("/api/sessions/{session_id}/write", response_model=SessionResponse)
def submit_original_code(session_id: str, req: OriginalCodeSubmit):
    """Submit student's original code, then resume graph past saboteur_inject interrupt."""
    _touch_session(session_id)
    if session_id not in _sessions:
        stored = load_session(session_id)
        if stored is None:
            raise HTTPException(status_code=404, detail='Session not found')
        _sessions[session_id] = {'state': stored['state'], 'config': stored['config'], 'created_at': stored.get('created_at', '')}
        raise HTTPException(status_code=409, detail='Session restored from disk but cannot resume an interrupted round after server restart. Start a new session.')
    if not req.original_code.strip():
        raise HTTPException(status_code=400, detail="original_code cannot be empty")

    session = _sessions[session_id]
    graph = get_graph()
    config = session["config"]

    # Update state with the student's original code
    current_round = session["state"].get("current_round", {})
    graph.update_state(config, {
        "current_round": {
            **current_round,
            "original_code": req.original_code,
            "original_code_submitted": True,
        },
        "original_code_submitted": True,
    })

    # Resume graph — runs saboteur_inject, then interrupts before student_fix_await
    try:
        result = graph.invoke(None, config)
    except Exception as e:
        logger.error(f"Graph resume error (write): {e}")
        raise HTTPException(status_code=500, detail=str(e))

    # Update stored state
    session["state"] = result
    update_session(session_id, result)

    rounds = result.get("rounds", [])
    score = rounds[-1].get("score") if rounds else result.get("current_round", {}).get("score")

    return {
        "session_id": session_id,
        "phase": result.get("phase"),
        "language": result.get("language", ""),
        "topic": result.get("topic", ""),
        "score": score,
        "chat": result.get("chat", []),
        "trace": result.get("trace", []),
        "round_num": result.get("round_num"),
        "difficulty": result.get("difficulty"),
        "challenge": result.get("current_round", {}).get("challenge", ""),
        "original_code": result.get("current_round", {}).get("original_code", ""),
        "buggy_code": result.get("current_round", {}).get("buggy_code", ""),
    }



@router.get("/api/sessions/{session_id}", response_model=SessionResponse)
def get_session(session_id: str):
    """Get current session state."""
    _touch_session(session_id)
    if session_id not in _sessions:
        stored = load_session(session_id)
        if stored is None:
            raise HTTPException(status_code=404, detail='Session not found')
        _sessions[session_id] = {'state': stored['state'], 'config': stored['config'], 'created_at': stored.get('created_at', '')}
    state = _sessions[session_id]['state']

    return {
        "session_id": session_id,
        "phase": state.get("phase"),
        "language": state.get("language", ""),
        "topic": state.get("topic", ""),
        "round_num": state.get("round_num"),
        "difficulty": state.get("difficulty"),
        "challenge": state.get("current_round", {}).get("challenge", ""),
        "original_code": state.get("current_round", {}).get("original_code", ""),
        "buggy_code": state.get("current_round", {}).get("buggy_code", ""),
        "chat": state.get("chat", []),
        "trace": state.get("trace", []),
        "score": state.get("current_round", {}).get("score"),
    }


@router.get("/api/sessions")
def get_all_sessions():
    """List all stored sessions (metadata only)."""
    return {"sessions": list_sessions()}


@router.get("/api/sessions/{session_id}/report")
def get_session_report(session_id: str):
    """Generate and return a PDF report for a completed session.

    Tries the in-memory cache first, then falls back to SQLite persistence.
    """
    # Try in-memory cache first
    session = _sessions.get(session_id)
    if session is not None:
        state = session["state"]
        state["created_at"] = session.get("created_at", "")
    else:
        # Fall back to SQLite
        stored = load_session(session_id)
        if stored is None:
            raise HTTPException(status_code=404, detail="Session not found")
        state = stored["state"]
        state["created_at"] = stored.get("created_at", "")

    try:
        pdf_bytes = generate_session_report(state)
    except Exception as e:
        logger.error(f"PDF generation error for session {session_id}: {e}")
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {e}")

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="agentx-report-{session_id}.pdf"'
        },
    )



# --- WebSocket for real-time streaming ---


@router.websocket("/ws/{session_id}")
async def websocket_session(websocket: WebSocket, session_id: str):
    """WebSocket endpoint for real-time graph event streaming."""
    await websocket.accept()
    if session_id not in _sessions:
        await websocket.send_json({"type": "error", "message": "Session not found"})
        await websocket.close()
        return

    event_queue: asyncio.Queue = asyncio.Queue(maxsize=100)
    _session_queues[session_id] = event_queue

    loop = asyncio.get_running_loop()
    def _emit(event: dict):
        try:
            loop.call_soon_threadsafe(event_queue.put_nowait, event)
        except Exception:
            pass

    set_emit_callback_for_session(session_id, _emit)

    try:
        session = _sessions[session_id]
        state = session['state']
        await websocket.send_json({
            "type": "state",
            "phase": state.get("phase"),
            "round_num": state.get("round_num"),
        })
        while True:
            try:
                event = await asyncio.wait_for(event_queue.get(), timeout=30)
                await websocket.send_json(event)
                if event.get("type") in ("result", "error"):
                    break
            except asyncio.TimeoutError:
                await websocket.send_json({"type": "ping"})
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected: {session_id}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        _session_queues.pop(session_id, None)
        set_emit_callback_for_session(session_id, None)

