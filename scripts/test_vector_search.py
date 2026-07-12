import os

import duckdb
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

DB_PATH = os.getenv("RECIPES_DB_PATH", "data/recipes.db")
EMBEDDING_MODEL = "gemini-embedding-001"

client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))


def test_semantic_search(query: str, db_path: str = DB_PATH):
    con = duckdb.connect(db_path, read_only=True)

    # Get embedding for the query
    print(f"Searching for: '{query}'...")
    response = client.models.embed_content(
        model=EMBEDDING_MODEL,
        contents=query,
        config=types.EmbedContentConfig(task_type="RETRIEVAL_QUERY"),
    )
    query_vector = list(response.embeddings[0].values)

    # Perform vector search (brute-force array_distance; HNSW index is optional at this scale)
    search_query = """
        SELECT title, array_distance(embedding, ?::FLOAT[3072]) as distance
        FROM recipes
        ORDER BY distance ASC
        LIMIT 3;
    """

    results = con.execute(search_query, [query_vector]).fetchall()

    print("\nSearch Results:")
    for title, distance in results:
        print(f"- {title} (Distance: {distance:.4f})")

    con.close()

if __name__ == "__main__":
    # Test cases
    test_semantic_search("spicy noodles")
    print("\n" + "="*30 + "\n")
    test_semantic_search("italian pasta with eggs")
    print("\n" + "="*30 + "\n")
    test_semantic_search("mexican ground meat")
