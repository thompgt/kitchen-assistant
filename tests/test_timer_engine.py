import asyncio
from datetime import datetime
from typing import List

import pytest

from app.schemas import KitchenTimer
from app.services.timer_engine import TimerEngine
from app.state_manager import StateManager


def make_timer(timer_id: str, seconds: float, label: str = "test") -> KitchenTimer:
    return KitchenTimer(
        id=timer_id,
        label=label,
        duration_seconds=int(seconds) or 1,
        start_time=datetime.now(),
        remaining_seconds=int(seconds) or 1,
    )


@pytest.fixture
def engine(state_manager: StateManager) -> TimerEngine:
    return TimerEngine(state_manager)


async def test_expiry_fires_callback_and_deactivates_timer(
    state_manager: StateManager, engine: TimerEngine
) -> None:
    fired: List[KitchenTimer] = []

    async def on_expiry(timer: KitchenTimer) -> None:
        fired.append(timer)

    timer = make_timer("t1", 1, "eggs")
    timer.duration_seconds = 0  # sleep(0) -> immediate expiry
    await state_manager.update("s1", lambda s: s.active_timers.update({"t1": timer}))

    engine.register_session("s1", on_expiry)
    engine.start("s1", timer)
    await asyncio.sleep(0.05)

    assert [t.label for t in fired] == ["eggs"]
    state = await state_manager.get_state("s1")
    assert state is not None
    assert state.active_timers["t1"].is_active is False
    assert state.active_timers["t1"].remaining_seconds == 0
    assert engine.active_count("s1") == 0


async def test_cancel_prevents_expiry(
    state_manager: StateManager, engine: TimerEngine
) -> None:
    fired: List[KitchenTimer] = []

    async def on_expiry(timer: KitchenTimer) -> None:
        fired.append(timer)

    engine.register_session("s1", on_expiry)
    timer = make_timer("t1", 30)
    engine.start("s1", timer)

    assert engine.cancel("s1", "t1") is True
    assert engine.cancel("s1", "t1") is False  # already gone
    await asyncio.sleep(0.05)

    assert fired == []
    assert engine.active_count("s1") == 0


async def test_unregister_session_cancels_all_tasks(
    state_manager: StateManager, engine: TimerEngine
) -> None:
    engine.start("s1", make_timer("t1", 30))
    engine.start("s1", make_timer("t2", 30))
    engine.start("other", make_timer("t3", 30))

    engine.unregister_session("s1")
    await asyncio.sleep(0)

    assert engine.active_count("s1") == 0
    assert engine.active_count("other") == 1
    engine.unregister_session("other")


async def test_expiry_without_listener_does_not_crash(
    state_manager: StateManager, engine: TimerEngine
) -> None:
    timer = make_timer("t1", 1)
    timer.duration_seconds = 0
    engine.start("s1", timer)
    await asyncio.sleep(0.05)
    assert engine.active_count("s1") == 0
