"""Tenant and Actor context — U1.

Every request carries:
  - X-Demo-Tenant header  → TenantContext (which DB to use)
  - X-Demo-Actor  header  → ActorContext  (which persona is acting)

The persona selector is NOT authentication.  Authorization is enforced server-
side in services/authz.  The headers exist only to allow the demo to switch
personas without a real auth layer.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from fastapi import Header, HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from app.db.control import (
    TenantRecord,
    get_tenant,
    tenant_db_url,
)


# ── Engine registry ────────────────────────────────────────────────────────────
# One SQLite engine per tenant — kept alive for the process lifetime.

_TENANT_ENGINES: dict[str, object] = {}  # tenant_id → engine


def _get_tenant_engine(tenant_id: str, db_path: str):
    if tenant_id not in _TENANT_ENGINES:
        url = f"sqlite:///{db_path}"
        engine = create_engine(
            url,
            connect_args={"check_same_thread": False},
            echo=False,
        )
        # Ensure schema is up-to-date for this tenant DB (create tables +
        # apply any missing column migrations added after initial creation).
        from app.models.models import Base
        Base.metadata.create_all(bind=engine)
        # Run column migrations against this tenant engine directly
        from sqlalchemy import text as _text
        with engine.connect() as _conn:
            # sim_state columns
            rows = _conn.execute(_text("PRAGMA table_info(sim_state)")).fetchall()
            existing = {r[1] for r in rows}
            if "director_mode" not in existing:
                _conn.execute(_text(
                    "ALTER TABLE sim_state ADD COLUMN director_mode TEXT NOT NULL DEFAULT 'off'"
                ))
            if "active_persona" not in existing:
                _conn.execute(_text(
                    "ALTER TABLE sim_state ADD COLUMN active_persona TEXT"
                ))
            if "executed_step_ids" not in existing:
                _conn.execute(_text(
                    "ALTER TABLE sim_state ADD COLUMN executed_step_ids TEXT NOT NULL DEFAULT '[]'"
                ))
            # announcements columns
            rows = _conn.execute(_text("PRAGMA table_info(announcements)")).fetchall()
            existing = {r[1] for r in rows}
            if "is_read" not in existing:
                _conn.execute(_text(
                    "ALTER TABLE announcements ADD COLUMN is_read BOOLEAN NOT NULL DEFAULT 0"
                ))
            if "read_at_utc" not in existing:
                _conn.execute(_text(
                    "ALTER TABLE announcements ADD COLUMN read_at_utc DATETIME"
                ))
            # tasks columns
            rows = _conn.execute(_text("PRAGMA table_info(tasks)")).fetchall()
            existing = {r[1] for r in rows}
            if "source_signal_id" not in existing:
                _conn.execute(_text(
                    "ALTER TABLE tasks ADD COLUMN source_signal_id TEXT"
                ))
            if "provenance" not in existing:
                _conn.execute(_text(
                    "ALTER TABLE tasks ADD COLUMN provenance TEXT NOT NULL DEFAULT 'manual'"
                ))
            # FTS5 virtual table
            _conn.execute(_text(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_chunks_fts
                USING fts5(
                    chunk_id UNINDEXED,
                    text,
                    tokenize='porter unicode61'
                )
                """
            ))
            _conn.commit()
        _TENANT_ENGINES[tenant_id] = engine
    return _TENANT_ENGINES[tenant_id]


def _invalidate_engine(tenant_id: str) -> None:
    """Discard a cached engine (e.g. after a pack reload)."""
    _TENANT_ENGINES.pop(tenant_id, None)


# ── Sim-clock registry ─────────────────────────────────────────────────────────
# The virtual clock is per tenant.

_TENANT_CLOCKS: dict[str, Optional[object]] = {}  # tenant_id → datetime | None


def get_tenant_clock(tenant_id: str):
    return _TENANT_CLOCKS.get(tenant_id)


def set_tenant_clock(tenant_id: str, dt) -> None:
    _TENANT_CLOCKS[tenant_id] = dt


# ── TenantContext ──────────────────────────────────────────────────────────────

@dataclass
class TenantContext:
    tenant_id: str
    tenant_name: str
    db_path: str
    is_default: bool


DEFAULT_TENANT_ID = "sbu_demo"


def resolve_tenant(x_demo_tenant: Optional[str] = Header(default=None)) -> TenantContext:
    """FastAPI dependency — resolve the tenant from X-Demo-Tenant header.

    Falls back to sbu_demo when the header is absent.
    Returns 404 for an unknown or disabled tenant.
    """
    tenant_id = (x_demo_tenant or DEFAULT_TENANT_ID).strip().lower()
    rec: Optional[TenantRecord] = get_tenant(tenant_id)
    if rec is None or rec.status != "active":
        raise HTTPException(status_code=404, detail=f"Tenant '{tenant_id}' not found.")
    return TenantContext(
        tenant_id=rec.id,
        tenant_name=rec.name,
        db_path=rec.db_path,
        is_default=rec.is_default,
    )


# ── ActorContext ───────────────────────────────────────────────────────────────

DEFAULT_ACTOR_ID = "student_alex"

# Roles that have personal data (calendar, tasks, announcements).
# Others (facilities, it, academic_ops) do NOT have a personal data row and
# return 403 with an explanation if queried for personal data.
PERSONAS_WITH_PERSONAL_DATA = {
    "student_alex", "student_blake", "student_casey", "student_dana",
}

KNOWN_PERSONAS = {
    "student_alex":       "student",
    "student_blake":      "student",
    "student_casey":      "student",
    "student_dana":       "student",
    "faculty_jordan":     "faculty",
    "faculty_sam":        "faculty",
    "facilities_morgan":  "facilities",
    "it_casey":           "it",
    "acadops_taylor":     "academic_ops",
    "org_riley":          "org_organizer",
}


@dataclass
class ActorContext:
    actor_id: str
    role: str
    tenant_id: str = DEFAULT_TENANT_ID  # server-resolved; never from request body


def resolve_actor(
    x_demo_actor: Optional[str] = Header(default=None),
    x_demo_tenant: Optional[str] = Header(default=None),
) -> ActorContext:
    """FastAPI dependency — resolve the actor from X-Demo-Actor header.

    Falls back to student_alex when the header is absent.
    Returns 400 for an unknown persona.
    tenant_id is server-resolved here so downstream code never reads it from
    request bodies.
    """
    actor_id = (x_demo_actor or DEFAULT_ACTOR_ID).strip()
    if actor_id not in KNOWN_PERSONAS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unknown persona '{actor_id}'. "
                f"Known personas: {sorted(KNOWN_PERSONAS.keys())}"
            ),
        )
    tenant_id = (x_demo_tenant or DEFAULT_TENANT_ID).strip().lower()
    return ActorContext(
        actor_id=actor_id,
        role=KNOWN_PERSONAS[actor_id],
        tenant_id=tenant_id,
    )


# ── user_id helper ─────────────────────────────────────────────────────────────

# Maps persona ID → the user_id (UUID) stored in user_profiles for that tenant.
# For the SBU demo the student personas share the V2 demo user ID; other
# personas get generated stable IDs.  This mapping is loaded lazily from the DB.

_ACTOR_USER_IDS: dict[str, str] = {}

# Legacy V2 demo user — student_alex maps to this for backward compatibility.
_V2_DEMO_USER_ID = "00000000-0000-0000-0000-000000000001"

# Stable placeholder UUIDs for non-student personas (no personal-data rows).
_PLACEHOLDER_IDS: dict[str, str] = {
    "faculty_jordan":    "10000000-0000-0000-0000-000000000001",
    "faculty_sam":       "10000000-0000-0000-0000-000000000002",
    "facilities_morgan": "20000000-0000-0000-0000-000000000001",
    "it_casey":          "30000000-0000-0000-0000-000000000001",
    "acadops_taylor":    "40000000-0000-0000-0000-000000000001",
    "org_riley":         "50000000-0000-0000-0000-000000000001",
}
# Student placeholders for blake/casey/dana (they can be added in U2 pack load)
_PLACEHOLDER_IDS.update({
    "student_blake": "00000000-0000-0000-0000-000000000002",
    "student_casey": "00000000-0000-0000-0000-000000000003",
    "student_dana":  "00000000-0000-0000-0000-000000000004",
})


def current_user_id(actor: ActorContext) -> str:
    """Return the user_profiles.id for this actor.

    student_alex → settings.demo_user_id  (backward compat — tests monkeypatch
    this value so the test isolation is preserved automatically).
    All others → stable placeholder UUIDs (no personal-data rows in V2 DB).
    """
    if actor.actor_id == "student_alex":
        from app.core.config import settings
        return settings.demo_user_id
    return _PLACEHOLDER_IDS.get(actor.actor_id, actor.actor_id)


# ── Tenant-aware get_db ────────────────────────────────────────────────────────

def make_tenant_get_db(tenant: TenantContext):
    """Return a FastAPI dependency that yields a DB session for this tenant."""
    engine = _get_tenant_engine(tenant.tenant_id, tenant.db_path)

    def _get_db() -> Session:
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    return _get_db
