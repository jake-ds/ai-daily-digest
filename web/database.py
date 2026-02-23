"""SQLite database configuration with SQLAlchemy."""

from sqlalchemy import create_engine, inspect, text
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
    from web.models import article, collection, linkedin_draft, reference_post, style_profile  # noqa: F401
    Base.metadata.create_all(bind=engine)
    migrate_db()


def migrate_db():
    """Run schema migrations for new columns (ALTER TABLE for SQLite)."""
    inspector = inspect(engine)

    # LinkedIn drafts 테이블 마이그레이션
    if "linkedin_drafts" in inspector.get_table_names():
        existing = {col["name"] for col in inspector.get_columns("linkedin_drafts")}
        new_columns = {
            "generation_mode": "VARCHAR(20) DEFAULT 'simple'",
            "analysis": "TEXT",
            "direction": "TEXT",
            "review_notes": "TEXT",
            "evaluation": "TEXT",
            "user_feedback": "TEXT",
            "iteration_count": "INTEGER DEFAULT 1",
            "status": "VARCHAR(20) DEFAULT 'draft'",
            "linkedin_url": "TEXT",
            "published_at": "DATETIME",
            "chat_history": "TEXT",
            "guidelines_checklist": "TEXT",
        }
        with engine.begin() as conn:
            for col_name, col_type in new_columns.items():
                if col_name not in existing:
                    conn.execute(text(
                        f"ALTER TABLE linkedin_drafts ADD COLUMN {col_name} {col_type}"
                    ))

    # Articles 테이블 AI 평가 컬럼 마이그레이션
    if "articles" in inspector.get_table_names():
        existing_articles = {col["name"] for col in inspector.get_columns("articles")}
        article_columns = {
            "ai_score": "FLOAT",
            "linkedin_potential": "FLOAT",
            "eval_data": "TEXT",
        }
        with engine.begin() as conn:
            for col_name, col_type in article_columns.items():
                if col_name not in existing_articles:
                    conn.execute(text(
                        f"ALTER TABLE articles ADD COLUMN {col_name} {col_type}"
                    ))
            # ai_score 인덱스 추가
            if "ai_score" not in existing_articles:
                try:
                    conn.execute(text(
                        "CREATE INDEX ix_articles_ai_score ON articles (ai_score)"
                    ))
                except Exception:
                    pass  # 인덱스 이미 존재

    # Reference posts 테이블 마이그레이션
    if "reference_posts" in inspector.get_table_names():
        existing_ref = {col["name"] for col in inspector.get_columns("reference_posts")}
        ref_columns = {
            "scenario": "VARCHAR(10)",
            "tags": "TEXT",
        }
        with engine.begin() as conn:
            for col_name, col_type in ref_columns.items():
                if col_name not in existing_ref:
                    conn.execute(text(
                        f"ALTER TABLE reference_posts ADD COLUMN {col_name} {col_type}"
                    ))


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
