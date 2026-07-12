"""Tool registry: Gemini FunctionDeclarations plus server-side dispatch.

The model only ever sees user-meaningful parameters. `session_id` and
`state_manager` are injected here at dispatch time (ARCHITECTURE.md,
tool registry) and never appear in a declaration.
"""
import inspect
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

from google.genai import types

from ..services.recipe_store import RecipeStore
from ..services.timer_engine import TimerEngine
from ..state_manager import StateManager
from . import cooking_tools

ToolFn = Callable[..., Awaitable[Dict[str, Any]]]

_DECLARATIONS: List[types.FunctionDeclaration] = [
    types.FunctionDeclaration(
        name="set_kitchen_timer",
        description="Set a countdown kitchen timer with a descriptive label.",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "duration_seconds": types.Schema(
                    type=types.Type.INTEGER,
                    description="Timer length in seconds. Must be positive.",
                ),
                "label": types.Schema(
                    type=types.Type.STRING,
                    description="Short name for the timer, e.g. 'pasta' or 'roast'.",
                ),
            },
            required=["duration_seconds", "label"],
        ),
    ),
    types.FunctionDeclaration(
        name="cancel_timer",
        description="Cancel an active kitchen timer before it expires.",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "timer_id": types.Schema(
                    type=types.Type.STRING,
                    description="The identifier returned when the timer was set.",
                ),
            },
            required=["timer_id"],
        ),
    ),
    types.FunctionDeclaration(
        name="list_timers",
        description="List all currently active kitchen timers with remaining time.",
        parameters=types.Schema(type=types.Type.OBJECT, properties={}),
    ),
    types.FunctionDeclaration(
        name="convert_units",
        description=(
            "Convert a kitchen measurement between units. Supports mass "
            "(g, kg, oz, lb), volume (ml, l, cup, tsp, tbsp, fl oz), and "
            "temperature (Fahrenheit/Celsius)."
        ),
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "value": types.Schema(
                    type=types.Type.NUMBER, description="The numeric value to convert."
                ),
                "from_unit": types.Schema(
                    type=types.Type.STRING, description="Source unit, e.g. 'cup' or 'F'."
                ),
                "to_unit": types.Schema(
                    type=types.Type.STRING, description="Target unit, e.g. 'ml' or 'C'."
                ),
            },
            required=["value", "from_unit", "to_unit"],
        ),
    ),
    types.FunctionDeclaration(
        name="scale_recipe",
        description=(
            "Scale the loaded recipe's ingredient quantities by a positive "
            "multiplier (2.0 doubles, 0.5 halves)."
        ),
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "multiplier": types.Schema(
                    type=types.Type.NUMBER,
                    description="Scaling factor. Must be positive.",
                ),
            },
            required=["multiplier"],
        ),
    ),
    types.FunctionDeclaration(
        name="search_recipes",
        description="Search the recipe catalog by meaning (semantic search), not just keywords.",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "query": types.Schema(
                    type=types.Type.STRING,
                    description="What the chef is looking for, e.g. 'something with mushrooms'.",
                ),
                "k": types.Schema(
                    type=types.Type.INTEGER,
                    description="Maximum number of results to return. Defaults to 3.",
                ),
            },
            required=["query"],
        ),
    ),
    types.FunctionDeclaration(
        name="load_recipe",
        description="Load a recipe into the session so its steps and ingredients become active.",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "recipe_id": types.Schema(
                    type=types.Type.STRING,
                    description="The identifier of the recipe to load, from search_recipes results.",
                ),
            },
            required=["recipe_id"],
        ),
    ),
    types.FunctionDeclaration(
        name="navigate_steps",
        description=(
            "Move through the loaded recipe's instructions and read back the "
            "current step."
        ),
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "direction": types.Schema(
                    type=types.Type.STRING,
                    enum=["next", "previous", "jump"],
                    description="'next', 'previous', or 'jump' to a specific step.",
                ),
                "step_index": types.Schema(
                    type=types.Type.INTEGER,
                    description="0-based step index, required when direction is 'jump'.",
                ),
            },
            required=["direction"],
        ),
    ),
]

_IMPLEMENTATIONS: Dict[str, ToolFn] = {
    "set_kitchen_timer": cooking_tools.set_kitchen_timer,
    "cancel_timer": cooking_tools.cancel_timer,
    "list_timers": cooking_tools.list_timers,
    "convert_units": cooking_tools.convert_units,
    "scale_recipe": cooking_tools.scale_recipe,
    "navigate_steps": cooking_tools.navigate_steps,
    "search_recipes": cooking_tools.search_recipes,
    "load_recipe": cooking_tools.load_recipe,
}


class ToolRegistry:
    """Maps tool name -> (FunctionDeclaration, async callable) and dispatches calls."""

    def __init__(
        self,
        state_manager: StateManager,
        timer_engine: Optional[TimerEngine] = None,
        recipe_store: Optional[RecipeStore] = None,
    ):
        self._state_manager = state_manager
        self._timer_engine = timer_engine
        self._recipe_store = recipe_store
        self._tools: Dict[str, Tuple[types.FunctionDeclaration, ToolFn]] = {}
        for declaration in _DECLARATIONS:
            assert declaration.name is not None
            self.register(declaration, _IMPLEMENTATIONS[declaration.name])

    def register(self, declaration: types.FunctionDeclaration, fn: ToolFn) -> None:
        if declaration.name is None:
            raise ValueError("FunctionDeclaration must have a name.")
        self._tools[declaration.name] = (declaration, fn)

    @property
    def declarations(self) -> List[types.FunctionDeclaration]:
        return [declaration for declaration, _ in self._tools.values()]

    def live_tools(self) -> List[types.Tool]:
        """Tool list in the shape LiveConnectConfig expects."""
        return [types.Tool(function_declarations=self.declarations)]

    async def dispatch(
        self, session_id: str, name: str, args: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Run a tool by name, injecting server-side context. Always returns a dict."""
        entry = self._tools.get(name)
        if entry is None:
            return {"status": "error", "message": f"Unknown tool '{name}'."}

        _, fn = entry
        kwargs: Dict[str, Any] = dict(args or {})
        signature = inspect.signature(fn).parameters
        if "state_manager" in signature:
            kwargs["state_manager"] = self._state_manager
        if "session_id" in signature:
            kwargs["session_id"] = session_id
        if "timer_engine" in signature:
            kwargs["timer_engine"] = self._timer_engine
        if "recipe_store" in signature:
            kwargs["recipe_store"] = self._recipe_store

        try:
            return await fn(**kwargs)
        except TypeError as exc:
            # Model sent malformed arguments; report back instead of crashing the session.
            return {"status": "error", "message": f"Invalid arguments for '{name}': {exc}"}
