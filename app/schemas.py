from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class Ingredient(BaseModel):
    name: str
    amount: float
    unit: str

class RecipeStep(BaseModel):
    step_number: int
    instruction: str
    duration_minutes: Optional[int] = None

class RecipeMetadata(BaseModel):
    id: str
    title: str
    description: Optional[str] = None
    ingredients: List[Ingredient]
    steps: List[RecipeStep]
    total_time_minutes: int

class KitchenTimer(BaseModel):
    id: str
    label: str
    duration_seconds: int
    start_time: datetime
    remaining_seconds: int
    is_active: bool = True

class RecipeState(BaseModel):
    """
    Centralized state model for the kitchen assistant session.
    Matches the 'RecipeState' requirements from the skills definition.
    """
    session_id: str
    recipe_id: Optional[str] = None
    recipe_metadata: Optional[RecipeMetadata] = None
    current_step_index: int = 0
    active_timers: Dict[str, KitchenTimer] = Field(default_factory=dict)
    servings_multiplier: float = 1.0
    last_updated: datetime = Field(default_factory=datetime.now)

class RecipeSearchResult(BaseModel):
    id: str
    title: str
    total_time_minutes: int
    distance: float

class UserUtterance(BaseModel):
    text: str
    session_id: str

class AgentResponse(BaseModel):
    text: str
    session_id: str
    state: RecipeState
