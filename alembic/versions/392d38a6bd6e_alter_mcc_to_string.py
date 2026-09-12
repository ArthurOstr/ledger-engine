"""alter_mcc_to_string

Revision ID: 392d38a6bd6e
Revises: c8985766e632
Create Date: 2026-09-12 15:06:02.781618

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '392d38a6bd6e'
down_revision: Union[str, Sequence[str], None] = 'c8985766e632'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # lpad ensures existing 3-digit ints like 742 are padded to "0742" on disk
    op.alter_column(
        "transactions",
        "mcc",
        existing_type=sa.Integer(),
        type_=sa.String(length=4),
        postgresql_using="lpad(mcc::text, 4, '0')",
    )

def downgrade() -> None:
    op.alter_column(
        "transactions",
        "mcc",
        existing_type=sa.String(length=4),
        type_=sa.Integer(),
        postgresql_using="mcc::integer",
    )