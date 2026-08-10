"""Populate embeddings for recipes and build the HNSW vector index.

Only recipes missing an embedding are sent to the API, batched into a
single embed_content call per chunk instead of one request per recipe.
Pass `--rebuild` to clear existing vectors first, which is what an
embedding-document change requires.
"""
import argparse
import json
import os
from typing import Any, List, Optional, Tuple

import duckdb
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

DB_PATH = os.getenv("RECIPES_DB_PATH", "data/recipes.db")
EMBEDDING_MODEL = "gemini-embedding-001"
BATCH_SIZE = 20

_client: Optional[Any] = None


def get_client() -> Any:
    """Build the embedding client on first use.

    Importing this module must not require an API key — a module-level
    `genai.Client(...)` made the script unimportable without one, which is why
    it had no unit tests while the sibling ingest script does. Same lazy shape
    as `app.services.recipe_store.RecipeStore._get_client`.
    """
    global _client
    if _client is None:
        _client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
    return _client


def get_embeddings(texts: List[str], client: Optional[Any] = None) -> List[List[float]]:
    if not texts:
        return []
    response = (client or get_client()).models.embed_content(
        model=EMBEDDING_MODEL,
        contents=texts,
        config=types.EmbedContentConfig(task_type="RETRIEVAL_DOCUMENT"),
    )
    return [list(e.values) for e in response.embeddings]


def _chunks(items: List, size: int) -> List[List]:
    return [items[i:i + size] for i in range(0, len(items), size)]


def build_document(title: str, ingredients_json: str, steps_json: str) -> str:
    """The text a recipe is embedded as.

    Ingredient and step columns are DuckDB structs; stringified they carry
    `{"name":...}` keys that add nothing to the vector. Only the human-readable
    values go in, and the step instructions go in too — technique ("sear",
    "fold", "proof") is most of what a chef actually searches by.
    """
    ingredients: List[Any] = json.loads(ingredients_json)
    steps: List[Any] = json.loads(steps_json)
    names = ", ".join(str(item["name"]) for item in ingredients)
    instructions = " ".join(str(item["instruction"]) for item in steps)
    return f"{title}. Ingredients: {names}. Steps: {instructions}"


def setup_vector_db(
    db_path: str = DB_PATH,
    rebuild: bool = False,
    client: Optional[Any] = None,
) -> int:
    con = duckdb.connect(db_path)

    print("Installing DuckDB VSS extension...")
    con.execute("INSTALL vss;")
    con.execute("LOAD vss;")
    con.execute("SET hnsw_enable_experimental_persistence=true;")

    print("Ensuring embedding column exists...")
    con.execute("ALTER TABLE recipes ADD COLUMN IF NOT EXISTS embedding FLOAT[3072];")

    if rebuild:
        print("Clearing existing embeddings (--rebuild)...")
        con.execute("DROP INDEX IF EXISTS recipe_vss_idx;")
        con.execute("UPDATE recipes SET embedding = NULL;")

    pending: List[Tuple[str, str, str, str]] = con.execute(
        "SELECT id, title, ingredients::VARCHAR, steps::VARCHAR "
        "FROM recipes WHERE embedding IS NULL"
    ).fetchall()

    if not pending:
        print("No recipes missing embeddings.")
    else:
        print(f"Embedding {len(pending)} recipe(s) missing vectors, in batches of {BATCH_SIZE}...")
        for batch in _chunks(pending, BATCH_SIZE):
            texts = [
                build_document(title, ingredients, steps)
                for _, title, ingredients, steps in batch
            ]
            vectors = get_embeddings(texts, client=client)
            for (recipe_id, title, _, _), vector in zip(batch, vectors):
                con.execute("UPDATE recipes SET embedding = ? WHERE id = ?", [vector, recipe_id])
                print(f"  embedded: {title}")

    print("Creating HNSW index...")
    con.execute("CREATE INDEX IF NOT EXISTS recipe_vss_idx ON recipes USING HNSW (embedding);")

    con.close()
    print("Vector DB setup complete.")
    return len(pending)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Re-embed every recipe instead of only those missing a vector.",
    )
    args = parser.parse_args()
    setup_vector_db(rebuild=args.rebuild)
