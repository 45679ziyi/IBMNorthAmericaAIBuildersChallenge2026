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
    _setup_fts(engine)
    _ensure_columns(engine)
    _seed_personas()


def _ensure_columns(target_engine=None) -> None:
    """Add missing columns to existing tables (safe to call multiple times).

    Accepts an optional *target_engine* so the same migrations can be applied
    to both the legacy aurora.db and any per-tenant SQLite file.  Defaults to
    the module-level ``engine`` (aurora.db) for backward compatibility.
    """
    eng = target_engine if target_engine is not None else engine
    with eng.connect() as conn:
        def _cols(table: str) -> set:
            return {r[1] for r in conn.execute(text(f"PRAGMA table_info({table})")).fetchall()}

        # ── announcements ────────────────────────────────────────────────────
        existing = _cols("announcements")
        if "is_read" not in existing:
            conn.execute(text(
                "ALTER TABLE announcements ADD COLUMN is_read BOOLEAN NOT NULL DEFAULT 0"
            ))
        if "read_at_utc" not in existing:
            conn.execute(text("ALTER TABLE announcements ADD COLUMN read_at_utc DATETIME"))

        # ── tasks ────────────────────────────────────────────────────────────
        existing = _cols("tasks")
        if "source_signal_id" not in existing:
            conn.execute(text("ALTER TABLE tasks ADD COLUMN source_signal_id TEXT"))
        if "provenance" not in existing:
            conn.execute(text(
                "ALTER TABLE tasks ADD COLUMN provenance TEXT NOT NULL DEFAULT 'manual'"
            ))

        # ── sim_state ────────────────────────────────────────────────────────
        existing = _cols("sim_state")
        if "director_mode" not in existing:
            conn.execute(text(
                "ALTER TABLE sim_state ADD COLUMN director_mode TEXT NOT NULL DEFAULT 'off'"
            ))
        if "active_persona" not in existing:
            conn.execute(text("ALTER TABLE sim_state ADD COLUMN active_persona TEXT"))
        if "executed_step_ids" not in existing:
            conn.execute(text(
                "ALTER TABLE sim_state ADD COLUMN executed_step_ids TEXT NOT NULL DEFAULT '[]'"
            ))

        # ── signals (V4 additions) ───────────────────────────────────────────
        existing = _cols("signals")
        if "relevance_reason" not in existing:
            conn.execute(text("ALTER TABLE signals ADD COLUMN relevance_reason TEXT"))
        if "data_origin" not in existing:
            conn.execute(text(
                "ALTER TABLE signals ADD COLUMN data_origin TEXT NOT NULL DEFAULT 'synthetic'"
            ))
        if "scenario_id" not in existing:
            conn.execute(text("ALTER TABLE signals ADD COLUMN scenario_id TEXT"))
        if "canonical_event_id" not in existing:
            conn.execute(text("ALTER TABLE signals ADD COLUMN canonical_event_id TEXT"))

        # ── moves (V4 additions) ─────────────────────────────────────────────
        existing = _cols("moves")
        if "canonical_event_id" not in existing:
            conn.execute(text("ALTER TABLE moves ADD COLUMN canonical_event_id TEXT"))
        if "dismissed_at" not in existing:
            conn.execute(text("ALTER TABLE moves ADD COLUMN dismissed_at DATETIME"))
        if "expires_at" not in existing:
            conn.execute(text("ALTER TABLE moves ADD COLUMN expires_at DATETIME"))

        # ── notifications (V4 additions) ─────────────────────────────────────
        existing = _cols("notifications")
        if "idempotency_key" not in existing:
            conn.execute(text("ALTER TABLE notifications ADD COLUMN idempotency_key TEXT"))
        if "work_item_id" not in existing:
            conn.execute(text("ALTER TABLE notifications ADD COLUMN work_item_id TEXT"))

        # ── service_requests (V4 additions) ──────────────────────────────────
        existing = _cols("service_requests")
        if "canonical_event_id" not in existing:
            conn.execute(text("ALTER TABLE service_requests ADD COLUMN canonical_event_id TEXT"))

        # ── entity_links (V4-05 addition) ─────────────────────────────────────
        existing = _cols("entity_links")
        if "meta_json" not in existing:
            conn.execute(text("ALTER TABLE entity_links ADD COLUMN meta_json TEXT"))

        conn.commit()


def _setup_fts(target_engine=None) -> None:
    """Create SQLite FTS5 virtual table for knowledge chunk search if not present."""
    eng = target_engine if target_engine is not None else engine
    with eng.connect() as conn:
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
