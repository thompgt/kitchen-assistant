"""FastAPI TestClient coverage for the /ws/voice/{session_id} route itself.

Complements test_gateway.py (which exercises LiveGateway directly) by
proving the actual route wires a fresh LiveGateway per connection and that
the browser-facing WS protocol round-trips through the real ASGI app, with
LiveGateway's real-Live connect factory swapped for a fake one — no network
or API key required.
"""
import json
from types import SimpleNamespace

from fastapi.testclient import TestClient

import app.main as main_module
from app.live.gateway import LiveGateway
from tests.test_gateway import FakeLiveSession, _ConnectCM, make_message, make_tool_call


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

    with TestClient(main_module.app).websocket_connect("/ws/voice/route-test-1") as ws:
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

    with TestClient(main_module.app).websocket_connect("/ws/voice/route-test-2") as ws:
        envelopes = [json.loads(ws.receive_text()) for _ in range(2)]

    assert envelopes[0] == {"type": "session.status", "status": "ready"}
    assert envelopes[1] == {"type": "interrupted"}
