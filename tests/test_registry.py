from app.state_manager import StateManager
from app.tools.registry import ToolRegistry


def test_declarations_never_expose_injected_params(state_manager: StateManager) -> None:
    registry = ToolRegistry(state_manager)
    for declaration in registry.declarations:
        assert declaration.parameters is not None
        params = declaration.parameters.properties or {}
        assert "session_id" not in params
        assert "state_manager" not in params


async def test_dispatch_injects_session_and_state(state_manager: StateManager) -> None:
    registry = ToolRegistry(state_manager)
    result = await registry.dispatch(
        "s1", "set_kitchen_timer", {"duration_seconds": 60, "label": "eggs"}
    )
    assert result["status"] == "success"

    state = await state_manager.get_state("s1")
    assert state is not None
    assert state.active_timers[result["timer_id"]].label == "eggs"


async def test_dispatch_tool_without_state_params(state_manager: StateManager) -> None:
    registry = ToolRegistry(state_manager)
    result = await registry.dispatch(
        "s1", "convert_units", {"value": 1, "from_unit": "cup", "to_unit": "ml"}
    )
    assert result["status"] == "success"


async def test_dispatch_unknown_tool_returns_error(state_manager: StateManager) -> None:
    registry = ToolRegistry(state_manager)
    result = await registry.dispatch("s1", "launch_rocket", {})
    assert result["status"] == "error"


async def test_dispatch_malformed_args_returns_error(state_manager: StateManager) -> None:
    registry = ToolRegistry(state_manager)
    result = await registry.dispatch("s1", "set_kitchen_timer", {"bogus": True})
    assert result["status"] == "error"
    assert "Invalid arguments" in result["message"]
