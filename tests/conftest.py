import pytest

from app.schemas import Ingredient, RecipeMetadata, RecipeStep
from app.state_manager import StateManager


@pytest.fixture
def state_manager() -> StateManager:
    """Fresh in-memory store per test — no cross-test state leaks."""
    return StateManager(use_redis=False)


@pytest.fixture
def sample_recipe() -> RecipeMetadata:
    return RecipeMetadata(
        id="pasta-01",
        title="Weeknight Pasta",
        description="Simple tomato pasta.",
        ingredients=[
            Ingredient(name="spaghetti", amount=200.0, unit="g"),
            Ingredient(name="olive oil", amount=2.0, unit="tbsp"),
        ],
        steps=[
            RecipeStep(step_number=1, instruction="Boil salted water."),
            RecipeStep(step_number=2, instruction="Cook spaghetti 9 minutes.", duration_minutes=9),
            RecipeStep(step_number=3, instruction="Toss with sauce and serve."),
        ],
        total_time_minutes=20,
    )
