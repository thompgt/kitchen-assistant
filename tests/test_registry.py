from app.services.timer_engine import TimerEngine
from app.state_manager import StateManager
from app.tools.registry import ToolRegistry


def test_declarations_never_expose_injected_params(state_manager: StateManager) -> None:
    registry = ToolRegistry(state_manager)
    for declaration in registry.declarations:
        assert declaration.parameters is not None
        params = declaration.parameters.properties or {}
        assert "session_id" not in params
        assert "state_manager" not in params
        assert "timer_engine" not in params


async def test_dispatch_injects_session_and_state(state_manager: StateManager) -> None:
    registry = ToolRegistry(state_manager)
    result = await registry.dispatch(
        "s1", "set_kitchen_timer", {"duration_seconds": 60, "label": "eggs"}
    )
    assert result["status"] == "success"

    state = await state_manager.get_state("s1")
    assert state is not None
    assert state.active_timers[result["timer_id"]].label == "eggs"


async def test_dispatch_injects_timer_engine_when_present(state_manager: StateManager) -> None:
    engine = TimerEngine(state_manager)
    registry = ToolRegistry(state_manager, timer_engine=engine)
    result = await registry.dispatch(
        "s1", "set_kitchen_timer", {"duration_seconds": 60, "label": "eggs"}
    )
    assert result["status"] == "success"
    assert engine.active_count("s1") == 1
    engine.cancel("s1", result["timer_id"])


async def test_dispatch_cancel_and_list_timers(state_manager: StateManager) -> None:
    registry = ToolRegistry(state_manager)
    set_result = await registry.dispatch(
        "s1", "set_kitchen_timer", {"duration_seconds": 60, "label": "eggs"}
    )

    listed = await registry.dispatch("s1", "list_timers", {})
    assert listed["status"] == "success"
    assert {t["timer_id"] for t in listed["timers"]} == {set_result["timer_id"]}

    cancelled = await registry.dispatch(
        "s1", "cancel_timer", {"timer_id": set_result["timer_id"]}
    )
    assert cancelled["status"] == "success"

    listed_after = await registry.dispatch("s1", "list_timers", {})
    assert listed_after["timers"] == []


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
