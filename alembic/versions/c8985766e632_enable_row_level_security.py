"""enable_row_level_security

Revision ID: c8985766e632
Revises: b15f2c000860
Create Date: 2026-06-12 19:20:47.142242

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c8985766e632'
down_revision: Union[str, Sequence[str], None] = 'b15f2c000860'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Enable the RLS engine on the protected tables
    op.execute("ALTER TABLE transactions ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE category_rules ENABLE ROW LEVEL SECURITY;")

    # 2. FORCE RLS to prevent the application owner from bypassing the locks
    op.execute("ALTER TABLE transactions FORCE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE category_rules FORCE ROW LEVEL SECURITY;")

    # 3. Create the mathematical isolation policies
    op.execute("""
        CREATE POLICY tenant_isolation_policy ON transactions
        FOR ALL
        USING (owner_id = current_setting('app.current_user_id')::integer);
    """)
    op.execute("""
        CREATE POLICY tenant_isolation_policy_rules ON category_rules
        FOR ALL
        USING (owner_id = current_setting('app.current_user_id')::integer);
    """)


def downgrade() -> None:
    # Safely dismantle the locks if we ever need to roll back
    op.execute("DROP POLICY IF EXISTS tenant_isolation_policy ON transactions;")
    op.execute("DROP POLICY IF EXISTS tenant_isolation_policy_rules ON category_rules;")

    op.execute("ALTER TABLE transactions NO FORCE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE category_rules NO FORCE ROW LEVEL SECURITY;")

    op.execute("ALTER TABLE transactions DISABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE category_rules DISABLE ROW LEVEL SECURITY;")