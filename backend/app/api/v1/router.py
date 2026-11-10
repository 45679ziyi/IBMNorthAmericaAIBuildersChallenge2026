"""API v1 router — aggregates all endpoint sub-routers."""
from fastapi import APIRouter

from app.api.v1 import (
    health,
    events,
    tasks,
    announcements,
    plans,
    assistant,
    connectors,
    pulse,
    demo,
    security,
    sim,
    moves as moves_router,
    autonomy,
    calendar_export,
    ops,
    identity,
    tenant,
    canonical_events,
    work_items,
    inbox,
    threads,
    service_requests,
    campus,
    course_updates,
    trust,
    scenarios,
)

api_router = APIRouter()

api_router.include_router(health.router, tags=["health"])
api_router.include_router(identity.router, tags=["identity"])   # U1
api_router.include_router(tenant.router, tags=["tenant"])       # U2
api_router.include_router(events.router, prefix="/events", tags=["events"])
api_router.include_router(tasks.router, prefix="/tasks", tags=["tasks"])
api_router.include_router(announcements.router, prefix="/announcements", tags=["announcements"])
api_router.include_router(plans.router, prefix="/plans", tags=["plans"])
api_router.include_router(assistant.router, tags=["assistant"])
api_router.include_router(connectors.router, prefix="/connectors", tags=["connectors"])
api_router.include_router(pulse.router, prefix="/campus-pulse", tags=["campus-pulse"])
api_router.include_router(demo.router, tags=["demo"])
api_router.include_router(security.router, prefix="/security", tags=["security"])
api_router.include_router(sim.router, prefix="/sim", tags=["sim"])
api_router.include_router(sim.feeds_router, tags=["sim"])
api_router.include_router(moves_router.router, prefix="/moves", tags=["moves"])
api_router.include_router(autonomy.router, prefix="/autonomy", tags=["autonomy"])
api_router.include_router(calendar_export.router, prefix="/calendar", tags=["calendar"])
api_router.include_router(ops.router, prefix="/ops", tags=["ops"])
api_router.include_router(canonical_events.router, prefix="/canonical-events", tags=["canonical-events"])  # U3
api_router.include_router(work_items.router, prefix="/work-items", tags=["work-items"])  # U3
api_router.include_router(inbox.router, prefix="/inbox", tags=["inbox"])  # U4
api_router.include_router(threads.router, prefix="/canonical-events", tags=["threads"])  # U4
api_router.include_router(service_requests.router, prefix="/service-requests", tags=["service-requests"])  # U4
api_router.include_router(campus.router, tags=["campus"])                         # U5-3
api_router.include_router(course_updates.router, prefix="/course-updates", tags=["course-updates"])  # U5-5
api_router.include_router(trust.router, prefix="/trust", tags=["trust"])          # U6-6
api_router.include_router(scenarios.router, prefix="/scenarios", tags=["scenarios"])  # V4-05
