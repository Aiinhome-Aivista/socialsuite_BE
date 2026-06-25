"""
Quick-start DB initializer. Creates all tables.

    python -m app.init_db

For production use Alembic migrations instead so schema changes are versioned:
    alembic init alembic   (then point env.py at app.database.Base.metadata)
"""
from app.database import Base, engine
import app.models  # noqa: F401  (imports register all tables on Base)


def main():
    Base.metadata.create_all(bind=engine)
    print("All tables created.")


if __name__ == "__main__":
    main()
