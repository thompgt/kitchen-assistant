"""Load the recipe catalog from data/recipes_seed.json into DuckDB.

Idempotent and reproducible from scratch: creates the `recipes` table if it
doesn't exist, then inserts any seed recipes not already present by id.
Embeddings are populated separately by scripts/setup_vector_search.py.
"""
import json
import os
from pathlib import Path
from typing import Any, Dict, List

import duckdb
from dotenv import load_dotenv

load_dotenv()

DB_PATH = os.getenv("RECIPES_DB_PATH", "data/recipes.db")
SEED_PATH = Path(__file__).resolve().parent.parent / "data" / "recipes_seed.json"

REQUIRED_RECIPE_FIELDS = {"id", "title", "ingredients", "steps", "total_time_minutes", "servings"}
REQUIRED_INGREDIENT_FIELDS = {"name", "amount", "unit"}
REQUIRED_STEP_FIELDS = {"step_number", "instruction"}


def load_seed_recipes(seed_path: Path = SEED_PATH) -> List[Dict[str, Any]]:
    """Load and shallow-validate the seed catalog. Raises ValueError on a malformed entry."""
    recipes = json.loads(seed_path.read_text(encoding="utf-8"))

    for recipe in recipes:
        missing = REQUIRED_RECIPE_FIELDS - recipe.keys()
        if missing:
            raise ValueError(f"Recipe {recipe.get('id', '?')} missing fields: {missing}")
        for ingredient in recipe["ingredients"]:
            missing = REQUIRED_INGREDIENT_FIELDS - ingredient.keys()
            if missing:
                raise ValueError(f"Recipe {recipe['id']} has an ingredient missing fields: {missing}")
        for step in recipe["steps"]:
            missing = REQUIRED_STEP_FIELDS - step.keys()
            if missing:
                raise ValueError(f"Recipe {recipe['id']} has a step missing fields: {missing}")

    ids = [r["id"] for r in recipes]
    duplicates = {i for i in ids if ids.count(i) > 1}
    if duplicates:
        raise ValueError(f"Duplicate recipe ids in seed data: {duplicates}")

    return recipes


def ensure_schema(con: "duckdb.DuckDBPyConnection") -> None:
    con.execute("INSTALL vss;")
    con.execute("LOAD vss;")
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS recipes (
            id VARCHAR PRIMARY KEY,
            title VARCHAR,
            ingredients JSON,
            steps JSON,
            total_time_minutes INTEGER,
            servings INTEGER,
            embedding FLOAT[3072]
        )
        """
    )


def ingest_recipes(db_path: str = DB_PATH, seed_path: Path = SEED_PATH) -> int:
    recipes = load_seed_recipes(seed_path)

    con = duckdb.connect(db_path)
    try:
        ensure_schema(con)
        before = con.execute("SELECT COUNT(*) FROM recipes").fetchone()[0]

        for r in recipes:
            con.execute(
                "INSERT OR IGNORE INTO recipes "
                "(id, title, ingredients, steps, total_time_minutes, servings) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                [
                    r["id"],
                    r["title"],
                    json.dumps(r["ingredients"]),
                    json.dumps(r["steps"]),
                    r["total_time_minutes"],
                    r["servings"],
                ],
            )

        after = con.execute("SELECT COUNT(*) FROM recipes").fetchone()[0]
    finally:
        con.close()

    inserted = after - before
    print(f"Ingested {inserted} new recipe(s) into {db_path} ({after} total, {len(recipes)} in seed).")
    return inserted


if __name__ == "__main__":
    ingest_recipes()
