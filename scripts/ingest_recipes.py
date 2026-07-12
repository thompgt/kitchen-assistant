import json
import os

import duckdb
from dotenv import load_dotenv

load_dotenv()

DB_PATH = os.getenv("RECIPES_DB_PATH", "data/recipes.db")


def ingest_sample_recipes():
    con = duckdb.connect(DB_PATH)
    # The table's embedding column has an HNSW index (vss extension); DuckDB
    # needs the extension loaded before it can update an indexed table.
    con.execute("INSTALL vss;")
    con.execute("LOAD vss;")

    recipes = [
        {
            "id": "r2",
            "title": "Mushroom Risotto",
            "ingredients": [
                {"name": "Arborio Rice", "amount": 1, "unit": "cup"},
                {"name": "Mushrooms", "amount": 250, "unit": "g"},
                {"name": "Vegetable Broth", "amount": 500, "unit": "ml"},
                {"name": "Onion", "amount": 1, "unit": "piece"}
            ],
            "steps": [
                {"step_number": 1, "instruction": "Sauté onions and mushrooms until soft."},
                {"step_number": 2, "instruction": "Add rice and toast for 2 minutes."},
                {"step_number": 3, "instruction": "Add broth ladle by ladle, stirring constantly."}
            ],
            "total_time_minutes": 45,
            "servings": 4
        },
        {
            "id": "r3",
            "title": "Thai Green Curry",
            "ingredients": [
                {"name": "Chicken Breast", "amount": 300, "unit": "g"},
                {"name": "Coconut Milk", "amount": 400, "unit": "ml"},
                {"name": "Green Curry Paste", "amount": 2, "unit": "tbsp"},
                {"name": "Eggplant", "amount": 1, "unit": "piece"}
            ],
            "steps": [
                {"step_number": 1, "instruction": "Fry curry paste in a bit of oil until fragrant."},
                {"step_number": 2, "instruction": "Add chicken and cook until sealed."},
                {"step_number": 3, "instruction": "Pour in coconut milk and add eggplant."}
            ],
            "total_time_minutes": 30,
            "servings": 3
        },
        {
            "id": "r4",
            "title": "Taco Tuesday Beef",
            "ingredients": [
                {"name": "Ground Beef", "amount": 500, "unit": "g"},
                {"name": "Taco Seasoning", "amount": 1, "unit": "packet"},
                {"name": "Water", "amount": 100, "unit": "ml"}
            ],
            "steps": [
                {"step_number": 1, "instruction": "Brown the beef in a skillet over medium heat."},
                {"step_number": 2, "instruction": "Drain excess fat."},
                {"step_number": 3, "instruction": "Add seasoning and water, simmer for 5 minutes."}
            ],
            "total_time_minutes": 15,
            "servings": 4
        }
    ]

    for r in recipes:
        con.execute(
            "INSERT OR IGNORE INTO recipes "
            "(id, title, ingredients, steps, total_time_minutes, servings) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [
                r['id'],
                r['title'],
                json.dumps(r['ingredients']),
                json.dumps(r['steps']),
                r['total_time_minutes'],
                r['servings'],
            ],
        )

    print(f"Successfully ingested {len(recipes)} new recipes into {DB_PATH}.")
    con.close()

if __name__ == "__main__":
    ingest_sample_recipes()
