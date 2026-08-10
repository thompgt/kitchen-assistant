"""Transcript-driven tool-calling eval: does the model pick the right tool?

Feeds each labelled chef utterance to `generate_content` with the *same*
`SYSTEM_INSTRUCTION` and the *same* `FunctionDeclaration`s the Live gateway
sends, and checks the tool the model chose and the arguments it filled in.
Non-Live on purpose: one turn, no audio, deterministic enough to score, and it
exercises the only thing that differs between the two paths (the declarations).

A case with `expected_tool: null` must be answered in words, which is how tool
over-triggering shows up as a number instead of a vibe.

Needs GOOGLE_API_KEY.

    poetry run python scripts/eval_tool_calls.py
    poetry run python scripts/eval_tool_calls.py --model gemini-3.1-flash --min-accuracy 0.9
"""
import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv
from google import genai
from google.genai import types

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.live.gateway import SYSTEM_INSTRUCTION  # noqa: E402
from app.state_manager import StateManager  # noqa: E402
from app.tools.registry import ToolRegistry  # noqa: E402

load_dotenv()

GOLDEN_PATH = Path(__file__).resolve().parent.parent / "data" / "eval" / "tool_calls_golden.json"
DEFAULT_MODEL = os.getenv("EVAL_MODEL", "gemini-3.1-flash")


def load_cases(path: Path) -> List[Dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8"))["cases"]


def _args_match(actual: Dict[str, Any], expected: Dict[str, Any]) -> bool:
    """Subset match: every expected argument is present and equal (numbers loosely)."""
    for key, want in expected.items():
        if key not in actual:
            return False
        got = actual[key]
        if isinstance(want, (int, float)) and isinstance(got, (int, float)):
            if abs(float(got) - float(want)) > 1e-6:
                return False
        elif str(got).strip().lower() != str(want).strip().lower():
            return False
    return True


def score_case(
    client: Any, model: str, registry: ToolRegistry, case: Dict[str, Any]
) -> Tuple[bool, str]:
    response = client.models.generate_content(
        model=model,
        contents=case["utterance"],
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            tools=[types.Tool(function_declarations=registry.declarations)],
        ),
    )
    calls = response.function_calls or []
    expected_tool: Optional[str] = case["expected_tool"]

    if expected_tool is None:
        names = [call.name for call in calls]
        return (not calls), f"expected no tool call, got {names or 'none'}"

    if not calls:
        return False, f"expected {expected_tool}, got no tool call"

    call = calls[0]
    actual_args = dict(call.args or {})
    if call.name != expected_tool:
        return False, f"expected {expected_tool}, got {call.name}({actual_args})"
    if not _args_match(actual_args, case["expected_args"]):
        return False, f"{expected_tool} args {actual_args} != expected {case['expected_args']}"
    return True, f"{call.name}({actual_args})"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--golden", type=Path, default=GOLDEN_PATH)
    parser.add_argument("--min-accuracy", type=float, default=0.9)
    args = parser.parse_args()

    if not os.getenv("GOOGLE_API_KEY"):
        print("GOOGLE_API_KEY is not set; tool-calling eval needs a real model.")
        return 2

    registry = ToolRegistry(StateManager())
    client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
    cases = load_cases(args.golden)

    passed = 0
    for case in cases:
        ok, detail = score_case(client, args.model, registry, case)
        passed += int(ok)
        print(f"[{'PASS' if ok else 'FAIL'}] {case['utterance']!r} -> {detail}")

    accuracy = passed / len(cases) if cases else 0.0
    print(f"\ntool-call accuracy ({args.model}): {accuracy:.3f} ({passed}/{len(cases)})")
    if accuracy < args.min_accuracy:
        print(f"FAIL: below the {args.min_accuracy} threshold")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
