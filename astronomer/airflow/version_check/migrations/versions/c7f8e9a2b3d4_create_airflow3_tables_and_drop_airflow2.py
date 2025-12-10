"""Create Airflow 3 tables and drop Airflow 2 tables

Revision ID: c7f8e9a2b3d4
Revises: b5ad49d1f9b4
Create Date: 2025-12-05 14:08:59.000000

This migration creates new tables for Airflow 3 with the updated schema
(end_of_maintenance and end_of_basic_support instead of end_of_support)
and drops the old Airflow 2 tables. This approach avoids migration complexity
and downgrade issues since we don't support downgrades of external DB managers
on Astro.
"""

# revision identifiers, used by Alembic.
revision = "c7f8e9a2b3d4"
down_revision = "b5ad49d1f9b4"
branch_labels = None
depends_on = None

import sqlalchemy as sa  # noqa: E402
from airflow.utils.sqlalchemy import UtcDateTime  # noqa: E402
from alembic import op  # noqa: E402


def upgrade() -> None:
    """
    Create new Airflow 3 tables with updated schema.

    This migration creates tables with _v3 suffix and the new schema
    (end_of_maintenance and end_of_basic_support instead of end_of_support).
    The old Airflow 2 tables are dropped in create_db_from_orm().
    """
    op.create_table(
        "astro_version_check_v3",
        sa.Column("singleton", sa.Boolean(), nullable=False),
        sa.Column("last_checked", UtcDateTime(timezone=True), nullable=True),
        sa.Column("last_checked_by", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("singleton"),
        schema=None,
    )

    op.create_table(
        "astro_available_version_v3",
        sa.Column("version", sa.Text().with_variant(sa.String(length=255), "mysql"), nullable=False),
        sa.Column("level", sa.Text(), nullable=False),
        sa.Column("date_released", UtcDateTime(timezone=True), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("hidden_from_ui", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("end_of_maintenance", UtcDateTime(timezone=True), nullable=True),
        sa.Column("end_of_basic_support", UtcDateTime(timezone=True), nullable=True),
        sa.Column("eos_dismissed_until", UtcDateTime(timezone=True), nullable=True),
        sa.Column("yanked", sa.Boolean(), nullable=True, server_default="0"),
        sa.PrimaryKeyConstraint("version"),
        schema=None,
    )

    op.create_index(
        "idx_astro_available_version_v3_hidden", "astro_available_version_v3", ["hidden_from_ui"], unique=False
    )


def downgrade() -> None:
    """
    Downgrade is not supported for external DB managers on Astro.
    This is a no-op to satisfy Alembic requirements.
    """
    pass
