"""Unit-level check of LiveGateway's timer-expiry wiring.

A full fake Live backend (connect-factory seam) lands in Phase 6; here we
exercise `_on_timer_expired` directly against fake websocket/session
collaborators to confirm the browser envelope and the proactive model nudge.
"""
import json
from datetime import datetime
from typing import Any, Dict, List

from app.live.gateway import LiveGateway
from app.schemas import KitchenTimer
from app.state_manager import StateManager
from app.tools.registry import ToolRegistry


class FakeWebSocket:
    def __init__(self) -> None:
        self.sent_text: List[str] = []

    async def send_text(self, text: str) -> None:
        self.sent_text.append(text)


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
