"""Database session and initialization.

U1: get_db is now tenant-aware.  It reads X-Demo-Tenant from the request
headers (via TenantContext) to choose the correct per-tenant SQLite file.
Falls back to the legacy aurora.db for backward compatibility when no tenant
context is present (e.g. scripts, background tasks, old tests).
"""
from __future__ import annotations

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session

from app.core.config import settings
from app.models.models import Base

# ── Legacy single-database engine (kept for scripts and backward compat) ───────
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
    _seed_personas()


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

        # ── sim_state (U3 additions) ─────────────────────────────────────────
        rows = conn.execute(text("PRAGMA table_info(sim_state)")).fetchall()
        existing = {row[1] for row in rows}
        if "director_mode" not in existing:
            conn.execute(text("ALTER TABLE sim_state ADD COLUMN director_mode TEXT NOT NULL DEFAULT 'off'"))
        if "active_persona" not in existing:
            conn.execute(text("ALTER TABLE sim_state ADD COLUMN active_persona TEXT"))
        if "executed_step_ids" not in existing:
            conn.execute(text("ALTER TABLE sim_state ADD COLUMN executed_step_ids TEXT NOT NULL DEFAULT '[]'"))

        # ── course_updates (U5-5) — create via create_all but ensure if missed ─
        # Tables are created by Base.metadata.create_all at startup, so no ALTER needed

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


def _seed_personas() -> None:
    """Idempotently seed demo personas into the default (legacy) DB."""
    try:
        from app.services.identity.personas import seed_personas
        db = SessionLocal()
        try:
            seed_personas(db)
        finally:
            db.close()
    except Exception:
        pass  # Non-fatal: personas are seeded per-tenant by pack loader in U2


def get_db():
    """FastAPI dependency — yields a database session.

    U1: when a TenantContext is available on the request this returns a session
    for that tenant's database.  Absent a tenant header it falls back to the
    legacy aurora.db so existing tests and scripts continue to work unchanged.

    The tenant-aware path is installed by main.py via a middleware that injects
    the correct dependency override per-request.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_tenant_db(db_path: str) -> Session:
    """Return a Session for a specific tenant DB path.

    Used by the request middleware to provide a tenant-aware session.
    This function is NOT a FastAPI dependency itself; it is called by the
    dependency override installed per request.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.core.tenancy import _get_tenant_engine
    # Extract tenant_id from db_path (last component without .db)
    from pathlib import Path
    tenant_id = Path(db_path).stem
    eng = _get_tenant_engine(tenant_id, db_path)
    SL = sessionmaker(autocommit=False, autoflush=False, bind=eng)
    return SL()
