"""Offline retrieval eval: recall@k over a labelled query -> recipe-id set.

Scores the RAG half of the assistant, which unit tests cannot: the tests use
one-hot fixture vectors, so they prove the SQL is right and say nothing about
whether a real chef phrase finds the right dish.

Three numbers come out:
  recall@k   fraction of positive cases whose expected id is in the top k
  MRR        1/rank of the first expected id, averaged (ranking quality)
  abstain    fraction of negative cases (expected_ids: []) that correctly
             returned nothing, which is what the relevance floor buys

Needs GOOGLE_API_KEY and a built catalog (see README, Recipe catalog).

    poetry run python scripts/eval_retrieval.py
    poetry run python scripts/eval_retrieval.py --k 3 --min-recall 0.8
"""
import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.recipe_store import RecipeStore  # noqa: E402

load_dotenv()

GOLDEN_PATH = Path(__file__).resolve().parent.parent / "data" / "eval" / "retrieval_golden.json"


def load_cases(path: Path) -> List[Dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8"))["cases"]


async def evaluate(cases: List[Dict[str, Any]], k: int) -> Dict[str, float]:
    store = RecipeStore()
    hits = 0
    reciprocal_ranks = 0.0
    positives = 0
    abstained = 0
    negatives = 0

    for case in cases:
        expected = set(case["expected_ids"])
        results = await store.search(case["query"], k=k)
        ids = [r.id for r in results]

        if not expected:
            negatives += 1
            ok = not ids
            abstained += int(ok)
            print(f"[{'PASS' if ok else 'FAIL'}] (no match expected) {case['query']!r} -> {ids}")
            continue

        positives += 1
        rank = next((i + 1 for i, rid in enumerate(ids) if rid in expected), 0)
        hits += int(rank > 0)
        reciprocal_ranks += 1.0 / rank if rank else 0.0
        status = "PASS" if rank else "FAIL"
        print(f"[{status}] {case['query']!r} -> {ids} (expected one of {sorted(expected)})")

    return {
        f"recall@{k}": hits / positives if positives else 0.0,
        "mrr": reciprocal_ranks / positives if positives else 0.0,
        "abstain_rate": abstained / negatives if negatives else 1.0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--k", type=int, default=3, help="Results retrieved per query.")
    parser.add_argument("--golden", type=Path, default=GOLDEN_PATH)
    parser.add_argument(
        "--min-recall", type=float, default=0.8, help="Exit non-zero below this recall@k."
    )
    parser.add_argument(
        "--min-abstain",
        type=float,
        default=1.0,
        help="Exit non-zero below this fraction of correctly-abstained negatives.",
    )
    args = parser.parse_args()

    if not os.getenv("GOOGLE_API_KEY"):
        print("GOOGLE_API_KEY is not set; retrieval eval needs real query embeddings.")
        return 2

    cases = load_cases(args.golden)
    scores = asyncio.run(evaluate(cases, args.k))

    print("\n--- scores ---")
    for name, value in scores.items():
        print(f"{name:>12}: {value:.3f}")

    recall = scores[f"recall@{args.k}"]
    failed = recall < args.min_recall or scores["abstain_rate"] < args.min_abstain
    if failed:
        print(
            f"\nFAIL: recall@{args.k}={recall:.3f} (min {args.min_recall}), "
            f"abstain={scores['abstain_rate']:.3f} (min {args.min_abstain})"
        )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
