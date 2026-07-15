"""LiveGateway tests against a fake Live backend.

Real `client.aio.live.connect(...)` is never touched: the connect-factory
seam (Phase 2) is fed fake sessions here so the whole protocol — tool
dispatch, `interrupted`/transcript/audio forwarding, resumption-handle
capture, GoAway-triggered reconnect — is exercised with no network or API
key, matching the Phase 6 "no secrets needed" CI goal.
"""
import asyncio
import base64
import json
from datetime import datetime
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

from app.live.gateway import LiveGateway
from app.schemas import KitchenTimer
from app.state_manager import StateManager
from app.tools.registry import ToolRegistry


class FakeWebSocket:
    def __init__(self) -> None:
        self.sent_text: List[str] = []
        self.sent_bytes: List[bytes] = []

    async def send_text(self, text: str) -> None:
        self.sent_text.append(text)

    async def send_bytes(self, data: bytes) -> None:
        self.sent_bytes.append(data)


class FakeSession:
    def __init__(self) -> None:
        self.sent_realtime: List[Dict[str, Any]] = []

    async def send_realtime_input(self, **kwargs: Any) -> None:
        self.sent_realtime.append(kwargs)


def _make_gateway(state_manager: StateManager, ws: FakeWebSocket) -> LiveGateway:
    registry = ToolRegistry(state_manager)
    return LiveGateway(
        websocket=ws, session_id="s1", state_manager=state_manager, registry=registry
    )


def _expired_timer() -> KitchenTimer:
    return KitchenTimer(
        id="t1",
        label="eggs",
        duration_seconds=1,
        start_time=datetime.now(),
        remaining_seconds=0,
        is_active=False,
    )


async def test_on_timer_expired_notifies_browser_and_nudges_model(
    state_manager: StateManager,
) -> None:
    ws = FakeWebSocket()
    gateway = _make_gateway(state_manager, ws)
    session = FakeSession()
    gateway._session = session
    await state_manager.get_or_create_state("s1")  # snapshot only sends for known sessions

    await gateway._on_timer_expired(_expired_timer())

    envelopes = [json.loads(text) for text in ws.sent_text]
    assert {"type": "timer.expired", "timer_id": "t1", "label": "eggs"} in envelopes
    assert any(e["type"] == "state.snapshot" for e in envelopes)
    assert len(session.sent_realtime) == 1
    assert "eggs" in session.sent_realtime[0]["text"]


async def test_on_timer_expired_without_active_session_skips_nudge(
    state_manager: StateManager,
) -> None:
    ws = FakeWebSocket()
    gateway = _make_gateway(state_manager, ws)  # gateway._session is None between connects

    await gateway._on_timer_expired(_expired_timer())

    envelopes = [json.loads(text) for text in ws.sent_text]
    assert any(e["type"] == "timer.expired" for e in envelopes)


# --- fake Live backend (connect-factory seam) ---------------------------------


def make_message(
    *,
    session_resumption_update: Optional[Any] = None,
    go_away: Optional[Any] = None,
    tool_call: Optional[Any] = None,
    server_content: Optional[Any] = None,
) -> SimpleNamespace:
    """Mimics the LiveServerMessage attributes _downlink reads."""
    return SimpleNamespace(
        session_resumption_update=session_resumption_update,
        go_away=go_away,
        tool_call=tool_call,
        server_content=server_content,
    )


def make_tool_call(*, id: str, name: str, args: Dict[str, Any]) -> SimpleNamespace:
    return SimpleNamespace(function_calls=[SimpleNamespace(id=id, name=name, args=args)])


def make_server_content(
    *,
    interrupted: bool = False,
    input_transcription: Optional[str] = None,
    output_transcription: Optional[str] = None,
    audio: Optional[bytes] = None,
) -> SimpleNamespace:
    model_turn = None
    if audio is not None:
        part = SimpleNamespace(inline_data=SimpleNamespace(data=audio))
        model_turn = SimpleNamespace(parts=[part])
    input_ns = SimpleNamespace(text=input_transcription) if input_transcription else None
    output_ns = SimpleNamespace(text=output_transcription) if output_transcription else None
    return SimpleNamespace(
        interrupted=interrupted,
        input_transcription=input_ns,
        output_transcription=output_ns,
        model_turn=model_turn,
    )


class FakeLiveSession:
    """Mimics the object yielded by `client.aio.live.connect(...)`."""

    def __init__(self, messages: Optional[List[Any]] = None, block_after: bool = False):
        self._messages = messages or []
        self._block_after = block_after
        self.sent_realtime: List[Dict[str, Any]] = []
        self.sent_tool_responses: List[Any] = []

    async def receive(self):
        for message in self._messages:
            yield message
        if self._block_after:
            await asyncio.Event().wait()  # simulate "still connected, nothing new yet"

    async def send_realtime_input(self, **kwargs: Any) -> None:
        self.sent_realtime.append(kwargs)

    async def send_tool_response(self, function_responses: Any) -> None:
        self.sent_tool_responses.append(function_responses)


class _ConnectCM:
    def __init__(self, session: FakeLiveSession):
        self._session = session

    async def __aenter__(self) -> FakeLiveSession:
        return self._session

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        return False


class FakeConnectFactory:
    """Mimics `client.aio.live.connect` as a callable connect-factory."""

    def __init__(self, sessions: List[FakeLiveSession]):
        self._sessions = sessions
        self.call_count = 0

    def __call__(self) -> _ConnectCM:
        session = self._sessions[self.call_count]
        self.call_count += 1
        return _ConnectCM(session)


class ScriptedWebSocket(FakeWebSocket):
    """Blocks on receive() until the `disconnect_after`-th call, then disconnects."""

    def __init__(self, disconnect_after: int):
        super().__init__()
        self._call_count = 0
        self._disconnect_after = disconnect_after

    async def receive(self) -> Dict[str, Any]:
        self._call_count += 1
        if self._call_count >= self._disconnect_after:
            return {"type": "websocket.disconnect"}
        await asyncio.Event().wait()  # block forever: no more client input this session


# --- _uplink protocol coverage --------------------------------------------------


class QueuedWebSocket(FakeWebSocket):
    """Replays a fixed list of receive() messages, then disconnects."""

    def __init__(self, messages: List[Dict[str, Any]]):
        super().__init__()
        self._messages = list(messages) + [{"type": "websocket.disconnect"}]
        self._index = 0

    async def receive(self) -> Dict[str, Any]:
        message = self._messages[self._index]
        self._index += 1
        return message


async def test_uplink_forwards_audio_text_and_video_frames(
    state_manager: StateManager,
) -> None:
    ws = QueuedWebSocket(
        [
            {"bytes": b"\x01\x02"},
            {"text": json.dumps({"type": "user.text", "text": "hello"})},
            {
                "text": json.dumps(
                    {
                        "type": "video.frame",
                        "data": base64.b64encode(b"fake-jpeg-bytes").decode(),
                        "mime_type": "image/jpeg",
                    }
                )
            },
        ]
    )
    gateway = _make_gateway(state_manager, ws)
    session = FakeSession()

    await gateway._uplink(session)

    assert session.sent_realtime[0]["audio"].data == b"\x01\x02"
    assert session.sent_realtime[1]["text"] == "hello"
    video_blob = session.sent_realtime[2]["video"]
    assert video_blob.data == b"fake-jpeg-bytes"
    assert video_blob.mime_type == "image/jpeg"


async def test_uplink_unknown_envelope_sends_error(state_manager: StateManager) -> None:
    ws = QueuedWebSocket([{"text": json.dumps({"type": "bogus"})}])
    gateway = _make_gateway(state_manager, ws)
    session = FakeSession()

    await gateway._uplink(session)

    envelopes = [json.loads(text) for text in ws.sent_text]
    assert any(e["type"] == "error" and "bogus" in e["message"] for e in envelopes)


# --- _downlink protocol coverage ----------------------------------------------


async def test_downlink_dispatches_tool_call_and_sends_state_snapshot(
    state_manager: StateManager,
) -> None:
    ws = FakeWebSocket()
    registry = ToolRegistry(state_manager)
    gateway = LiveGateway(
        websocket=ws, session_id="s1", state_manager=state_manager, registry=registry
    )
    session = FakeLiveSession(
        messages=[
            make_message(
                tool_call=make_tool_call(
                    id="call-1",
                    name="set_kitchen_timer",
                    args={"duration_seconds": 30, "label": "eggs"},
                )
            )
        ]
    )

    await gateway._downlink(session)

    assert len(session.sent_tool_responses) == 1
    [response] = session.sent_tool_responses[0]
    assert response.name == "set_kitchen_timer"
    assert response.response["status"] == "success"

    envelopes = [json.loads(text) for text in ws.sent_text]
    assert any(e["type"] == "state.snapshot" for e in envelopes)

    state = await state_manager.get_state("s1")
    assert state is not None
    assert any(t.label == "eggs" for t in state.active_timers.values())


async def test_downlink_forwards_interrupted_transcripts_and_audio(
    state_manager: StateManager,
) -> None:
    ws = FakeWebSocket()
    registry = ToolRegistry(state_manager)
    gateway = LiveGateway(
        websocket=ws, session_id="s1", state_manager=state_manager, registry=registry
    )
    session = FakeLiveSession(
        messages=[
            make_message(server_content=make_server_content(interrupted=True)),
            make_message(server_content=make_server_content(input_transcription="set a timer")),
            make_message(server_content=make_server_content(output_transcription="done")),
            make_message(server_content=make_server_content(audio=b"\x01\x02\x03")),
        ]
    )

    await gateway._downlink(session)

    envelopes = [json.loads(text) for text in ws.sent_text]
    assert {"type": "interrupted"} in envelopes
    assert {"type": "transcript.user", "text": "set a timer"} in envelopes
    assert {"type": "transcript.agent", "text": "done"} in envelopes
    assert ws.sent_bytes == [b"\x01\x02\x03"]


async def test_downlink_captures_resumption_handle_and_returns_on_go_away(
    state_manager: StateManager,
) -> None:
    ws = FakeWebSocket()
    registry = ToolRegistry(state_manager)
    gateway = LiveGateway(
        websocket=ws, session_id="s1", state_manager=state_manager, registry=registry
    )
    session = FakeLiveSession(
        messages=[
            make_message(
                session_resumption_update=SimpleNamespace(resumable=True, new_handle="handle-abc")
            ),
            make_message(go_away=SimpleNamespace(time_left="10s")),
            make_message(server_content=make_server_content(interrupted=True)),  # never reached
        ]
    )

    await gateway._downlink(session)

    assert gateway._resumption_handle == "handle-abc"
    envelopes = [json.loads(text) for text in ws.sent_text]
    assert envelopes == []  # go_away returns before the trailing interrupted message


# --- run() reconnect loop -------------------------------------------------------


async def test_run_reconnects_after_go_away_then_stops_on_disconnect(
    state_manager: StateManager,
) -> None:
    registry = ToolRegistry(state_manager)
    session1 = FakeLiveSession(
        messages=[
            make_message(
                session_resumption_update=SimpleNamespace(resumable=True, new_handle="handle-abc")
            ),
            make_message(go_away=SimpleNamespace(time_left="10s")),
        ]
    )
    session2 = FakeLiveSession(block_after=True)
    connect_factory = FakeConnectFactory([session1, session2])
    ws = ScriptedWebSocket(disconnect_after=2)

    gateway = LiveGateway(
        websocket=ws,
        session_id="s1",
        state_manager=state_manager,
        registry=registry,
        connect_factory=connect_factory,
    )

    await asyncio.wait_for(gateway.run(), timeout=5)

    assert connect_factory.call_count == 2
    assert gateway._resumption_handle == "handle-abc"
    statuses = [
        json.loads(text)["status"]
        for text in ws.sent_text
        if json.loads(text).get("type") == "session.status"
    ]
    assert statuses == ["ready", "reconnecting", "ready"]
