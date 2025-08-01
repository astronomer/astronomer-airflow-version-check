"""Add placeholder migration

Revision ID: b5ad49d1f9b4
Revises:
Create Date: 2025-05-12 11:42:36.379917

Note: This is a placeholder migration used to stamp the migration
when we create the migration from the ORM. Otherwise, it will run
without stamping the migration, leading to subsequent changes to
the tables not being migrated.
"""

# revision identifiers, used by Alembic.
revision = 'b5ad49d1f9b4'
down_revision = None
branch_labels = None
depends_on = None
version = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
