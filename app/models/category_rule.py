from psycopg2._psycopg import Boolean

from sqlalchemy import String, Integer, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

class Category(Base):
    __tablename__ = "category_rules"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    # Isolation: Every rule must belong to a specific user. Ability to delete user's data.
    owner_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False
    )

    # Trigger to look for custom words below
    keyword_id: Mapped[str] = mapped_column(String, index=True, nullable=False)

    # Custom rules for categorized words
    assigned_id: Mapped[str] = mapped_column(String, nullable=False)

    # Allow to disable custom rules on demand without deleting it from database
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)