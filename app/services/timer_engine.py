"""Timer engine: real asyncio countdowns with proactive expiry callbacks.

The gateway registers a per-session callback at connection start (no import
cycle: the engine knows nothing about Live sessions or WebSockets). On expiry
the engine marks the timer inactive in state and invokes the callback so the
assistant can announce it unprompted.
"""
import asyncio
import logging
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
        self._tasks[key] = asyncio.create_task(self._run(session_id, timer))

    def cancel(self, session_id: str, timer_id: str) -> bool:
        task = self._tasks.pop((session_id, timer_id), None)
        if task is None:
            return False
        task.cancel()
        return True

    def active_count(self, session_id: str) -> int:
        return sum(1 for key in self._tasks if key[0] == session_id)

    async def _run(self, session_id: str, timer: KitchenTimer) -> None:
        await asyncio.sleep(timer.duration_seconds)
        self._tasks.pop((session_id, timer.id), None)

        def _expire(state: RecipeState) -> None:
            expired = state.active_timers.get(timer.id)
            if expired is not None:
                expired.is_active = False
                expired.remaining_seconds = 0

        await self._state_manager.update(session_id, _expire)

        callback = self._callbacks.get(session_id)
        if callback is None:
            logger.info(
                "session %s: timer '%s' expired with no listener", session_id, timer.label
            )
            return
        await callback(timer)
