"""Cooking tool implementations.

Pure async functions: all state flows through the injected StateManager
(no module-level mutable state). `session_id` and `state_manager` are
injected server-side at dispatch time and are never model-visible
parameters (see ARCHITECTURE.md, tool registry).

Every tool returns a JSON-serializable dict with a "status" key:
"success" or "error" (with a human-readable "message").
"""
import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from ..schemas import KitchenTimer, RecipeState
from ..state_manager import StateManager

# Unit aliases normalize plural/long/symbol forms to canonical short names.
_UNIT_ALIASES: Dict[str, str] = {
    "cups": "cup",
    "milliliter": "ml", "milliliters": "ml", "millilitre": "ml", "millilitres": "ml",
    "liter": "l", "liters": "l", "litre": "l", "litres": "l",
    "teaspoon": "tsp", "teaspoons": "tsp",
    "tablespoon": "tbsp", "tablespoons": "tbsp",
    "ounce": "oz", "ounces": "oz",
    "fluid ounce": "floz", "fluid ounces": "floz", "fl oz": "floz", "fl. oz": "floz",
    "pound": "lb", "pounds": "lb", "lbs": "lb",
    "gram": "g", "grams": "g",
    "kilogram": "kg", "kilograms": "kg", "kgs": "kg",
    "fahrenheit": "f", "°f": "f",
    "celsius": "c", "°c": "c",
}

_MASS_TO_G: Dict[str, float] = {"g": 1.0, "kg": 1000.0, "oz": 28.3495, "lb": 453.592}
_VOLUME_TO_ML: Dict[str, float] = {
    "ml": 1.0, "l": 1000.0, "cup": 236.588, "tsp": 4.92892, "tbsp": 14.7868, "floz": 29.5735,
}
_TEMPERATURE_UNITS = {"f", "c"}


def _error(message: str) -> Dict[str, Any]:
    return {"status": "error", "message": message}


def _normalize_unit(unit: str) -> str:
    cleaned = unit.strip().lower()
    return _UNIT_ALIASES.get(cleaned, cleaned)


async def set_kitchen_timer(
    state_manager: StateManager, session_id: str, duration_seconds: int, label: str
) -> Dict[str, Any]:
    """
    Sets a new kitchen timer and tracks it in the session state.

    Args:
        state_manager: Injected session store (not model-visible).
        session_id: The unique identifier for the cooking session (not model-visible).
        duration_seconds: How long the timer should run. Must be positive.
        label: A descriptive name for the timer (e.g., "Boiling Pasta").

    Returns:
        A dictionary confirming the timer details, or a structured error.
    """
    if duration_seconds <= 0:
        return _error(f"Timer duration must be positive, got {duration_seconds} seconds.")

    timer_id = str(uuid.uuid4())[:8]
    timer = KitchenTimer(
        id=timer_id,
        label=label,
        duration_seconds=duration_seconds,
        start_time=datetime.now(),
        remaining_seconds=duration_seconds,
    )

    def _add_timer(state: RecipeState) -> None:
        state.active_timers[timer_id] = timer

    await state_manager.update(session_id, _add_timer)
    return {"status": "success", "timer_id": timer_id, "label": label, "duration": duration_seconds}


async def convert_units(value: float, from_unit: str, to_unit: str) -> Dict[str, Any]:
    """
    Converts measurements between common kitchen units.

    Supports mass (g, kg, oz, lb), volume (ml, l, cup, tsp, tbsp, fl oz), and
    temperature (Fahrenheit <-> Celsius). Unit names are case-insensitive and
    accept common aliases ("cups", "tablespoons", "°F", ...).

    Args:
        value: The numeric value to convert.
        from_unit: The source unit (e.g., 'cup', 'ml', 'F').
        to_unit: The target unit.

    Returns:
        A dictionary with the converted value, or a structured error.
    """
    src = _normalize_unit(from_unit)
    dst = _normalize_unit(to_unit)

    if src in _TEMPERATURE_UNITS and dst in _TEMPERATURE_UNITS:
        if src == dst:
            result = value
        elif src == "f":
            result = (value - 32.0) * 5.0 / 9.0
        else:
            result = value * 9.0 / 5.0 + 32.0
        return {"status": "success", "value": round(result, 2), "unit": to_unit}

    for table in (_MASS_TO_G, _VOLUME_TO_ML):
        if src in table and dst in table:
            result = value * table[src] / table[dst]
            return {"status": "success", "value": round(result, 2), "unit": to_unit}

    if (src in _MASS_TO_G and dst in _VOLUME_TO_ML) or (src in _VOLUME_TO_ML and dst in _MASS_TO_G):
        return _error(
            f"Cannot convert {from_unit} to {to_unit}: mass and volume need an "
            "ingredient density, which is not supported."
        )

    return _error(f"Conversion from {from_unit} to {to_unit} not supported.")


async def scale_recipe(
    state_manager: StateManager, session_id: str, multiplier: float
) -> Dict[str, Any]:
    """
    Scales the current recipe's ingredient quantities.

    Args:
        state_manager: Injected session store (not model-visible).
        session_id: The unique identifier for the session (not model-visible).
        multiplier: The scaling factor (e.g., 2.0 to double, 0.5 to halve). Must be positive.

    Returns:
        The new multiplier and the recomputed ingredient amounts when a
        recipe is loaded, or a structured error.
    """
    if multiplier <= 0:
        return _error(f"Scaling multiplier must be positive, got {multiplier}.")

    def _set_multiplier(state: RecipeState) -> None:
        state.servings_multiplier = multiplier

    state = await state_manager.update(session_id, _set_multiplier)

    result: Dict[str, Any] = {"status": "success", "new_multiplier": multiplier}
    if state.recipe_metadata is not None:
        result["scaled_ingredients"] = [
            {
                "name": ingredient.name,
                "amount": round(ingredient.amount * multiplier, 2),
                "unit": ingredient.unit,
            }
            for ingredient in state.recipe_metadata.ingredients
        ]
    else:
        result["note"] = "No recipe loaded; multiplier stored and applied once one is loaded."
    return result


async def navigate_steps(
    state_manager: StateManager,
    session_id: str,
    direction: str,
    step_index: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Updates the active step in the recipe instructions.

    Args:
        state_manager: Injected session store (not model-visible).
        session_id: The unique identifier for the session (not model-visible).
        direction: 'next', 'previous', or 'jump'.
        step_index: The specific 0-based index to jump to if direction is 'jump'.

    Returns:
        The updated step index and its instruction text, or a structured error.
    """
    if direction not in ("next", "previous", "jump"):
        return _error(f"Unknown direction '{direction}'. Use 'next', 'previous', or 'jump'.")
    if direction == "jump" and step_index is None:
        return _error("Direction 'jump' requires a step_index.")

    def _move(s: RecipeState) -> None:
        if s.recipe_metadata is None or not s.recipe_metadata.steps:
            return
        if direction == "next":
            target = s.current_step_index + 1
        elif direction == "previous":
            target = s.current_step_index - 1
        else:
            target = step_index  # validated non-None above
        s.current_step_index = max(0, min(target, len(s.recipe_metadata.steps) - 1))

    state = await state_manager.update(session_id, _move)
    if state.recipe_metadata is None or not state.recipe_metadata.steps:
        return _error("No recipe loaded. Load a recipe before navigating steps.")

    current = state.recipe_metadata.steps[state.current_step_index]
    return {
        "status": "success",
        "current_step": state.current_step_index,
        "total_steps": len(state.recipe_metadata.steps),
        "instruction": current.instruction,
    }
