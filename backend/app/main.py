"""AURORA Backend — Application entry point.

U1: Per-request tenant-aware DB.

Every request is inspected for X-Demo-Tenant and X-Demo-Actor headers.
The correct per-tenant SQLite engine is selected from the engine registry,
and X-Tenant + X-Auth-Mode headers are added to every response.
"""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from app.api.v1.router import api_router
from app.db.session import init_db, get_db
from app.core.config import settings

app = FastAPI(
    title="AURORA Campus Intelligence API",
    description=(
        "AURORA is an independent educational prototype. "
        "Not affiliated with, endorsed by, or operated by Stony Brook University or IBM."
    ),
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class TenantMiddleware(BaseHTTPMiddleware):
    """Per-request tenant resolution and response header injection.

    1. Reads X-Demo-Tenant (default: sbu_demo).
    2. Looks up the tenant's DB path in the control plane.
    3. Overrides the get_db FastAPI dependency so all route handlers
       receive a session connected to the correct tenant database.
    4. Adds X-Tenant and X-Auth-Mode to every response.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        from app.db.control import get_tenant, bootstrap_sbu_demo
        from app.core.tenancy import (
            DEFAULT_TENANT_ID, _get_tenant_engine,
            set_tenant_clock, get_tenant_clock,
        )
        from sqlalchemy.orm import sessionmaker
        from pathlib import Path

        # Resolve tenant.
        # When get_db is already overridden (test isolation), skip the tenant
        # lookup entirely and let the test's own dependency handle the DB.
        already_overridden = get_db in app.dependency_overrides

        raw = request.headers.get("x-demo-tenant", DEFAULT_TENANT_ID).strip().lower()

        if already_overridden:
            # Tests inject their own DB; don't do a control-plane lookup.
            tenant_id = raw
            rec = None
        else:
            try:
                rec = get_tenant(raw)
            except Exception:
                rec = None

            if rec is None or rec.status != "active":
                from fastapi.responses import JSONResponse
                return JSONResponse(
                    status_code=404,
                    content={"detail": f"Tenant '{raw}' not found."},
                )
            tenant_id = rec.id

        db_path = rec.db_path if rec else None

        # Install per-tenant get_db only when the test hasn't already done so.
        if not already_overridden and db_path:
            engine = _get_tenant_engine(tenant_id, db_path)
            TenantSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)

            def _tenant_get_db():
                db = TenantSession()
                try:
                    yield db
                finally:
                    db.close()

            app.dependency_overrides[get_db] = _tenant_get_db

        response = await call_next(request)

        # Only clean up the override we installed.
        if not already_overridden and db_path:
            app.dependency_overrides.pop(get_db, None)

        # Add U1 response headers
        response.headers["X-Tenant"] = tenant_id
        response.headers["X-Auth-Mode"] = "demo-persona"
        return response


app.add_middleware(TenantMiddleware)


@app.on_event("startup")
async def on_startup() -> None:
    init_db()
    # Bootstrap control plane and register sbu_demo tenant
    from app.db.control import bootstrap_sbu_demo
    bootstrap_sbu_demo()


app.include_router(api_router, prefix="/api/v1")
