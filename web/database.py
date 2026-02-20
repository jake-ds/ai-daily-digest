"""SQLite database configuration with SQLAlchemy."""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from contextlib import contextmanager

from web.config import DATABASE_URL, DATA_DIR

# Ensure data directory exists
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Create engine
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},  # SQLite specific
    echo=False,
)

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for models
Base = declarative_base()


def init_db():
    """Initialize database tables."""
    from web.models import article, collection, linkedin_draft  # noqa: F401
    Base.metadata.create_all(bind=engine)


def get_db():
    """Dependency for FastAPI to get DB session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def get_db_session():
    """Context manager for DB session (for use outside FastAPI)."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
