"""Add surrogate integer primary key to courses and keep unique (course_id, teacher_name)

Revision ID: a1b2c3d4e5f6
Revises: f3b1c9add0a1
Create Date: 2025-11-11 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "f3b1c9add0a1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop FK that still targets the composite primary key so we can replace it
    op.drop_constraint(
        "schedule_course_links_course_id_teacher_name_fkey",
        "schedule_course_links",
        type_="foreignkey",
    )

    # 1. Add new surrogate id column (nullable for now)
    op.add_column("courses", sa.Column("id", sa.Integer(), autoincrement=True, nullable=True))

    # 2. Populate id using a sequence for existing rows
    # Create sequence explicitly if not auto-created (PostgreSQL assumption); adapt for other DBs if needed.
    op.execute("CREATE SEQUENCE IF NOT EXISTS courses_id_seq")
    op.execute("UPDATE courses SET id = nextval('courses_id_seq') WHERE id IS NULL")

    # 3. Set id NOT NULL
    op.alter_column("courses", "id", nullable=False)

    # 4. Drop existing primary key (composite)
    op.drop_constraint("courses_pkey", "courses", type_="primary")

    # 5. Create new primary key on id
    op.create_primary_key("courses_pkey", "courses", ["id"])

    # 6. Ensure teacher_name nullable per new model (if previously NOT NULL)
    try:
        op.alter_column("courses", "teacher_name", nullable=True)
    except Exception:
        # Some DB backends may already have nullable; ignore
        pass

    # 7. Create unique constraint on (course_id, teacher_name)
    op.create_unique_constraint("uq_course_teacher", "courses", ["course_id", "teacher_name"])

    # Recreate FK so schedule_course_links still enforces referential integrity
    op.create_foreign_key(
        "schedule_course_links_course_id_teacher_name_fkey",
        "schedule_course_links",
        "courses",
        ["course_id", "teacher_name"],
        ["course_id", "teacher_name"],
        ondelete="CASCADE",
    )

    # NOTE: Junction tables (schedule_course_links, schedule_courses) still reference course_id & teacher_name.
    # We retain them; no FK changes needed since they don't point to the PK now, only unique pair.


def downgrade() -> None:
    op.drop_constraint(
        "schedule_course_links_course_id_teacher_name_fkey",
        "schedule_course_links",
        type_="foreignkey",
    )

    # Reverse unique constraint
    op.drop_constraint("uq_course_teacher", "courses", type_="unique")

    # Drop primary key on id
    op.drop_constraint("courses_pkey", "courses", type_="primary")

    # Recreate composite primary key
    op.create_primary_key("courses_pkey", "courses", ["course_id", "teacher_name"])    

    op.create_foreign_key(
        "schedule_course_links_course_id_teacher_name_fkey",
        "schedule_course_links",
        "courses",
        ["course_id", "teacher_name"],
        ["course_id", "teacher_name"],
        ondelete="CASCADE",
    )    

    # Make teacher_name NOT NULL again (assumes previous state)
    op.alter_column("courses", "teacher_name", nullable=False)

    # Drop surrogate id column
    op.drop_column("courses", "id")

    # Optionally drop sequence (PostgreSQL); ignore errors if other backend
    try:
        op.execute("DROP SEQUENCE IF EXISTS courses_id_seq")
    except Exception:
        pass
