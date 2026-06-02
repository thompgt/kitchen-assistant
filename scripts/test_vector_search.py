import duckdb
import os
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

def test_semantic_search(query, db_path='notebooks/recipes.db'):
    con = duckdb.connect(db_path)
    con.execute("LOAD vss;")
    con.execute("SET hnsw_enable_experimental_persistence=true;")
    
    # Get embedding for the query
    print(f"Searching for: '{query}'...")
    result = genai.embed_content(
        model="models/gemini-embedding-001",
        content=query,
        task_type="retrieval_query"
    )
    query_vector = result['embedding']
    
    # Perform vector search
    # HNSW uses distance metrics. We can use array_distance or specialized VSS functions
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
