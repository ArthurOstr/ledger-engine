from pydantic import BaseModel, ConfigDict
from typing import Optional

class CategoryRuleCreate(BaseModel):
    keyword: str
    assigned_category: str
    is_active: Optional[bool] = True

class CategoryRuleResponse(CategoryRuleCreate):
    id: int
    owner_id: int

    model_config = ConfigDict(from_attributes=True)