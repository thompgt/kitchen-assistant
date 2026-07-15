"""FastAPI TestClient coverage for the /ws/voice/{session_id} route itself.

Complements test_gateway.py (which exercises LiveGateway directly) by
proving the actual route wires a fresh LiveGateway per connection and that
the browser-facing WS protocol round-trips through the real ASGI app, with
LiveGateway's real-Live connect factory swapped for a fake one — no network
or API key required.
"""
import json
from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

import app.main as main_module
from app.live.gateway import LiveGateway
from tests.test_gateway import FakeLiveSession, _ConnectCM, make_message, make_tool_call


@contextmanager
def _websocket_session(path: str):
    """websocket_connect, tolerating the benign portal-teardown race where the
    fake session's blocked receive() is still being cancelled when TestClient's
    background ASGI thread winds down after the assertions already ran."""
    cm = TestClient(main_module.app).websocket_connect(path)
    ws = cm.__enter__()
    try:
        yield ws
    finally:
        try:
            cm.__exit__(None, None, None)
        except Exception:
            pass


def test_websocket_route_ready_status_and_tool_dispatch(monkeypatch) -> None:
    session = FakeLiveSession(
        messages=[
            make_message(
                tool_call=make_tool_call(
                    id="call-1",
                    name="set_kitchen_timer",
                    args={"duration_seconds": 30, "label": "eggs"},
                )
            )
        ],
        block_after=True,
    )

    def fake_factory(self) -> _ConnectCM:
        return _ConnectCM(session)

    monkeypatch.setattr(LiveGateway, "_default_connect_factory", fake_factory)

    with _websocket_session("/ws/voice/route-test-1") as ws:
        envelopes = []
        for _ in range(2):
            envelopes.append(json.loads(ws.receive_text()))

    types_seen = {e["type"] for e in envelopes}
    assert {"session.status", "state.snapshot"} <= types_seen

    ready = next(e for e in envelopes if e["type"] == "session.status")
    assert ready["status"] == "ready"

    [response] = session.sent_tool_responses[0]
    assert response.name == "set_kitchen_timer"
    assert response.response["status"] == "success"


def test_websocket_route_forwards_interrupted(monkeypatch) -> None:
    session = FakeLiveSession(
        messages=[
            make_message(server_content=SimpleNamespace(
                interrupted=True,
                input_transcription=None,
                output_transcription=None,
                model_turn=None,
            ))
        ],
        block_after=True,
    )

    def fake_factory(self) -> _ConnectCM:
        return _ConnectCM(session)

    monkeypatch.setattr(LiveGateway, "_default_connect_factory", fake_factory)

    with _websocket_session("/ws/voice/route-test-2") as ws:
        envelopes = [json.loads(ws.receive_text()) for _ in range(2)]

    assert envelopes[0] == {"type": "session.status", "status": "ready"}
    assert envelopes[1] == {"type": "interrupted"}


def test_websocket_route_rejects_missing_or_wrong_token(monkeypatch) -> None:
    monkeypatch.setenv("APP_AUTH_TOKEN", "secret-123")
    session = FakeLiveSession(block_after=True)

    def fake_factory(self) -> _ConnectCM:
        return _ConnectCM(session)

    monkeypatch.setattr(LiveGateway, "_default_connect_factory", fake_factory)

    with pytest.raises(WebSocketDisconnect) as exc_info:
        with _websocket_session("/ws/voice/route-test-3") as ws:
            ws.receive_text()
    assert exc_info.value.code == 4001


def test_websocket_route_accepts_correct_token(monkeypatch) -> None:
    monkeypatch.setenv("APP_AUTH_TOKEN", "secret-123")
    session = FakeLiveSession(block_after=True)

    def fake_factory(self) -> _ConnectCM:
        return _ConnectCM(session)

    monkeypatch.setattr(LiveGateway, "_default_connect_factory", fake_factory)

    with _websocket_session("/ws/voice/route-test-4?token=secret-123") as ws:
        envelope = json.loads(ws.receive_text())
    assert envelope == {"type": "session.status", "status": "ready"}
