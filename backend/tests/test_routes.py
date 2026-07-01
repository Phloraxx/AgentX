"""Tests for API routes: health, session CRUD, fix submission."""

import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from main import app


@pytest.fixture
def client():
    return TestClient(app)


class TestHealth:
    """Health endpoint returns 200 with service metadata."""

    def test_health_returns_200(self, client):
        response = client.get("/health")
        assert response.status_code == 200

    def test_health_response_shape(self, client):
        data = client.get("/health").json()
        assert data["status"] == "ok"
        assert data["service"] == "agentx"
        assert "version" in data


class TestCreateSession:
    """POST /api/sessions creates a session and runs the graph."""

    @patch("app.api.routes.get_graph")
    def test_create_session_success(self, mock_get_graph, client):
        mock_graph = MagicMock()
        mock_graph.invoke.return_value = {
            "session_id": "test-001",
            "phase": "student_fixing",
            "round_num": 0,
            "difficulty": "easy",
            "current_round": {
                "challenge": "Two Sum",
                "original_code": "def two_sum(nums, target):\n    pass",
                "buggy_code": "",
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
        assert data["phase"] in ("student_fixing", "student_writing")
        assert "challenge" in data
        assert "chat" in data
        assert "trace" in data

    @patch("app.api.routes.get_graph")
    def test_create_session_default_params(self, mock_get_graph, client):
        mock_graph = MagicMock()
        mock_graph.invoke.return_value = {
            "session_id": "test-002",
            "phase": "student_fixing",
            "current_round": {"challenge": "", "original_code": "", "buggy_code": ""},
            "rounds": [],
            "chat": [],
            "trace": [],
        }
        mock_get_graph.return_value = mock_graph

        # Empty body should use defaults
        response = client.post("/api/sessions", json={})
        assert response.status_code == 200
        data = response.json()
        assert "session_id" in data

    @patch("app.api.routes.get_graph")
    def test_create_session_graph_error_returns_500(self, mock_get_graph, client):
        mock_graph = MagicMock()
        mock_graph.invoke.side_effect = RuntimeError("LLM connection failed")
        mock_get_graph.return_value = mock_graph

        response = client.post("/api/sessions", json={
            "language": "python",
            "topic": "arrays",
            "difficulty": "easy",
        })
        assert response.status_code == 500

    @patch("app.api.routes.get_graph")
    def test_create_session_includes_language_topic(self, mock_get_graph, client):
        mock_graph = MagicMock()
        mock_graph.invoke.return_value = {
            'session_id': 'test-001',
            'phase': 'student_writing',
            'language': 'javascript',
            'topic': 'strings',
            'difficulty': 'easy',
            'round_num': 0,
            'challenge': 'Test challenge',
            'original_code': '',
            'buggy_code': '',
            'chat': [],
            'trace': [],
            'rounds': [],
            'error': None,
            'current_round': {},
            'max_rounds': 3,
            'original_code_submitted': False,
        }
        mock_get_graph.return_value = mock_graph
        response = client.post('/api/sessions', json={'language': 'javascript', 'topic': 'strings', 'difficulty': 'medium'})
        assert response.status_code == 200
        data = response.json()
        assert data['language'] == 'javascript'
        assert data['topic'] == 'strings'


class TestGetSession:
    """GET /api/sessions/{session_id} returns session state."""

    def test_get_nonexistent_session_returns_404(self, client):
        response = client.get("/api/sessions/nonexistent")
        assert response.status_code == 404

    def test_get_session_response_shape(self, client, sample_state):
        # Manually inject a session into the in-memory store
        from app.api.routes import _sessions
        session_id = "test-get-001"
        _sessions[session_id] = {
            "state": sample_state,
            "config": {"configurable": {"thread_id": session_id}},
            "created_at": "2026-01-01T00:00:00Z",
        }
        try:
            response = client.get(f"/api/sessions/{session_id}")
            assert response.status_code == 200
            data = response.json()
            assert data["session_id"] == session_id
            assert "phase" in data
            assert "round_num" in data
            assert "difficulty" in data
            assert "chat" in data
            assert "trace" in data
        finally:
            _sessions.pop(session_id, None)


class TestSubmitFix:
    """POST /api/sessions/{session_id}/fix submits student fix."""

    def test_submit_fix_nonexistent_session_returns_404(self, client):
        response = client.post("/api/sessions/nonexistent/fix", json={
            "fix_code": "def fixed(): pass",
        })
        assert response.status_code == 404

    def test_submit_fix_empty_code_still_404_before_validation(self, client):
        # Session not found error takes precedence over empty code validation
        response = client.post("/api/sessions/nonexistent/fix", json={
            "fix_code": "",
        })
        assert response.status_code == 404

    @patch("app.api.routes.update_session")
    @patch("app.api.routes.get_graph")
    def test_submit_fix_success(self, mock_get_graph, mock_update_session, client, sample_buggy_state):
        from app.api.routes import _sessions

        session_id = "test-fix-001"
        mock_graph = MagicMock()
        mock_graph.invoke.return_value = {
            **sample_buggy_state,
            "phase": "round_complete",
            "current_round": {
                **sample_buggy_state["current_round"],
                "score": {
                    "bugs_fixed": 1,
                    "bugs_total": 1,
                    "code_quality": 0.9,
                    "speed_bonus": 0.8,
                    "total": 85,
                },
            },
        }
        mock_get_graph.return_value = mock_graph

        _sessions[session_id] = {
            "state": sample_buggy_state,
            "config": {"configurable": {"thread_id": session_id}},
            "created_at": "2026-01-01T00:00:00Z",
        }
        try:
            response = client.post(f"/api/sessions/{session_id}/fix", json={
                "fix_code": "def two_sum(nums, target):\n    seen = {}\n    for i, num in enumerate(nums):\n        comp = target - num\n        if comp in seen:\n            return [seen[comp], i]\n        seen[num] = i\n    return []",
            })
            assert response.status_code == 200
            data = response.json()
            assert data["session_id"] == session_id
            assert data["phase"] == "round_complete"
            assert data["score"]["total"] == 85
            assert "chat" in data
        finally:
            _sessions.pop(session_id, None)
