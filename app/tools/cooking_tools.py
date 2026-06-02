import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from ..schemas import RecipeState, KitchenTimer, RecipeMetadata
import uuid

# Global in-memory state store for Phase 3
# In Phase 4, this will be replaced/complemented by Redis
_session_cache: Dict[str, RecipeState] = {}
_state_lock = asyncio.Lock()

async def get_or_create_state(session_id: str) -> RecipeState:
    """Helper to retrieve or initialize session state."""
    async with _state_lock:
        if session_id not in _session_cache:
            _session_cache[session_id] = RecipeState(session_id=session_id)
        return _session_cache[session_id]

async def set_kitchen_timer(session_id: str, duration_seconds: int, label: str) -> Dict[str, Any]:
    """
    Sets a new kitchen timer and tracks it in the session state.
    
    Args:
        session_id: The unique identifier for the cooking session.
        duration_seconds: How long the timer should run.
        label: A descriptive name for the timer (e.g., "Boiling Pasta").
        
    Returns:
        A dictionary confirming the timer details.
    """
    state = await get_or_create_state(session_id)
    timer_id = str(uuid.uuid4())[:8]
    
    timer = KitchenTimer(
        id=timer_id,
        label=label,
        duration_seconds=duration_seconds,
        start_time=datetime.now(),
        remaining_seconds=duration_seconds
    )
    
    async with _state_lock:
        state.active_timers[timer_id] = timer
        state.last_updated = datetime.now()
        
    return {"status": "success", "timer_id": timer_id, "label": label, "duration": duration_seconds}

async def convert_units(value: float, from_unit: str, to_unit: str) -> Dict[str, Any]:
    """
    Converts measurements between common kitchen units.
    
    Args:
        value: The numeric value to convert.
        from_unit: The source unit (e.g., 'cup', 'ml').
        to_unit: The target unit.
        
    Returns:
        A dictionary with the converted value.
    """
    # Simple conversion map for demonstration
    conversions = {
        ("cup", "ml"): 236.588,
        ("ml", "cup"): 1 / 236.588,
        ("tsp", "ml"): 4.92892,
        ("tbsp", "ml"): 14.7868,
        ("oz", "g"): 28.3495,
        ("lb", "g"): 453.592,
    }
    
    factor = conversions.get((from_unit.lower(), to_unit.lower()))
    if factor:
        result = value * factor
        return {"value": round(result, 2), "unit": to_unit}
    
    return {"error": f"Conversion from {from_unit} to {to_unit} not supported."}

async def scale_recipe(session_id: str, multiplier: float) -> Dict[str, Any]:
    """
    Scales the current recipe's ingredient quantities.
    
    Args:
        session_id: The unique identifier for the session.
        multiplier: The scaling factor (e.g., 2.0 to double, 0.5 to halve).
        
    Returns:
        Confirmation of the new scaling factor.
    """
    state = await get_or_create_state(session_id)
    
    async with _state_lock:
        state.servings_multiplier = multiplier
        state.last_updated = datetime.now()
        
    return {"status": "success", "new_multiplier": multiplier}

async def navigate_steps(session_id: str, direction: str, step_index: Optional[int] = None) -> Dict[str, Any]:
    """
    Updates the active step in the recipe instructions.
    
    Args:
        session_id: The unique identifier for the session.
        direction: 'next', 'previous', or 'jump'.
        step_index: The specific index to jump to if direction is 'jump'.
        
    Returns:
        The updated step index.
    """
    state = await get_or_create_state(session_id)
    
    async with _state_lock:
        if direction == "next":
            state.current_step_index += 1
        elif direction == "previous":
            state.current_step_index = max(0, state.current_step_index - 1)
        elif direction == "jump" and step_index is not None:
            state.current_step_index = step_index
            
        state.last_updated = datetime.now()
        
    return {"status": "success", "current_step": state.current_step_index}
