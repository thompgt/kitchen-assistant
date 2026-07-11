import json
from typing import Optional, Dict
from datetime import datetime
from .schemas import RecipeState

class StateManager:
    """
    Handles multi-tenant session persistence. 
    Can be backed by Redis or an in-memory store.
    """
    def __init__(self, use_redis: bool = False, redis_url: str = "redis://localhost:6379"):
        self.use_redis = use_redis
        self.in_memory_store: Dict[str, str] = {}
        self.redis_client = None
        
        if self.use_redis:
            try:
                import redis.asyncio as redis
                self.redis_client = redis.from_url(redis_url, decode_responses=True)
            except ImportError:
                print("Redis dependency not found. Falling back to in-memory store.")
                self.use_redis = False

    async def get_state(self, session_id: str) -> Optional[RecipeState]:
        if self.use_redis:
            data = await self.redis_client.get(f"session:{session_id}")
        else:
            data = self.in_memory_store.get(session_id)
            
        if data:
            return RecipeState.model_validate_json(data)
        return None

    async def save_state(self, state: RecipeState):
        state.last_updated = datetime.now()
        data = state.model_dump_json()
        
        if self.use_redis:
            await self.redis_client.set(f"session:{state.session_id}", data)
        else:
            self.in_memory_store[state.session_id] = data

    async def clear_state(self, session_id: str):
        if self.use_redis:
            await self.redis_client.delete(f"session:{session_id}")
        else:
            if session_id in self.in_memory_store:
                del self.in_memory_store[session_id]

# Global state manager instance
state_manager = StateManager()
