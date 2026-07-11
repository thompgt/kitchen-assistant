import asyncio

from app.schemas import RecipeState
from app.state_manager import StateManager


async def test_get_state_returns_none_for_unknown_session(state_manager: StateManager) -> None:
    assert await state_manager.get_state("nope") is None


async def test_save_and_get_roundtrip(state_manager: StateManager) -> None:
    state = RecipeState(session_id="s1", current_step_index=2)
    await state_manager.save_state(state)

    loaded = await state_manager.get_state("s1")
    assert loaded is not None
    assert loaded.session_id == "s1"
    assert loaded.current_step_index == 2


async def test_get_or_create_state_initializes_once(state_manager: StateManager) -> None:
    first = await state_manager.get_or_create_state("s1")
    assert first.session_id == "s1"

    first.servings_multiplier = 3.0
    await state_manager.save_state(first)

    again = await state_manager.get_or_create_state("s1")
    assert again.servings_multiplier == 3.0


async def test_update_applies_mutator_and_persists(state_manager: StateManager) -> None:
    def bump(state: RecipeState) -> None:
        state.current_step_index += 1

    result = await state_manager.update("s1", bump)
    assert result.current_step_index == 1

    loaded = await state_manager.get_state("s1")
    assert loaded is not None
    assert loaded.current_step_index == 1


async def test_concurrent_updates_do_not_lose_writes(state_manager: StateManager) -> None:
    def bump(state: RecipeState) -> None:
        state.current_step_index += 1

    await asyncio.gather(*(state_manager.update("s1", bump) for _ in range(50)))

    loaded = await state_manager.get_state("s1")
    assert loaded is not None
    assert loaded.current_step_index == 50


async def test_updates_isolated_between_sessions(state_manager: StateManager) -> None:
    def bump(state: RecipeState) -> None:
        state.current_step_index += 1

    await state_manager.update("a", bump)
    await state_manager.update("b", bump)
    await state_manager.update("b", bump)

    state_a = await state_manager.get_state("a")
    state_b = await state_manager.get_state("b")
    assert state_a is not None and state_a.current_step_index == 1
    assert state_b is not None and state_b.current_step_index == 2


async def test_clear_state_removes_session(state_manager: StateManager) -> None:
    await state_manager.get_or_create_state("s1")
    await state_manager.clear_state("s1")
    assert await state_manager.get_state("s1") is None
