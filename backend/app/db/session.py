"""Database session and initialization."""
from __future__ import annotations

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session

from app.core.config import settings
from app.models.models import Base

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False},
    echo=False,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db() -> None:
    """Create all tables and enable FTS5 virtual table for knowledge chunks."""
    Base.metadata.create_all(bind=engine)
    _setup_fts()


def _setup_fts() -> None:
    """Create SQLite FTS5 virtual table for knowledge chunk search if not present."""
    with engine.connect() as conn:
        conn.execute(
            text(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_chunks_fts
                USING fts5(
                    chunk_id UNINDEXED,
                    text,
                    tokenize='porter unicode61'
                )
                """
            )
        )
        conn.commit()


def get_db():
    """FastAPI dependency — yields a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
