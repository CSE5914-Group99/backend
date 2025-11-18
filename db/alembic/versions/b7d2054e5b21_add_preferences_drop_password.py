"""Add preferences column to users and drop hashed_password

Revision ID: b7d2054e5b21
Revises: f3b1c9add0a1
Create Date: 2025-11-12 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b7d2054e5b21"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS hashed_password")
    op.add_column(
        "users",
        sa.Column(
            "preferences",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.alter_column("users", "preferences", server_default=None)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("users", "preferences")
    op.add_column("users", sa.Column("hashed_password", sa.String(length=255), nullable=True))
