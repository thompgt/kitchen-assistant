"""RAG service: DuckDB + vss over the recipe catalog.

DuckDB is synchronous; every query runs in `asyncio.to_thread` so it never
blocks the event loop the Live gateway depends on. At catalog scale (a
handful of recipes) `array_distance` brute-force search is fine — the HNSW
index built by scripts/setup_vector_search.py is an optional speedup, not a
read-path requirement (ADR-004).
"""
import asyncio
import json
import os
from typing import Any, List, Optional

import duckdb
from google import genai
from google.genai import types

from ..schemas import Ingredient, RecipeMetadata, RecipeSearchResult, RecipeStep

EMBEDDING_MODEL = "gemini-embedding-001"
EMBEDDING_DIM = 3072


class RecipeStore:
    """Read-only access to the recipe catalog: semantic search + hydration."""

    def __init__(self, db_path: Optional[str] = None, client: Optional[Any] = None):
        self._db_path = db_path or os.getenv("RECIPES_DB_PATH", "data/recipes.db")
        self._client = client  # lazily built via _get_client so import never needs an API key

    def _get_client(self) -> Any:
        if self._client is None:
            self._client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
        return self._client

    def _connect(self) -> "duckdb.DuckDBPyConnection":
        return duckdb.connect(self._db_path, read_only=True)

    async def _embed(self, text: str, task_type: str) -> List[float]:
        response = await self._get_client().aio.models.embed_content(
            model=EMBEDDING_MODEL,
            contents=text,
            config=types.EmbedContentConfig(task_type=task_type),
        )
        return list(response.embeddings[0].values)

    async def search(self, query: str, k: int = 3) -> List[RecipeSearchResult]:
        vector = await self._embed(query, "RETRIEVAL_QUERY")

        def _query() -> List[RecipeSearchResult]:
            con = self._connect()
            try:
                rows = con.execute(
                    f"""
                    SELECT id, title, total_time_minutes,
                           array_distance(embedding, ?::FLOAT[{EMBEDDING_DIM}]) AS distance
                    FROM recipes
                    ORDER BY distance ASC
                    LIMIT ?
                    """,
                    [vector, k],
                ).fetchall()
            finally:
                con.close()
            return [
                RecipeSearchResult(id=row[0], title=row[1], total_time_minutes=row[2], distance=row[3])
                for row in rows
            ]

        return await asyncio.to_thread(_query)

    async def get_recipe(self, recipe_id: str) -> Optional[RecipeMetadata]:
        def _query() -> Optional[RecipeMetadata]:
            con = self._connect()
            try:
                row = con.execute(
                    "SELECT id, title, ingredients::VARCHAR, steps::VARCHAR, total_time_minutes "
                    "FROM recipes WHERE id = ?",
                    [recipe_id],
                ).fetchone()
            finally:
                con.close()
            return row

        row = await asyncio.to_thread(_query)
        if row is None:
            return None
        recipe_id_, title, ingredients_json, steps_json, total_time_minutes = row
        return RecipeMetadata(
            id=recipe_id_,
            title=title,
            ingredients=[Ingredient(**item) for item in json.loads(ingredients_json)],
            steps=[RecipeStep(**item) for item in json.loads(steps_json)],
            total_time_minutes=total_time_minutes,
        )
