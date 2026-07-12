import pytest

from app.schemas import RecipeMetadata, RecipeState
from app.services.timer_engine import TimerEngine
from app.state_manager import StateManager
from app.tools.cooking_tools import (
    cancel_timer,
    convert_units,
    list_timers,
    navigate_steps,
    scale_recipe,
    set_kitchen_timer,
)


async def _load_recipe(
    state_manager: StateManager, session_id: str, recipe: RecipeMetadata
) -> None:
    def load(state: RecipeState) -> None:
        state.recipe_id = recipe.id
        state.recipe_metadata = recipe

    await state_manager.update(session_id, load)


# --- set_kitchen_timer -------------------------------------------------------

async def test_set_timer_success_persists_in_state(state_manager: StateManager) -> None:
    result = await set_kitchen_timer(state_manager, "s1", 300, "Boiling Pasta")
    assert result["status"] == "success"

    state = await state_manager.get_state("s1")
    assert state is not None
    timer = state.active_timers[result["timer_id"]]
    assert timer.label == "Boiling Pasta"
    assert timer.duration_seconds == 300


@pytest.mark.parametrize("duration", [0, -5])
async def test_set_timer_rejects_non_positive_duration(
    state_manager: StateManager, duration: int
) -> None:
    result = await set_kitchen_timer(state_manager, "s1", duration, "Bad")
    assert result["status"] == "error"
    assert await state_manager.get_state("s1") is None  # nothing persisted


async def test_set_timer_starts_engine_countdown(state_manager: StateManager) -> None:
    engine = TimerEngine(state_manager)
    result = await set_kitchen_timer(state_manager, "s1", 300, "Boiling Pasta", timer_engine=engine)
    assert result["status"] == "success"
    assert engine.active_count("s1") == 1
    engine.cancel("s1", result["timer_id"])


# --- cancel_timer --------------------------------------------------------------

async def test_cancel_timer_removes_from_state(state_manager: StateManager) -> None:
    set_result = await set_kitchen_timer(state_manager, "s1", 300, "Boiling Pasta")
    timer_id = set_result["timer_id"]

    result = await cancel_timer(state_manager, "s1", timer_id)
    assert result["status"] == "success"
    assert result["label"] == "Boiling Pasta"

    state = await state_manager.get_state("s1")
    assert state is not None
    assert timer_id not in state.active_timers


async def test_cancel_timer_stops_engine_countdown(state_manager: StateManager) -> None:
    engine = TimerEngine(state_manager)
    set_result = await set_kitchen_timer(
        state_manager, "s1", 300, "Boiling Pasta", timer_engine=engine
    )
    timer_id = set_result["timer_id"]

    result = await cancel_timer(state_manager, "s1", timer_id, timer_engine=engine)
    assert result["status"] == "success"
    assert engine.active_count("s1") == 0


async def test_cancel_timer_unknown_id_returns_error(state_manager: StateManager) -> None:
    result = await cancel_timer(state_manager, "s1", "nope")
    assert result["status"] == "error"


# --- list_timers ---------------------------------------------------------------

async def test_list_timers_empty_when_no_session(state_manager: StateManager) -> None:
    result = await list_timers(state_manager, "s1")
    assert result == {"status": "success", "timers": []}


async def test_list_timers_reports_active_timers(state_manager: StateManager) -> None:
    await set_kitchen_timer(state_manager, "s1", 300, "Boiling Pasta")
    await set_kitchen_timer(state_manager, "s1", 60, "Toast")

    result = await list_timers(state_manager, "s1")
    assert result["status"] == "success"
    labels = {t["label"] for t in result["timers"]}
    assert labels == {"Boiling Pasta", "Toast"}
    for timer in result["timers"]:
        assert 0 <= timer["remaining_seconds"] <= 300


async def test_list_timers_excludes_expired_timers(state_manager: StateManager) -> None:
    set_result = await set_kitchen_timer(state_manager, "s1", 300, "Boiling Pasta")
    timer_id = set_result["timer_id"]

    def _expire(state: RecipeState) -> None:
        state.active_timers[timer_id].is_active = False

    await state_manager.update("s1", _expire)

    result = await list_timers(state_manager, "s1")
    assert result["timers"] == []


# --- convert_units -----------------------------------------------------------

@pytest.mark.parametrize(
    ("value", "src", "dst", "expected"),
    [
        (1, "cup", "ml", 236.59),
        (473.176, "ml", "cup", 2.0),
        (1, "lb", "g", 453.59),
        (2, "kg", "lb", 4.41),
        (1, "l", "cup", 4.23),
        (8, "fl oz", "ml", 236.59),
        (212, "F", "C", 100.0),
        (0, "Celsius", "fahrenheit", 32.0),
    ],
)
async def test_convert_units_supported_pairs(
    value: float, src: str, dst: str, expected: float
) -> None:
    result = await convert_units(value, src, dst)
    assert result["status"] == "success"
    assert result["value"] == pytest.approx(expected, abs=0.01)


async def test_convert_units_handles_aliases_and_case() -> None:
    result = await convert_units(2, "Tablespoons", "ML")
    assert result["status"] == "success"
    assert result["value"] == pytest.approx(29.57, abs=0.01)


async def test_convert_units_rejects_mass_to_volume() -> None:
    result = await convert_units(100, "g", "ml")
    assert result["status"] == "error"
    assert "density" in result["message"]


async def test_convert_units_rejects_unknown_unit() -> None:
    result = await convert_units(1, "smidgen", "g")
    assert result["status"] == "error"


# --- scale_recipe ------------------------------------------------------------

@pytest.mark.parametrize("multiplier", [0, -1.5])
async def test_scale_recipe_rejects_non_positive_multiplier(
    state_manager: StateManager, multiplier: float
) -> None:
    result = await scale_recipe(state_manager, "s1", multiplier)
    assert result["status"] == "error"


async def test_scale_recipe_without_recipe_stores_multiplier(
    state_manager: StateManager,
) -> None:
    result = await scale_recipe(state_manager, "s1", 2.0)
    assert result["status"] == "success"
    assert result["new_multiplier"] == 2.0
    assert "scaled_ingredients" not in result

    state = await state_manager.get_state("s1")
    assert state is not None
    assert state.servings_multiplier == 2.0


async def test_scale_recipe_recomputes_ingredient_amounts(
    state_manager: StateManager, sample_recipe: RecipeMetadata
) -> None:
    await _load_recipe(state_manager, "s1", sample_recipe)

    result = await scale_recipe(state_manager, "s1", 1.5)
    assert result["status"] == "success"
    assert result["scaled_ingredients"] == [
        {"name": "spaghetti", "amount": 300.0, "unit": "g"},
        {"name": "olive oil", "amount": 3.0, "unit": "tbsp"},
    ]


# --- navigate_steps ----------------------------------------------------------

async def test_navigate_requires_loaded_recipe(state_manager: StateManager) -> None:
    result = await navigate_steps(state_manager, "s1", "next")
    assert result["status"] == "error"
    assert "No recipe loaded" in result["message"]


async def test_navigate_next_returns_instruction(
    state_manager: StateManager, sample_recipe: RecipeMetadata
) -> None:
    await _load_recipe(state_manager, "s1", sample_recipe)

    result = await navigate_steps(state_manager, "s1", "next")
    assert result["status"] == "success"
    assert result["current_step"] == 1
    assert result["instruction"] == "Cook spaghetti 9 minutes."


async def test_navigate_clamps_at_last_step(
    state_manager: StateManager, sample_recipe: RecipeMetadata
) -> None:
    await _load_recipe(state_manager, "s1", sample_recipe)

    for _ in range(10):
        result = await navigate_steps(state_manager, "s1", "next")
    assert result["current_step"] == 2  # last index, not 10


async def test_navigate_previous_clamps_at_zero(
    state_manager: StateManager, sample_recipe: RecipeMetadata
) -> None:
    await _load_recipe(state_manager, "s1", sample_recipe)

    result = await navigate_steps(state_manager, "s1", "previous")
    assert result["status"] == "success"
    assert result["current_step"] == 0


async def test_navigate_jump_clamps_out_of_bounds(
    state_manager: StateManager, sample_recipe: RecipeMetadata
) -> None:
    await _load_recipe(state_manager, "s1", sample_recipe)

    result = await navigate_steps(state_manager, "s1", "jump", step_index=99)
    assert result["current_step"] == 2

    result = await navigate_steps(state_manager, "s1", "jump", step_index=-3)
    assert result["current_step"] == 0


async def test_navigate_jump_requires_index(
    state_manager: StateManager, sample_recipe: RecipeMetadata
) -> None:
    await _load_recipe(state_manager, "s1", sample_recipe)
    result = await navigate_steps(state_manager, "s1", "jump")
    assert result["status"] == "error"


async def test_navigate_rejects_unknown_direction(state_manager: StateManager) -> None:
    result = await navigate_steps(state_manager, "s1", "sideways")
    assert result["status"] == "error"
