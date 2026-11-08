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
    _ensure_columns()


def _ensure_columns() -> None:
    """Add missing columns to existing tables (safe to call multiple times)."""
    with engine.connect() as conn:
        # ── announcements ────────────────────────────────────────────────────
        rows = conn.execute(text("PRAGMA table_info(announcements)")).fetchall()
        existing = {row[1] for row in rows}
        if "is_read" not in existing:
            conn.execute(
                text("ALTER TABLE announcements ADD COLUMN is_read BOOLEAN NOT NULL DEFAULT 0")
            )
        if "read_at_utc" not in existing:
            conn.execute(
                text("ALTER TABLE announcements ADD COLUMN read_at_utc DATETIME")
            )

        # ── tasks (V2 additions) ─────────────────────────────────────────────
        rows = conn.execute(text("PRAGMA table_info(tasks)")).fetchall()
        existing = {row[1] for row in rows}
        if "source_signal_id" not in existing:
            conn.execute(
                text("ALTER TABLE tasks ADD COLUMN source_signal_id TEXT")
            )
        if "provenance" not in existing:
            conn.execute(
                text("ALTER TABLE tasks ADD COLUMN provenance TEXT NOT NULL DEFAULT 'manual'")
            )

        conn.commit()


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
