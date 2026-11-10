"""Tenant endpoints — U2.

GET /tenant/config  → TenantConfigResponse (time_zone, clock, role_vocabulary, …)
GET /tenants        → list[TenantSummary] (all active tenants)
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.tenancy import TenantContext, resolve_tenant
from app.db.session import get_db

router = APIRouter(tags=["tenant"])


# ── Schemas ────────────────────────────────────────────────────────────────────

class TenantConfigResponse(BaseModel):
    tenant_id: str
    time_zone: str
    clock: str                          # "12h" | "24h"
    week_start: str                     # "sunday" | "monday"
    course_code_format: str
    room_code_format: str
    credit_unit: str
    role_vocabulary: dict[str, str]
    min_cell_size: int


class TenantSummary(BaseModel):
    id: str
    name: str
    is_default: bool


# ── Routes ─────────────────────────────────────────────────────────────────────

@router.get("/tenant/config", response_model=TenantConfigResponse)
def get_tenant_config(
    tenant: TenantContext = Depends(resolve_tenant),
    db: Session = Depends(get_db),
):
    """Return the tenant's configuration from its pack."""
    from app.models.models import TenantConfig
    cfg = db.query(TenantConfig).first()

    if cfg is None:
        # Fall back to defaults for the legacy DB (pre-pack-load)
        return TenantConfigResponse(
            tenant_id=tenant.tenant_id,
            time_zone="America/New_York",
            clock="12h",
            week_start="sunday",
            course_code_format="{d} {n}",
            room_code_format="{b} {r}",
            credit_unit="credits",
            role_vocabulary={},
            min_cell_size=5,
        )

    return TenantConfigResponse(
        tenant_id=cfg.tenant_id,
        time_zone=cfg.timezone,
        clock=cfg.clock,
        week_start=cfg.week_start,
        course_code_format=cfg.course_code_format,
        room_code_format=cfg.room_code_format,
        credit_unit=cfg.credit_unit,
        role_vocabulary=json.loads(cfg.role_vocabulary or "{}"),
        min_cell_size=cfg.min_cell_size,
    )


@router.get("/tenants", response_model=list[TenantSummary])
def list_active_tenants():
    """Return all active tenants (for the tenant switcher)."""
    from app.db.control import list_tenants
    tenants = list_tenants()
    return [
        TenantSummary(id=t.id, name=t.name, is_default=t.is_default)
        for t in tenants
    ]
