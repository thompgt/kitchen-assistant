import duckdb
import os
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

def setup_vector_db(db_path='notebooks/recipes.db'):
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
            
    # Function to get embeddings
    def get_embedding(text):
        result = genai.embed_content(
            model="models/gemini-embedding-001",
            content=text,
            task_type="retrieval_document"
        )
        return result['embedding']

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
    # Note: VSS index creation syntax for DuckDB
    con.execute("CREATE INDEX IF NOT EXISTS recipe_vss_idx ON recipes USING HNSW (embedding);")
    
    con.close()
    print("Vector DB setup complete.")

if __name__ == "__main__":
    setup_vector_db()
