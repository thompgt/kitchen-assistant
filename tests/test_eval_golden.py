"""Offline validation of the eval golden sets.

The evals themselves need an API key and are run by hand (see README,
Evaluating the LLM half). What CI *can* check for free is that the labels
still describe this system: every expected recipe id exists in the seed
catalog, every expected tool exists in the registry, and every expected
argument is one the model is actually shown.
"""
import json
from pathlib import Path
from typing import Any, Dict, List

from app.state_manager import StateManager
from app.tools.registry import ToolRegistry

ROOT = Path(__file__).resolve().parent.parent
EVAL_DIR = ROOT / "data" / "eval"


def _cases(name: str) -> List[Dict[str, Any]]:
    return json.loads((EVAL_DIR / name).read_text(encoding="utf-8"))["cases"]


def test_retrieval_golden_ids_exist_in_the_seed_catalog() -> None:
    seed = json.loads((ROOT / "data" / "recipes_seed.json").read_text(encoding="utf-8"))
    known = {recipe["id"] for recipe in seed}
    cases = _cases("retrieval_golden.json")

    assert cases
    for case in cases:
        assert case["query"].strip()
        assert set(case["expected_ids"]) <= known, case["query"]

    assert any(not case["expected_ids"] for case in cases)  # negatives keep the floor honest


def test_tool_call_golden_matches_the_registry_declarations() -> None:
    registry = ToolRegistry(StateManager())
    declarations = {d.name: d for d in registry.declarations}
    cases = _cases("tool_calls_golden.json")

    assert cases
    for case in cases:
        tool = case["expected_tool"]
        if tool is None:
            assert case["expected_args"] == {}
            continue
        assert tool in declarations, tool
        properties = declarations[tool].parameters.properties or {}
        assert set(case["expected_args"]) <= set(properties), case["utterance"]

    assert any(case["expected_tool"] is None for case in cases)  # over-triggering check
