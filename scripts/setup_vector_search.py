import os

import duckdb
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

DB_PATH = os.getenv("RECIPES_DB_PATH", "data/recipes.db")
EMBEDDING_MODEL = "gemini-embedding-001"

client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))


def get_embedding(text: str) -> list:
    response = client.models.embed_content(
        model=EMBEDDING_MODEL,
        contents=text,
        config=types.EmbedContentConfig(task_type="RETRIEVAL_DOCUMENT"),
    )
    return list(response.embeddings[0].values)


def setup_vector_db(db_path: str = DB_PATH):
    con = duckdb.connect(db_path)

    # Install and load VSS extension
    print("Installing DuckDB VSS extension...")
    con.execute("INSTALL vss;")
    con.execute("LOAD vss;")

    # Enable experimental HNSW persistence
    con.execute("SET hnsw_enable_experimental_persistence=true;")

    # Add embedding column to recipes table if it doesn't exist
    print("Updating schema for vector support...")
    try:
        con.execute("ALTER TABLE recipes DROP COLUMN IF EXISTS embedding;")
        con.execute("ALTER TABLE recipes ADD COLUMN embedding FLOAT[3072];")
    except Exception as e:
        print(f"Schema update note: {e}")

    # Update existing recipes with embeddings
    print("Generating embeddings for existing recipes...")
    recipes = con.execute("SELECT id, title, ingredients::VARCHAR as ing FROM recipes").fetchall()

    for recipe_id, title, ingredients in recipes:
        # Combine title and ingredients for a richer embedding
        search_text = f"{title}. Ingredients: {ingredients}"
        vector = get_embedding(search_text)
        con.execute("UPDATE recipes SET embedding = ? WHERE id = ?", [vector, recipe_id])
        print(f"Updated embedding for: {title}")

    # Create HNSW index for fast search
    print("Creating HNSW index...")
    con.execute("CREATE INDEX IF NOT EXISTS recipe_vss_idx ON recipes USING HNSW (embedding);")

    con.close()
    print("Vector DB setup complete.")

if __name__ == "__main__":
    setup_vector_db()
