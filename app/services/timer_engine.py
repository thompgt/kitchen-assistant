"""Timer engine: real asyncio countdowns with proactive expiry callbacks.

The gateway registers a per-session callback at connection start (no import
cycle: the engine knows nothing about Live sessions or WebSockets). On expiry
the engine drops the timer from state and invokes the callback so the
assistant can announce it unprompted.

Countdown tasks live in this process, so a restart (or a reconnect against a
Redis-backed StateManager) loses them while the records survive. `rehydrate`
rebuilds them from `start_time + duration_seconds`.
"""
import asyncio
import logging
from datetime import datetime
from typing import Awaitable, Callable, Dict, Tuple

from ..schemas import KitchenTimer, RecipeState
from ..state_manager import StateManager

logger = logging.getLogger(__name__)

ExpiryCallback = Callable[[KitchenTimer], Awaitable[None]]


class TimerEngine:
    """Owns countdown tasks keyed by (session_id, timer_id)."""

    def __init__(self, state_manager: StateManager):
        self._state_manager = state_manager
        self._tasks: Dict[Tuple[str, str], asyncio.Task] = {}
        self._callbacks: Dict[str, ExpiryCallback] = {}

    def register_session(self, session_id: str, callback: ExpiryCallback) -> None:
        self._callbacks[session_id] = callback

    def unregister_session(self, session_id: str) -> None:
        """Drop the callback and cancel the session's countdowns (no orphans)."""
        self._callbacks.pop(session_id, None)
        for key in [key for key in self._tasks if key[0] == session_id]:
            self._tasks.pop(key).cancel()

    def start(self, session_id: str, timer: KitchenTimer) -> None:
        key = (session_id, timer.id)
        self._tasks[key] = asyncio.create_task(
            self._run(session_id, timer, timer.duration_seconds)
        )

    async def rehydrate(self, session_id: str) -> int:
        """Restart countdowns for timers persisted by an earlier process.

        Without this, a Redis-backed session that survives a restart keeps its
        timer records forever and none of them ever fire. Timers whose deadline
        has already passed expire immediately, so the chef is told late rather
        than never.
        """
        state = await self._state_manager.get_state(session_id)
        if state is None:
            return 0

        restarted = 0
        now = datetime.now()
        for timer in list(state.active_timers.values()):
            if not timer.is_active or (session_id, timer.id) in self._tasks:
                continue
            elapsed = (now - timer.start_time).total_seconds()
            remaining = max(0.0, timer.duration_seconds - elapsed)
            self._tasks[(session_id, timer.id)] = asyncio.create_task(
                self._run(session_id, timer, remaining)
            )
            restarted += 1
        if restarted:
            logger.info("session %s: rehydrated %d timer(s)", session_id, restarted)
        return restarted

    def cancel(self, session_id: str, timer_id: str) -> bool:
        task = self._tasks.pop((session_id, timer_id), None)
        if task is None:
            return False
        task.cancel()
        return True

    def active_count(self, session_id: str) -> int:
        return sum(1 for key in self._tasks if key[0] == session_id)

    async def _run(self, session_id: str, timer: KitchenTimer, delay: float) -> None:
        await asyncio.sleep(delay)
        self._tasks.pop((session_id, timer.id), None)

        def _expire(state: RecipeState) -> None:
            # Dropped, not just flagged: a kept record grows state forever and
            # re-ships a dead timer in every subsequent snapshot.
            state.active_timers.pop(timer.id, None)

        await self._state_manager.update(session_id, _expire)

        callback = self._callbacks.get(session_id)
        if callback is None:
            logger.info(
                "session %s: timer '%s' expired with no listener", session_id, timer.label
            )
            return
        await callback(timer)
