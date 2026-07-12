"""RecipeStore tests against a synthetic fixture DB — no network, no API key.

The embedding client is faked so vector search is fully deterministic: each
fixture recipe gets a one-hot vector, and the fake client returns whichever
one-hot vector the test wants back as the "query embedding".
"""
import json
from types import SimpleNamespace
from typing import List

import duckdb
import pytest

from app.services.recipe_store import EMBEDDING_DIM, RecipeStore

FIXTURE_RECIPES = [
    ("r1", "Classic Carbonara", [{"name": "Pasta", "amount": 200, "unit": "g"}],
     [{"step_number": 1, "instruction": "Boil water."}], 20),
    ("r2", "Mushroom Risotto", [{"name": "Arborio Rice", "amount": 1, "unit": "cup"}],
     [{"step_number": 1, "instruction": "Saute onions."}], 45),
    ("r3", "Thai Green Curry", [{"name": "Chicken Breast", "amount": 300, "unit": "g"}],
     [{"step_number": 1, "instruction": "Fry curry paste."}], 30),
]


def _one_hot(index: int) -> List[float]:
    vector = [0.0] * EMBEDDING_DIM
    vector[index] = 1.0
    return vector


class FakeModels:
    def __init__(self, vector: List[float]):
        self._vector = vector

    async def embed_content(self, *, model, contents, config):
        return SimpleNamespace(embeddings=[SimpleNamespace(values=self._vector)])


class FakeClient:
    def __init__(self, vector: List[float]):
        self.aio = SimpleNamespace(models=FakeModels(vector))


@pytest.fixture
def fixture_db(tmp_path) -> str:
    db_path = str(tmp_path / "recipes_test.db")
    con = duckdb.connect(db_path)
    con.execute(
        f"CREATE TABLE recipes (id VARCHAR PRIMARY KEY, title VARCHAR, ingredients JSON, "
        f"steps JSON, total_time_minutes INTEGER, embedding FLOAT[{EMBEDDING_DIM}])"
    )
    for index, (recipe_id, title, ingredients, steps, total_time) in enumerate(FIXTURE_RECIPES):
        con.execute(
            "INSERT INTO recipes VALUES (?, ?, ?, ?, ?, ?)",
            [recipe_id, title, json.dumps(ingredients), json.dumps(steps), total_time, _one_hot(index)],
        )
    con.close()
    return db_path


async def test_search_returns_closest_match_first(fixture_db: str) -> None:
    store = RecipeStore(db_path=fixture_db, client=FakeClient(_one_hot(1)))
    results = await store.search("something with mushrooms", k=2)

    assert len(results) == 2
    assert results[0].id == "r2"
    assert results[0].distance == pytest.approx(0.0, abs=1e-6)
    assert results[1].distance > results[0].distance


async def test_search_respects_k(fixture_db: str) -> None:
    store = RecipeStore(db_path=fixture_db, client=FakeClient(_one_hot(0)))
    results = await store.search("pasta", k=1)
    assert len(results) == 1
    assert results[0].id == "r1"


async def test_get_recipe_hydrates_metadata(fixture_db: str) -> None:
    store = RecipeStore(db_path=fixture_db, client=FakeClient(_one_hot(0)))
    recipe = await store.get_recipe("r1")

    assert recipe is not None
    assert recipe.title == "Classic Carbonara"
    assert recipe.ingredients[0].name == "Pasta"
    assert recipe.steps[0].instruction == "Boil water."
    assert recipe.total_time_minutes == 20


async def test_get_recipe_unknown_id_returns_none(fixture_db: str) -> None:
    store = RecipeStore(db_path=fixture_db, client=FakeClient(_one_hot(0)))
    assert await store.get_recipe("nope") is None
