# Database Management

This directory contains all database-related files including models, session management, and Alembic migrations.

## Directory Structure

```
db/
├── alembic/              # Migration scripts directory
│   ├── versions/         # Individual migration files
│   ├── env.py           # Alembic environment configuration
│   └── script.py.mako   # Migration template
├── models.py            # SQLAlchemy ORM models
├── session.py           # Database session management
└── README.md            # This file
```

## Database Configuration

Database connection is configured via the `DATABASE_URL` environment variable in your `.env` file:

```
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/backend
```
(the '+asyncpg' is important for making sure that calls to the db are async)

## Starting the Database

### Using Docker Compose (Recommended)

```bash
docker-compose up -d db
```

This starts PostgreSQL 18 on port 5432.

### Using Local PostgreSQL

Ensure PostgreSQL 18 is installed and running, then create the database:

```bash
createdb backend
```

## Migration Commands

### Check Current Migration Status

```bash
alembic current
```

Shows which migration is currently applied.

### View Migration History

```bash
alembic history --verbose
```

Shows all available migrations and their status.

### Create a New Migration

After modifying models in `models.py`:

```bash
alembic revision --autogenerate -m "Description of changes"
```

This auto-generates a migration file in `db/alembic/versions/`.

**Important:** Always review the generated migration file before applying it. Alembic may not detect all changes (like renamed columns or tables).

### Apply Migrations

Apply all pending migrations:

```bash
alembic upgrade head
```

Apply migrations up to a specific revision:

```bash
alembic upgrade <revision_id>
```

### Rollback Migrations

Rollback the last migration:

```bash
alembic downgrade -1
```

Rollback to a specific revision:

```bash
alembic downgrade <revision_id>
```

Rollback all migrations:

```bash
alembic downgrade base
```

### Show SQL Without Executing

Preview SQL that would be executed:

```bash
alembic upgrade head --sql
```

## How to Change Database Schema

### Step-by-Step Workflow

1. **Modify the models** in `db/models.py`

   Example - Adding a new column:
   ```python
   class User(Base):
       # ... existing fields ...
       bio: Mapped[str | None] = mapped_column(Text, nullable=True)
   ```

2. **Generate the migration**
   ```bash
   alembic revision --autogenerate -m "Add bio column to users table"
   ```

3. **Review the migration file** in `db/alembic/versions/`

   Check that:
   - All changes are captured correctly
   - The upgrade() and downgrade() functions are correct
   - No unwanted changes are included

4. **Apply the migration**
   ```bash
   alembic upgrade head
   ```

5. **Commit to version control**
   ```bash
   git add db/models.py db/alembic/versions/<new_migration_file>.py
   git commit -m "Add bio column to users table"
   ```

### Common Schema Changes

#### Adding a Column

```python
# In models.py
phone_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
```

Then run:
```bash
alembic revision --autogenerate -m "Add phone_number to users"
alembic upgrade head
```

#### Removing a Column

```python
# In models.py - delete the column definition
# old_field: Mapped[str] = mapped_column(String(100))  # Remove this line
```

Then run:
```bash
alembic revision --autogenerate -m "Remove old_field from users"
alembic upgrade head
```

#### Adding a New Table

```python
# In models.py
class NewTable(Base):
    __tablename__ = "new_table"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
```

Then run:
```bash
alembic revision --autogenerate -m "Add new_table"
alembic upgrade head
```

#### Renaming a Column (Manual)

Alembic doesn't auto-detect renames, so you need to manually edit the migration:

```python
# In the generated migration file
def upgrade() -> None:
    op.alter_column('users', 'old_name', new_column_name='new_name')

def downgrade() -> None:
    op.alter_column('users', 'new_name', new_column_name='old_name')
```

## Database Models

### Current Models

- **User** - User accounts with authentication
- **Schedule** - User schedules
- **Course** - Course catalog
- **ScheduleActivity** - Activities within schedules
- **ScheduleCourse** - Junction table for Schedule-Course relationship

See `models.py` for full model definitions.

## Important Notes

### What Alembic Auto-Detects

- Adding/removing tables
- Adding/removing columns
- Adding/removing indexes
- Changing column nullable status
- Some constraint changes

### What Alembic Does NOT Auto-Detect

- Table renames
- Column renames
- Column type changes (sometimes)
- Custom CHECK constraints
- Sequence changes

For these changes, manually edit the migration file or create a manual migration:

```bash
alembic revision -m "Manual migration description"
```

### Best Practices

1. **Never modify applied migrations** - Once a migration is applied to production, don't change it
2. **Always review auto-generated migrations** - Alembic isn't perfect
3. **Test migrations in development first** - Apply and test before pushing to production
4. **Keep migrations small and focused** - One logical change per migration
5. **Write descriptive migration messages** - Future you will thank you
6. **Commit migrations with code changes** - Keep them in sync

### Production Deployment

When deploying to production:

1. Backup the database first
2. Run migrations before starting the new application code:
   ```bash
   alembic upgrade head
   ```
3. Start the application

### Troubleshooting

#### "Target database is not up to date"

Your database is behind. Run:
```bash
alembic upgrade head
```

#### "Can't locate revision identified by 'xyz'"

The migration file might be missing. Check `db/alembic/versions/` directory.

#### Migration conflicts

If multiple developers created migrations simultaneously:
```bash
alembic merge <rev1> <rev2> -m "Merge migrations"
```

#### Reset everything (DANGEROUS - loses all data)

```bash
alembic downgrade base
alembic upgrade head
```

Or drop and recreate the database:
```bash
dropdb backend
createdb backend
alembic upgrade head
```

## Manual Database Operations

### Connect to Database

```bash
psql -U postgres -d backend
```

Or using Docker:
```bash
docker-compose exec db psql -U postgres -d backend
```

### View Tables

```sql
\dt
```

### Describe Table Structure

```sql
\d users
```

### View Data

```sql
SELECT * FROM users LIMIT 10;
```

## Additional Resources

- [Alembic Documentation](https://alembic.sqlalchemy.org/)
- [SQLAlchemy Documentation](https://docs.sqlalchemy.org/)
- [PostgreSQL Documentation](https://www.postgresql.org/docs/)
