from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete

from app.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.models.category_rule import CategoryRule
from app.models.transaction import Transaction
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
    clean_keyword = rule_in.keyword.lower().strip()
    if not clean_keyword:
        raise HTTPException(status_code=400, detail="Keyword cannot be empty")

    # Enforce keyword uniqueness per user to prevent rule collision
    conflict_stmt = select(CategoryRule).where(
        CategoryRule.owner_id == current_user.id,
        CategoryRule.keyword == clean_keyword,
        CategoryRule.is_active == True
    )
    existing = await db.execute(conflict_stmt)
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail=f"An active rule for keyword {clean_keyword} already exists"
                            )

    # Build the new rule
    new_rule = CategoryRule(
        owner_id=current_user.id,
        keyword=clean_keyword,
        assigned_category=rule_in.assigned_category.strip(),
        is_active=rule_in.is_active,
    )

    db.add(new_rule)

    # Push-Down Compute: We execute a bulk update directly inside the PostgreSQL kernel
    # rather than pulling historical transaction models into Python memory.
    search_pattern = f"%{clean_keyword}%"
    sweep_stmt = (
        update(Transaction)
        .where(Transaction.owner_id == current_user.id)
        .where(Transaction.category.is_(None))
        .where(Transaction.description.ilike(search_pattern))
        .values(category=new_rule.assigned_category)
    )
    await db.execute(sweep_stmt)

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

@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rule(
        rule_id: int,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    """
    Deletes a specific categorization rule.

    Verifies ownership before deletion to prevent cross-tenant security breaks.
    """
    stmt = delete(CategoryRule).where(
        CategoryRule.id == rule_id,
        CategoryRule.owner_id == current_user.id
    )
    result = await db.execute(stmt)

    if result.rowcount == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found")

    await db.commit()

    return None