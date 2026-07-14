"""Tests for scripts/ingest_recipes.py against a temp DuckDB — no network."""
import json

import duckdb
import pytest

from scripts.ingest_recipes import ensure_schema, ingest_recipes, load_seed_recipes

VALID_SEED = [
    {
        "id": "t1",
        "title": "Test Soup",
        "ingredients": [{"name": "Water", "amount": 1, "unit": "l"}],
        "steps": [{"step_number": 1, "instruction": "Boil it."}],
        "total_time_minutes": 5,
        "servings": 2,
    },
    {
        "id": "t2",
        "title": "Test Salad",
        "ingredients": [{"name": "Lettuce", "amount": 100, "unit": "g"}],
        "steps": [{"step_number": 1, "instruction": "Toss it."}],
        "total_time_minutes": 3,
        "servings": 1,
    },
]


def _write_seed(tmp_path, recipes) -> str:
    path = tmp_path / "seed.json"
    path.write_text(json.dumps(recipes), encoding="utf-8")
    return path


def test_load_seed_recipes_valid(tmp_path):
    path = _write_seed(tmp_path, VALID_SEED)
    recipes = load_seed_recipes(path)
    assert len(recipes) == 2
    assert {r["id"] for r in recipes} == {"t1", "t2"}


def test_load_seed_recipes_missing_field_raises(tmp_path):
    broken = [
        {"id": "t1", "title": "No steps", "ingredients": [], "total_time_minutes": 5, "servings": 1}
    ]
    path = _write_seed(tmp_path, broken)
    with pytest.raises(ValueError, match="missing fields"):
        load_seed_recipes(path)


def test_load_seed_recipes_bad_ingredient_raises(tmp_path):
    broken = [{
        "id": "t1", "title": "Bad ingredient",
        "ingredients": [{"name": "Water"}],
        "steps": [{"step_number": 1, "instruction": "Boil."}],
        "total_time_minutes": 5, "servings": 1,
    }]
    path = _write_seed(tmp_path, broken)
    with pytest.raises(ValueError, match="ingredient missing fields"):
        load_seed_recipes(path)


def test_load_seed_recipes_duplicate_ids_raises(tmp_path):
    path = _write_seed(tmp_path, [VALID_SEED[0], VALID_SEED[0]])
    with pytest.raises(ValueError, match="Duplicate recipe ids"):
        load_seed_recipes(path)


def test_ensure_schema_creates_table(tmp_path):
    db_path = str(tmp_path / "recipes.db")
    con = duckdb.connect(db_path)
    try:
        ensure_schema(con)
        columns = {row[0] for row in con.execute("DESCRIBE recipes").fetchall()}
        expected = {"id", "title", "ingredients", "steps", "total_time_minutes", "servings", "embedding"}
        assert expected <= columns
    finally:
        con.close()


def test_ingest_recipes_from_scratch(tmp_path):
    seed_path = _write_seed(tmp_path, VALID_SEED)
    db_path = str(tmp_path / "recipes.db")

    inserted = ingest_recipes(db_path=db_path, seed_path=seed_path)
    assert inserted == 2

    con = duckdb.connect(db_path, read_only=True)
    try:
        rows = con.execute("SELECT id, title, servings FROM recipes ORDER BY id").fetchall()
    finally:
        con.close()
    assert rows == [("t1", "Test Soup", 2), ("t2", "Test Salad", 1)]


def test_ingest_recipes_is_idempotent(tmp_path):
    seed_path = _write_seed(tmp_path, VALID_SEED)
    db_path = str(tmp_path / "recipes.db")

    first = ingest_recipes(db_path=db_path, seed_path=seed_path)
    second = ingest_recipes(db_path=db_path, seed_path=seed_path)

    assert first == 2
    assert second == 0

    con = duckdb.connect(db_path, read_only=True)
    try:
        count = con.execute("SELECT COUNT(*) FROM recipes").fetchone()[0]
    finally:
        con.close()
    assert count == 2
