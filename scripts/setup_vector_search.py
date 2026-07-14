"""Populate embeddings for recipes and build the HNSW vector index.

Only recipes missing an embedding are sent to the API, batched into a
single embed_content call per chunk instead of one request per recipe.
"""
import os
from typing import List, Tuple

import duckdb
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

DB_PATH = os.getenv("RECIPES_DB_PATH", "data/recipes.db")
EMBEDDING_MODEL = "gemini-embedding-001"
BATCH_SIZE = 20

client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))


def get_embeddings(texts: List[str]) -> List[List[float]]:
    if not texts:
        return []
    response = client.models.embed_content(
        model=EMBEDDING_MODEL,
        contents=texts,
        config=types.EmbedContentConfig(task_type="RETRIEVAL_DOCUMENT"),
    )
    return [list(e.values) for e in response.embeddings]


def _chunks(items: List, size: int) -> List[List]:
    return [items[i:i + size] for i in range(0, len(items), size)]


def setup_vector_db(db_path: str = DB_PATH) -> int:
    con = duckdb.connect(db_path)

    print("Installing DuckDB VSS extension...")
    con.execute("INSTALL vss;")
    con.execute("LOAD vss;")
    con.execute("SET hnsw_enable_experimental_persistence=true;")

    print("Ensuring embedding column exists...")
    con.execute("ALTER TABLE recipes ADD COLUMN IF NOT EXISTS embedding FLOAT[3072];")

    pending: List[Tuple[str, str]] = con.execute(
        "SELECT id, title, ingredients::VARCHAR FROM recipes WHERE embedding IS NULL"
    ).fetchall()

    if not pending:
        print("No recipes missing embeddings.")
    else:
        print(f"Embedding {len(pending)} recipe(s) missing vectors, in batches of {BATCH_SIZE}...")
        for batch in _chunks(pending, BATCH_SIZE):
            texts = [f"{title}. Ingredients: {ingredients}" for _, title, ingredients in batch]
            vectors = get_embeddings(texts)
            for (recipe_id, title, _), vector in zip(batch, vectors):
                con.execute("UPDATE recipes SET embedding = ? WHERE id = ?", [vector, recipe_id])
                print(f"  embedded: {title}")

    print("Creating HNSW index...")
    con.execute("CREATE INDEX IF NOT EXISTS recipe_vss_idx ON recipes USING HNSW (embedding);")

    con.close()
    print("Vector DB setup complete.")
    return len(pending)


if __name__ == "__main__":
    setup_vector_db()
