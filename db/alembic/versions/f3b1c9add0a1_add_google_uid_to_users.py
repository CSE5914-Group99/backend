"""Add google_uid column to users

Revision ID: f3b1c9add0a1
Revises: c2628224de4c
Create Date: 2025-11-10 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'f3b1c9add0a1'
down_revision: Union[str, Sequence[str], None] = 'c2628224de4c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add nullable google_uid column
    op.add_column('users', sa.Column('google_uid', sa.String(length=255), nullable=True))
    # Add unique constraint on google_uid
    op.create_unique_constraint('uq_users_google_uid', 'users', ['google_uid'])


def downgrade() -> None:
    """Downgrade schema."""
    # Drop the unique constraint and column
    op.drop_constraint('uq_users_google_uid', 'users', type_='unique')
    op.drop_column('users', 'google_uid')
