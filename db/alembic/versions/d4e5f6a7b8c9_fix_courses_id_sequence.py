"""Fix courses id sequence

Revision ID: d4e5f6a7b8c9
Revises: b7d2054e5b21
Create Date: 2025-11-13 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, Sequence[str], None] = "b7d2054e5b21"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Ensure the sequence exists (it should from previous migration, but just in case)
    op.execute("CREATE SEQUENCE IF NOT EXISTS courses_id_seq")
    
    # Set the default value of the id column to use the sequence
    op.alter_column(
        "courses",
        "id",
        server_default=sa.text("nextval('courses_id_seq')"),
        existing_type=sa.Integer(),
        existing_nullable=False
    )
    
    # Also ensure the sequence is owned by the column so it drops with it (optional but good practice)
    op.execute("ALTER SEQUENCE courses_id_seq OWNED BY courses.id")


def downgrade() -> None:
    # Remove the default value
    op.alter_column(
        "courses",
        "id",
        server_default=None,
        existing_type=sa.Integer(),
        existing_nullable=False
    )
