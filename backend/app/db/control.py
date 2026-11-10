"""Control-plane database.

Stores the tenants registry in data/control.db — a separate SQLite file from
any tenant database.  Tenant databases live in data/tenants/<id>.db.

U1: silo-tenancy — one DB per tenant, no tenant_id column on tenant tables.
"""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from sqlalchemy import (
    Boolean,
    DateTime,
    Integer,
    String,
    create_engine,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker, Session

# ── Paths ──────────────────────────────────────────────────────────────────────

_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent   # …/backend/
_DATA_DIR = _BACKEND_ROOT / "data"
_TENANTS_DIR = _DATA_DIR / "tenants"
_BACKUPS_DIR = _DATA_DIR / "backups"
_CONTROL_DB = _DATA_DIR / "control.db"


def _ensure_dirs() -> None:
    _DATA_DIR.mkdir(exist_ok=True)
    _TENANTS_DIR.mkdir(exist_ok=True)
    _BACKUPS_DIR.mkdir(exist_ok=True)


def tenant_db_path(tenant_id: str) -> Path:
    return _TENANTS_DIR / f"{tenant_id}.db"


def tenant_db_url(tenant_id: str) -> str:
    return f"sqlite:///{tenant_db_path(tenant_id)}"


# ── Control-plane ORM ──────────────────────────────────────────────────────────

class ControlBase(DeclarativeBase):
    pass


class TenantRecord(ControlBase):
    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)   # slug, e.g. "sbu_demo"
    name: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(32), default="active")  # active | disabled
    db_path: Mapped[str] = mapped_column(String(512))
    pack_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    pack_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)

    def __repr__(self) -> str:
        return f"<TenantRecord id={self.id!r} name={self.name!r}>"


# ── Engine and session ─────────────────────────────────────────────────────────

_control_engine = None
_ControlSession = None


def get_control_engine():
    global _control_engine
    if _control_engine is None:
        _ensure_dirs()
        _control_engine = create_engine(
            f"sqlite:///{_CONTROL_DB}",
            connect_args={"check_same_thread": False},
            echo=False,
        )
        ControlBase.metadata.create_all(bind=_control_engine)
    return _control_engine


def get_control_session() -> Session:
    global _ControlSession
    if _ControlSession is None:
        _ControlSession = sessionmaker(
            autocommit=False, autoflush=False, bind=get_control_engine()
        )
    return _ControlSession()


# ── Bootstrap helper ───────────────────────────────────────────────────────────

def bootstrap_sbu_demo() -> None:
    """Ensure sbu_demo tenant exists in the control plane.

    Called at startup.  Idempotent.
    """
    _ensure_dirs()
    db = get_control_session()
    try:
        existing = db.get(TenantRecord, "sbu_demo")
        if existing is None:
            # Check if data/tenants/sbu_demo.db exists; if not, copy aurora.db
            dest = tenant_db_path("sbu_demo")
            if not dest.exists():
                src = _BACKEND_ROOT / "aurora.db"
                if src.exists():
                    import shutil, datetime as _dt
                    ts = _dt.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
                    (_BACKUPS_DIR / ts).mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, _BACKUPS_DIR / ts / "aurora.db")
                    shutil.copy2(src, dest)
            rec = TenantRecord(
                id="sbu_demo",
                name="SBU Demo",
                status="active",
                db_path=str(dest),
                is_default=True,
            )
            db.add(rec)
            db.commit()
    finally:
        db.close()


def list_tenants() -> list[TenantRecord]:
    db = get_control_session()
    try:
        return db.query(TenantRecord).filter(TenantRecord.status == "active").all()
    finally:
        db.close()


def get_tenant(tenant_id: str) -> TenantRecord | None:
    db = get_control_session()
    try:
        return db.get(TenantRecord, tenant_id)
    finally:
        db.close()
