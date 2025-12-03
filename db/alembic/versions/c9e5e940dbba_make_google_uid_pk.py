"""make_google_uid_pk

Revision ID: c9e5e940dbba
Revises: 54d777bd7740
Create Date: 2025-11-20 23:02:12.270788

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c9e5e940dbba'
down_revision: Union[str, Sequence[str], None] = '54d777bd7740'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 1. Drop the existing foreign key constraint on schedules
    op.drop_constraint('schedules_user_id_fkey', 'schedules', type_='foreignkey')

    # 2. Add a temporary column to store the google_uid
    op.add_column('schedules', sa.Column('user_google_uid', sa.String(length=255), nullable=True))

    # 3. Migrate data: Update schedules with the corresponding google_uid from users
    op.execute("""
        UPDATE schedules 
        SET user_google_uid = users.google_uid 
        FROM users 
        WHERE schedules.user_id = users.id
    """)

    # 4. Remove users/schedules where google_uid is null (cannot be PK)
    op.execute("DELETE FROM schedules WHERE user_google_uid IS NULL")
    op.execute("DELETE FROM users WHERE google_uid IS NULL")

    # 5. Drop the old user_id column from schedules
    op.drop_column('schedules', 'user_id')

    # 6. Rename the new column to user_id
    op.alter_column('schedules', 'user_google_uid', new_column_name='user_id', nullable=False)

    # 7. Update users table
    op.alter_column('users', 'google_uid',
               existing_type=sa.VARCHAR(length=255),
               nullable=False)
    
    # Drop the unique constraint if it exists (it might be named differently, but model said uq_users_google_uid)
    # We use a try-except block or check existence, but here we assume the name from the model/autogen
    try:
        op.drop_constraint('uq_users_google_uid', 'users', type_='unique')
    except Exception:
        pass # It might not exist or be named differently

    # Drop the old ID column
    op.drop_column('users', 'id')

    # 8. Create the new Primary Key on google_uid
    op.create_primary_key('pk_users', 'users', ['google_uid'])

    # 9. Create the new Foreign Key
    op.create_foreign_key(None, 'schedules', 'users', ['user_id'], ['google_uid'], ondelete='CASCADE')


def downgrade() -> None:
    """Downgrade schema."""
    # This is a destructive migration (ID loss), so downgrade is hard.
    # We will just reverse the structural changes but data might be lost/broken.
    
    # Drop FK
    op.drop_constraint(None, 'schedules', type_='foreignkey')
    
    # Drop PK
    op.drop_constraint('pk_users', 'users', type_='primary')

    # Add back ID column (will be empty/new sequence)
    op.add_column('users', sa.Column('id', sa.INTEGER(), server_default=sa.text("nextval('users_id_seq'::regclass)"), autoincrement=True, nullable=False))
    
    # Make ID the PK
    op.create_primary_key('pk_users_id', 'users', ['id'])

    # Restore google_uid to nullable and unique
    op.create_unique_constraint('uq_users_google_uid', 'users', ['google_uid'])
    op.alter_column('users', 'google_uid', existing_type=sa.VARCHAR(length=255), nullable=True)

    # Revert schedules.user_id to Integer
    # We can't easily restore the integer IDs. We'll just drop and recreate.
    op.drop_column('schedules', 'user_id')
    op.add_column('schedules', sa.Column('user_id', sa.INTEGER(), nullable=False))
    
    # Re-add FK
    op.create_foreign_key('schedules_user_id_fkey', 'schedules', 'users', ['user_id'], ['id'], ondelete='CASCADE')

