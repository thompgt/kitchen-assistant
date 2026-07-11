import asyncio
import os
from datetime import datetime
from typing import Any, Callable, Dict, Optional

from dotenv import load_dotenv

from .schemas import RecipeState

load_dotenv()


class StateManager:
    """
    Single session store for RecipeState (ADR-003).

    In-memory by default, optionally Redis-backed. All read-modify-write
    cycles must go through `update`, which serializes concurrent mutations
    of the same session behind a per-session asyncio.Lock.
    """

    def __init__(self, use_redis: bool = False, redis_url: str = "redis://localhost:6379"):
        self.use_redis = use_redis
        self.in_memory_store: Dict[str, str] = {}
        self.redis_client: Optional[Any] = None
        self._locks: Dict[str, asyncio.Lock] = {}

        if self.use_redis:
            try:
                import redis.asyncio as redis
                self.redis_client = redis.from_url(redis_url, decode_responses=True)
            except ImportError:
                print("Redis dependency not found. Falling back to in-memory store.")
                self.use_redis = False

    def _lock(self, session_id: str) -> asyncio.Lock:
        # No await between check and insert, so this is race-free on one event loop.
        if session_id not in self._locks:
            self._locks[session_id] = asyncio.Lock()
        return self._locks[session_id]

    async def get_state(self, session_id: str) -> Optional[RecipeState]:
        if self.use_redis:
            data = await self.redis_client.get(f"session:{session_id}")
        else:
            data = self.in_memory_store.get(session_id)

        if data:
            return RecipeState.model_validate_json(data)
        return None

    async def get_or_create_state(self, session_id: str) -> RecipeState:
        async with self._lock(session_id):
            state = await self.get_state(session_id)
            if state is None:
                state = RecipeState(session_id=session_id)
                await self.save_state(state)
            return state

    async def save_state(self, state: RecipeState) -> None:
        state.last_updated = datetime.now()
        data = state.model_dump_json()

        if self.use_redis:
            await self.redis_client.set(f"session:{state.session_id}", data)
        else:
            self.in_memory_store[state.session_id] = data

    async def update(
        self, session_id: str, mutator: Callable[[RecipeState], None]
    ) -> RecipeState:
        """Atomically read-modify-write a session's state and return the result."""
        async with self._lock(session_id):
            state = await self.get_state(session_id)
            if state is None:
                state = RecipeState(session_id=session_id)
            mutator(state)
            await self.save_state(state)
            return state

    async def clear_state(self, session_id: str) -> None:
        async with self._lock(session_id):
            if self.use_redis:
                await self.redis_client.delete(f"session:{session_id}")
            else:
                self.in_memory_store.pop(session_id, None)
        self._locks.pop(session_id, None)


# Global state manager instance
state_manager = StateManager(
    use_redis=os.getenv("USE_REDIS", "false").lower() == "true",
    redis_url=os.getenv("REDIS_URL", "redis://localhost:6379"),
)
