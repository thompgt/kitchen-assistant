import asyncio
from datetime import datetime, timedelta
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


async def test_expiry_fires_callback_and_drops_timer(
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
    assert "t1" not in state.active_timers  # dropped, so snapshots stop re-shipping it
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


async def test_rehydrate_restarts_persisted_timers_with_the_remaining_time(
    state_manager: StateManager, engine: TimerEngine
) -> None:
    """A timer record that outlived its process (Redis + restart) must still fire."""
    fired: List[KitchenTimer] = []

    async def on_expiry(timer: KitchenTimer) -> None:
        fired.append(timer)

    still_running = make_timer("t1", 30, "roast")
    already_due = make_timer("t2", 5, "eggs")
    already_due.start_time = datetime.now() - timedelta(seconds=10)  # deadline passed
    await state_manager.update(
        "s1", lambda s: s.active_timers.update({"t1": still_running, "t2": already_due})
    )

    engine.register_session("s1", on_expiry)
    assert await engine.rehydrate("s1") == 2
    await asyncio.sleep(0.05)

    assert [t.label for t in fired] == ["eggs"]  # the overdue one fired immediately
    assert engine.active_count("s1") == 1  # the roast is still counting down
    state = await state_manager.get_state("s1")
    assert state is not None
    assert set(state.active_timers) == {"t1"}
    engine.unregister_session("s1")


async def test_rehydrate_is_idempotent_and_ignores_unknown_sessions(
    state_manager: StateManager, engine: TimerEngine
) -> None:
    assert await engine.rehydrate("never-seen") == 0

    timer = make_timer("t1", 30)
    await state_manager.update("s1", lambda s: s.active_timers.update({"t1": timer}))
    assert await engine.rehydrate("s1") == 1
    assert await engine.rehydrate("s1") == 0  # already has a live task
    assert engine.active_count("s1") == 1
    engine.unregister_session("s1")


async def test_expiry_without_listener_does_not_crash(
    state_manager: StateManager, engine: TimerEngine
) -> None:
    timer = make_timer("t1", 1)
    timer.duration_seconds = 0
    engine.start("s1", timer)
    await asyncio.sleep(0.05)
    assert engine.active_count("s1") == 0
