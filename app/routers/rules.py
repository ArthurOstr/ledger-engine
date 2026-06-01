from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.models.category_rule import CategoryRule
from app.schemas.category_rule import CategoryRuleCreate, CategoryRuleResponse

router = APIRouter(prefix="/api/rules", tags=["Category Rules"])

@router.post("", response_model=CategoryRuleResponse)
async def create_rule(
        rule_in: CategoryRuleCreate,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    """
    Creates a dynamic categorization rule for the authenticated user.

    The keyword is automatically stripped of whitespace and converted to lowercase
    to ensure deterministic matching during the Excel ingestion pipeline.
    """
    # Sanitize the input: we use lowercase and strip whitespace to match
    new_rule = CategoryRule(
        owner_id=current_user.id,
        keyword=rule_in.keyword.lower().strip(),
        assigned_category=rule_in.assigned_category.strip(),
        is_active=rule_in.is_active,
    )

    db.add(new_rule)
    await db.commit()
    await db.refresh(new_rule)

    return new_rule

@router.get("", response_model=list[CategoryRuleResponse])
async def get_rules(
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    """
    Retrieves all active categorization rules belonging to the authenticated user.

    Rules marked as is_active=False are filtered out at the database level and
    will not be returned to the client or injected into the ingestion pipeline.
    """

    # Only fetch active rules belonging to exact user making the request
    stmt = select(CategoryRule).where(
        CategoryRule.owner_id == current_user.id,
        CategoryRule.is_active == True
    )

    result = await db.execute(stmt)
    return result.scalars().all()