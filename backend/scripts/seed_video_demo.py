"""Seed a rich, video-demo-ready dataset into the AURORA tenant database.

This script fills every major table with realistic data so that every
screen in the AURORA UI has meaningful content when recording a demo video.

Scenario: "Disrupted Tuesday" — a mid-morning HVAC fault in Javits 101
cascades into a room change, a weather alert, a career fair conflict, and a
team meeting request.  Every role (student, faculty, facilities, IT, academic
ops, organizer) has relevant moves and notifications.

Usage (from backend/ directory with venv active):
    python -m scripts.seed_video_demo

Run once after start.sh has created the DB.  Idempotent — safe to re-run.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text

from app.db.session import SessionLocal, init_db
from app.db.control import get_tenant, bootstrap_sbu_demo, tenant_db_path, get_control_session
from app.core.tenancy import _get_tenant_engine
from sqlalchemy.orm import sessionmaker
from app.models.models import (
    # Legacy / student-side
    UserProfile, UserPreference, ConsentGrant,
    Task, Announcement, CampusEvent,
    KnowledgeDocument, KnowledgeChunk, SensorReading,
    # Personas / teams
    Person, Team, TeamMembership, RoleAssignment,
    # Simulation / signals
    SimState, Signal, Move, ActionLog,
    # Canonical workflow
    CanonicalEvent, WorkItem, WorkItemTransition,
    # Notifications
    Notification, NotificationPref, AccessLog,
    # Threads / service requests
    Thread, ThreadMessage, ServiceRequest,
    # Faculty
    CourseUpdate,
    # Scenario
    ScenarioRun,
    # Audit
    AuditEvent,
)

# ── Anchor date/time ──────────────────────────────────────────────────────────
# We pin to a Tuesday in the demo week so "today" always looks right.
ANCHOR = datetime(2026, 11, 11, 0, 0, 0, tzinfo=timezone.utc)  # Tuesday
def _dt(h: int, m: int = 0, day_offset: int = 0) -> datetime:
    return ANCHOR + timedelta(days=day_offset, hours=h, minutes=m)

NOW = _dt(10, 35)  # mid-morning, after the HVAC incident fired

TENANT = "sbu_demo"

# ── Persona IDs (from pack) ───────────────────────────────────────────────────
STUDENT_ALEX    = "student_alex"
STUDENT_BLAKE   = "student_blake"
FAC_JORDAN      = "faculty_jordan"
FAC_SAM         = "faculty_sam"
FACILITIES_MORGAN = "facilities_morgan"
IT_CASEY        = "it_casey"
ACADOPS_TAYLOR  = "acadops_taylor"
ORG_RILEY       = "org_riley"

TEAM_FAC_1      = "team-facilities-1"
TEAM_IT_2       = "team-it-2"
TEAM_ACADOPS    = "team-academic_ops-1"

# ── Canonical event IDs ───────────────────────────────────────────────────────
CE_HVAC         = "ce-hvac-jav101-2026111"
CE_ROOM_CHANGE  = "ce-roomchg-cse214-20261111"
CE_CAREER_FAIR  = "ce-careerfair-20261111"
CE_WIFI         = "ce-wifi-mel-20261111"


# ─────────────────────────────────────────────────────────────────────────────
def seed_all() -> None:
    init_db()

    # Legacy DB (student side)
    legacy = SessionLocal()
    try:
        _seed_legacy(legacy)
        legacy.commit()
    finally:
        legacy.close()

    # Tenant DB (staff / ops side) — locate via control plane
    bootstrap_sbu_demo()
    rec = get_tenant(TENANT)
    if rec is None:
        # Fallback: use data/tenants/sbu_demo.db directly
        db_path = str(tenant_db_path(TENANT))
    else:
        db_path = rec.db_path

    eng = _get_tenant_engine(TENANT, db_path)
    TenantSession = sessionmaker(autocommit=False, autoflush=False, bind=eng)
    tenant_db = TenantSession()
    try:
        _seed_tenant(tenant_db)
        tenant_db.commit()
    finally:
        tenant_db.close()

    print("✅  Video demo seed complete.")
    print("    Open http://localhost:5173 and switch personas to explore.")


# ─────────────────────────────────────────────────────────────────────────────
# LEGACY DB  (UserProfile, Tasks, Announcements, CampusEvents, Knowledge)
# ─────────────────────────────────────────────────────────────────────────────
def _seed_legacy(db) -> None:
    _upsert_user(db)
    _upsert_tasks(db)
    _upsert_announcements(db)
    _upsert_campus_events(db)
    _upsert_knowledge(db)
    _upsert_sensors(db)
    db.flush()


def _upsert_user(db) -> None:
    if db.get(UserProfile, STUDENT_ALEX):
        return
    user = UserProfile(
        id=STUDENT_ALEX,
        display_name="Alex Chen (Demo Student)",
        timezone="America/New_York",
    )
    db.add(user)
    db.flush()
    db.add(UserPreference(
        user_id=STUDENT_ALEX,
        day_start_time="08:00",
        day_end_time="22:00",
        preferred_focus_block_minutes=50,
        short_break_minutes=10,
        long_break_minutes=30,
        default_travel_buffer_minutes=10,
    ))
    for src, purpose in [
        ("ics_import",        "Display imported calendar events in the planner."),
        ("brightspace_demo",  "Show demo announcements (synthetic data only)."),
        ("campus_knowledge",  "Answer campus questions from the public knowledge base."),
    ]:
        db.add(ConsentGrant(
            user_id=STUDENT_ALEX, source_type=src, purpose=purpose,
            granted=True, granted_at=datetime.now(timezone.utc),
        ))
    db.flush()


def _upsert_tasks(db) -> None:
    tasks = [
        # Overdue — shows urgency badge
        dict(id="vd-task-01", title="CSE 213 Programming Assignment 3",
             description="Implement a generic stack using Java generics. Submit to Brightspace.",
             course_label="CSE 213", due_at_utc=_dt(23, 59, -1),
             estimated_minutes=120, priority="urgent", status="in_progress",
             provenance="brightspace"),
        # Due today
        dict(id="vd-task-02", title="Review MAT 203 Chapter 14 Notes",
             description="Partial derivatives and multiple integrals — quiz Thursday.",
             course_label="MAT 203", due_at_utc=_dt(23, 59, 0),
             estimated_minutes=60, priority="high", status="todo",
             provenance="manual"),
        # Created by AI from announcement
        dict(id="vd-task-03", title="Prepare for MAT 203 Quiz 4",
             description="Quiz 4 is Thursday at 12:30 PM. Topics: Ch 14 §1-3.",
             course_label="MAT 203", due_at_utc=_dt(12, 30, 3),
             estimated_minutes=90, priority="high", status="todo",
             provenance="signal", source_signal_id="vd-sig-004"),
        # Group project — in-progress
        dict(id="vd-task-04", title="CSE 316 Group Project — Introduction Section",
             description="Draft problem statement and motivation. 500-700 words.",
             course_label="CSE 316", due_at_utc=_dt(17, 0, 3),
             estimated_minutes=90, priority="high", status="in_progress",
             provenance="brightspace"),
        # Low-priority misc
        dict(id="vd-task-05", title="Email Prof. Jordan about office hours",
             description="Ask about the upcoming midterm review session.",
             course_label=None, due_at_utc=None,
             estimated_minutes=10, priority="low", status="todo",
             provenance="manual"),
        # Binary search trees reading
        dict(id="vd-task-06", title="Read CSE 214 Ch 5 — Binary Search Trees",
             description="Complete textbook reading and practice problems.",
             course_label="CSE 214", due_at_utc=_dt(23, 59, 2),
             estimated_minutes=60, priority="normal", status="todo",
             provenance="manual"),
        # Done — shows completed state
        dict(id="vd-task-07", title="Submit CSE 316 Milestone 1",
             description="Background and related work section.",
             course_label="CSE 316", due_at_utc=_dt(17, 0, -7),
             estimated_minutes=90, priority="high", status="done",
             provenance="brightspace"),
    ]
    for t in tasks:
        if db.get(Task, t["id"]):
            continue
        db.add(Task(
            id=t["id"], user_id=STUDENT_ALEX,
            title=t["title"], description=t["description"],
            course_label=t.get("course_label"),
            due_at_utc=t.get("due_at_utc"),
            estimated_minutes=t["estimated_minutes"],
            priority=t["priority"], status=t["status"],
            source_type="demo",
            provenance=t.get("provenance", "manual"),
            source_signal_id=t.get("source_signal_id"),
        ))
    db.flush()


def _upsert_announcements(db) -> None:
    anns = [
        dict(id="vd-ann-01", course_label="CSE 213",
             title="⚠️  Assignment 3 — Final Reminder",
             body_summary="Assignment 3 is due TONIGHT at 11:59 PM. Implement a generic stack in Java. Late submissions incur a 20% penalty per day.",
             published_at_utc=_dt(8, 0, 0), is_read=False),
        dict(id="vd-ann-02", course_label="MAT 203",
             title="Quiz 4 on Thursday — Chapter 14",
             body_summary="Reminder: Quiz 4 is Thursday at 12:30 PM. Topics: partial derivatives and multiple integrals (Ch 14, §1–3). Bring a calculator.",
             published_at_utc=_dt(8, 5, 0), is_read=False),
        dict(id="vd-ann-03", course_label="CSE 214",
             title="TODAY: Class moved to Javits 101",
             body_summary="Due to projector maintenance in LE 201, today's CSE 214 lecture (10:00 AM) will be held in Javits 101. Please plan accordingly.",
             published_at_utc=_dt(9, 10, 0), is_read=False),
        dict(id="vd-ann-04", course_label="CSE 316",
             title="Milestone 2 Due November 14",
             body_summary="Milestone 2 (introduction and background sections) is due November 14 at 5:00 PM. Submit via the group portal. Contact your TA with questions.",
             published_at_utc=_dt(16, 0, -7), is_read=True,
             read_at_utc=_dt(17, 30, -7)),
        dict(id="vd-ann-05", course_label="CSE 214",
             title="Midterm Grades Posted",
             body_summary="Midterm grades are now visible in the grade centre. Extended office hours this week: Mon/Wed 3–5 PM in CS 2101.",
             published_at_utc=_dt(9, 0, -14), is_read=True,
             read_at_utc=_dt(10, 0, -14)),
        dict(id="vd-ann-06", course_label="CSE 213",
             title="Programming Assignment 3 Posted",
             body_summary="Assignment 3 is now available on Brightspace. Implement a generic stack using Java generics. See full spec for requirements. Due Nov 11 at 11:59 PM.",
             published_at_utc=_dt(14, 0, -12), is_read=True,
             read_at_utc=_dt(15, 0, -12)),
    ]
    for a in anns:
        if db.get(Announcement, a["id"]):
            continue
        db.add(Announcement(
            id=a["id"], user_id=STUDENT_ALEX,
            course_label=a["course_label"], title=a["title"],
            body_summary=a["body_summary"],
            published_at_utc=a["published_at_utc"],
            source_type="demo",
            is_read=a.get("is_read", False),
            read_at_utc=a.get("read_at_utc"),
        ))
    db.flush()


def _upsert_campus_events(db) -> None:
    events = [
        dict(id="vd-ce-01",
             title="Fall Career Fair 2026 — TODAY (moved up!)",
             description="Annual fall career fair. 80+ employers. Bring your résumé. Moved from Thursday to TODAY 2:00–5:00 PM.",
             start_at_utc=_dt(14, 0, 0), end_at_utc=_dt(17, 0, 0),
             location_text="SAC Ballroom (SAC-BALL)",
             source_title="SBU Career Center (Demo)",
             source_url="https://www.stonybrook.edu/commcms/career-center/"),
        dict(id="vd-ce-02",
             title="CS Colloquium: AI in Healthcare",
             description="Speaker: Dr. Alex Rivera (fictional). Topic: Responsible AI in Clinical Decision Support.",
             start_at_utc=_dt(17, 0, 1), end_at_utc=_dt(18, 0, 1),
             location_text="Computer Science Building, Room 2311",
             source_title="SBU CS Department (Demo)",
             source_url="https://www.cs.stonybrook.edu/"),
        dict(id="vd-ce-03",
             title="Library Research Workshop: Peer-Reviewed Sources",
             description="Learn to search peer-reviewed articles using SBU Library databases. Open to all undergrads.",
             start_at_utc=_dt(10, 0, 2), end_at_utc=_dt(11, 0, 2),
             location_text="Melville Library, Room N2017",
             source_title="SBU Libraries (Demo)",
             source_url="https://library.stonybrook.edu/"),
        dict(id="vd-ce-04",
             title="Hackathon: Build with AI",
             description="24-hour hackathon. Teams of 2–4. IBM API credits provided. Sign up before Thursday.",
             start_at_utc=_dt(9, 0, 4), end_at_utc=_dt(9, 0, 5),
             location_text="SAC Main Hall",
             source_title="SBU IEEE Chapter (Demo)",
             source_url="https://www.stonybrook.edu/"),
        dict(id="vd-ce-05",
             title="Student Association Movie Night",
             description="Free screening. Popcorn provided. All students welcome.",
             start_at_utc=_dt(20, 0, 3), end_at_utc=_dt(22, 30, 3),
             location_text="Stony Brook Union Auditorium",
             source_title="USG (Demo)",
             source_url="https://www.stonybrook.edu/commcms/usg/"),
    ]
    for e in events:
        if db.get(CampusEvent, e["id"]):
            continue
        db.add(CampusEvent(
            id=e["id"], title=e["title"], description=e["description"],
            start_at_utc=e["start_at_utc"], end_at_utc=e["end_at_utc"],
            location_text=e["location_text"],
            source_title=e["source_title"], source_url=e["source_url"],
            is_demo_data=True,
        ))
    db.flush()


def _upsert_knowledge(db) -> None:
    docs = [
        dict(id="vd-kd-01",
             title="Campus Room Change Policy",
             publisher="SBU Registrar (Demo)",
             url="https://registrar.example.invalid/room-change",
             text="When a classroom becomes unavailable, the Registrar's Office works with Facilities and Academic Operations to identify an alternative room with equivalent or greater capacity within 30 minutes. Students are notified via the SOLAR system and course LMS. The relocated class is held at the originally scheduled time unless a formal rescheduling request is approved.",
             chunks=["When a classroom becomes unavailable, the Registrar's Office works with Facilities and Academic Operations to identify an alternative room with equivalent or greater capacity within 30 minutes.",
                     "Students are notified via the SOLAR system and course LMS. The relocated class is held at the originally scheduled time unless a formal rescheduling request is approved."]),
        dict(id="vd-kd-02",
             title="Melville Library — Study Room Booking",
             publisher="SBU Libraries (Demo)",
             url="https://library.stonybrook.edu/study-rooms",
             text="Study rooms in Melville Library can be booked for up to 2 hours per day per group. Bookings open 7 days in advance via the library portal. Groups of 2–8 people. Rooms include a whiteboard and display screen. Cancellations must be made at least 1 hour before the booking.",
             chunks=["Study rooms in Melville Library can be booked for up to 2 hours per day per group.",
                     "Bookings open 7 days in advance via the library portal. Groups of 2–8 people.",
                     "Rooms include a whiteboard and display screen. Cancellations must be made at least 1 hour before the booking."]),
        dict(id="vd-kd-03",
             title="Campus Shuttle — Schedule and Routes",
             publisher="SBU Transportation (Demo)",
             url="https://transportation.example.invalid/shuttle",
             text="The campus shuttle runs Monday–Friday 7:00 AM–11:00 PM on four routes (Route 1–4). Route 3 connects the South Campus residence halls to the academic core buildings (LE, CS, JAV). Delays of more than 10 minutes are posted to the SBU mobile app. A real-time tracker is available at transportation.stonybrook.edu.",
             chunks=["The campus shuttle runs Monday–Friday 7:00 AM–11:00 PM on four routes.",
                     "Route 3 connects South Campus residence halls to academic core buildings (LE, CS, JAV).",
                     "Delays of more than 10 minutes are posted to the SBU mobile app."]),
        dict(id="vd-kd-04",
             title="Academic Integrity Policy",
             publisher="SBU Academic Integrity (Demo)",
             url="https://www.stonybrook.edu/academics/integrity",
             text="All submitted work must be the student's own. Use of AI tools to generate submitted text is subject to the same rules as other forms of unauthorised assistance. Violations may result in a failing grade for the assignment, course, or academic probation. Students uncertain about a specific use case should consult their instructor before submission.",
             chunks=["All submitted work must be the student's own.",
                     "Use of AI tools to generate submitted text is subject to the same rules as other forms of unauthorised assistance.",
                     "Violations may result in a failing grade. Students uncertain about a specific use case should consult their instructor."]),
    ]
    for d in docs:
        if db.get(KnowledgeDocument, d["id"]):
            continue
        doc = KnowledgeDocument(
            id=d["id"], title=d["title"], publisher=d["publisher"],
            canonical_url=d["url"],
            content_text="\n\n".join(d["chunks"]),
            last_verified_at_utc=datetime.now(timezone.utc),
            usage_note="Public information — curated allowlist",
            is_active=True,
        )
        db.add(doc)
        db.flush()
        for i, chunk_text in enumerate(d["chunks"]):
            chunk_id = f"{d['id']}-chunk-{i}"
            db.add(KnowledgeChunk(
                id=chunk_id, document_id=d["id"], chunk_index=i,
                text=chunk_text, search_text=chunk_text.lower(),
            ))
        db.flush()
        for i, chunk_text in enumerate(d["chunks"]):
            chunk_id = f"{d['id']}-chunk-{i}"
            try:
                db.execute(text(
                    "INSERT OR REPLACE INTO knowledge_chunks_fts(chunk_id, text) VALUES (:cid, :txt)"
                ), {"cid": chunk_id, "txt": chunk_text})
            except Exception:
                pass
    db.flush()


def _upsert_sensors(db) -> None:
    readings = [
        ("sensor-jav101-temp",   "temperature",      27.8, "°C"),
        ("sensor-jav101-air",    "air_quality",       65,  "AQI"),
        ("sensor-le201-temp",    "temperature",       21.2, "°C"),
        ("sensor-cs2311-temp",   "temperature",       20.5, "°C"),
        ("sensor-mel-temp",      "temperature",       20.1, "°C"),
        ("sensor-sac-occupancy", "occupancy_count",  312,  "people"),
        ("sensor-jav-occupancy", "occupancy_count",   95,  "people"),
        ("sensor-le-occupancy",  "occupancy_count",   62,  "people"),
    ]
    base = datetime.now(timezone.utc)
    for i, (label, metric, value, unit) in enumerate(readings):
        db.add(SensorReading(
            sensor_label=label, metric_type=metric, value=value, unit=unit,
            recorded_at_utc=base - timedelta(minutes=i * 3),
            data_origin="synthetic",
        ))
    db.flush()


# ─────────────────────────────────────────────────────────────────────────────
# TENANT DB  (Signals, Moves, CanonicalEvents, WorkItems, Notifications …)
# ─────────────────────────────────────────────────────────────────────────────
def _seed_tenant(db) -> None:
    _upsert_sim_state(db)
    _upsert_signals(db)
    _upsert_canonical_events(db)
    _upsert_work_items(db)
    _upsert_moves(db)
    _upsert_notifications(db)
    _upsert_service_requests(db)
    _upsert_threads(db)
    _upsert_course_updates(db)
    _upsert_scenario_runs(db)
    db.flush()


def _upsert_sim_state(db) -> None:
    existing = db.get(SimState, 1)
    if existing:
        return
    db.add(SimState(
        id=1, mode="scenario", scenario_id="disrupted_tuesday",
        anchor_date="2026-11-11",
        virtual_now=NOW,
        applied_signal_ids=json.dumps([f"vd-sig-{i:03d}" for i in range(1, 9)]),
        director_mode="off",
        active_persona=None,
        executed_step_ids="[]",
    ))
    db.flush()


def _upsert_signals(db) -> None:
    signals = [
        dict(id="vd-sig-001", feed="solar",          kind="schedule_snapshot",     at=_dt(7,30),  rel="relevant",
             summary="Class schedule loaded (3 meetings today)",
             payload={"commitments": ["c-cse214","c-mat203","c-cse316"]}),
        dict(id="vd-sig-002", feed="brightspace",    kind="deadlines_snapshot",    at=_dt(7,30),  rel="relevant",
             summary="Deadlines loaded (2 open tasks)",
             payload={"task_ids": ["vd-task-01","vd-task-04"]}),
        dict(id="vd-sig-003", feed="campus_events",  kind="saved_events_snapshot", at=_dt(7,31),  rel="relevant",
             summary="Saved events loaded (1): Fall Career Fair",
             payload={"event_ids": ["vd-ce-01"]}),
        dict(id="vd-sig-004", feed="brightspace",    kind="announcement",          at=_dt(8,5),   rel="relevant",
             summary="MAT 203: Quiz 4 on Thursday — Chapter 14",
             payload={"course":"MAT 203","title":"Quiz 4 on Thursday","body":"Quiz 4 is Thursday at 12:30 PM. Topics: Chapter 14, Sections 1-3."}),
        dict(id="vd-sig-005", feed="solar",          kind="room_change",           at=_dt(9,10),  rel="relevant",
             summary="CSE 214 moved from LE 201 → Javits 101",
             payload={"commitment":"c-cse214","from":"LE-201","to":"JAV-101","reason":"Projector replacement in LE 201"},
             canonical_event_id=CE_ROOM_CHANGE),
        dict(id="vd-sig-006", feed="shuttle",        kind="delay",                 at=_dt(9,40),  rel="filtered",
             summary="Shuttle Route 3 delayed 12 minutes",
             payload={"route":"Route 3","delay_minutes":12},
             relevance_reason="Student does not use shuttle today"),
        dict(id="vd-sig-007", feed="building_ops",   kind="incident",              at=_dt(10,5),  rel="relevant",
             summary="🌡  Cooling fault in Javits 101 — 27.8 °C and rising",
             payload={"incident_id":"inc-hvac-jav101","type":"hvac_fault","room":"JAV-101","temperature_c":27.8,"trend":"rising"},
             canonical_event_id=CE_HVAC),
        dict(id="vd-sig-008", feed="solar",          kind="room_change",           at=_dt(10,35), rel="relevant",
             summary="MAT 203 relocated: Javits 101 → Javits 102",
             payload={"commitment":"c-mat203","from":"JAV-101","to":"JAV-102","reason":"Cooling fault in Javits 101"},
             canonical_event_id=CE_HVAC),
        dict(id="vd-sig-009", feed="weather",        kind="forecast_change",       at=_dt(11,40), rel="relevant",
             summary="Rain expected 2:00–5:00 PM (85% probability)",
             payload={"condition":"rain","from":"14:00","to":"17:00","probability":0.85}),
        dict(id="vd-sig-010", feed="campus_events",  kind="event_rescheduled",     at=_dt(12,15), rel="relevant",
             summary="Fall Career Fair moved to TODAY 2:00–5:00 PM",
             payload={"event":"vd-ce-01","reason":"Moved up from Thursday","new_start":"14:00","new_end":"17:00"},
             canonical_event_id=CE_CAREER_FAIR),
        dict(id="vd-sig-011", feed="campus_events",  kind="event_announced",       at=_dt(13,20), rel="filtered",
             summary="Chess Club open night (7:00 PM)",
             payload={"title":"Chess Club open night","start":"19:00"},
             relevance_reason="Not saved by student; low relevance score"),
        dict(id="vd-sig-012", feed="library_rooms",  kind="availability",          at=_dt(16,10), rel="relevant",
             summary="Melville Study Room 3 free 4:30–6:30 PM",
             payload={"room":"MEL-SR3","slots":[["16:30","18:30"],["19:00","20:00"]]}),
    ]
    for s in signals:
        if db.get(Signal, s["id"]):
            continue
        db.add(Signal(
            id=s["id"], feed=s["feed"], kind=s["kind"],
            at_utc=s["at"], summary=s["summary"],
            payload=json.dumps(s["payload"]),
            relevance=s["rel"],
            relevance_reason=s.get("relevance_reason"),
            data_origin="synthetic",
            scenario_id="disrupted_tuesday",
            canonical_event_id=s.get("canonical_event_id"),
        ))
    db.flush()


def _upsert_canonical_events(db) -> None:
    events = [
        dict(id=CE_HVAC, type="incident.hvac_fault", status="triage",
             severity="high", idempotency_key="hvac-jav101-20261111-1005",
             source_feed="building_ops", occurred_at=_dt(10,5),
             entity_refs=[{"type":"room","id":"JAV-101"},{"type":"building","id":"JAV"}],
             payload={"room":"JAV-101","temperature_c":27.8,"trend":"rising"},
             classification="institutional",
             last_actor=FACILITIES_MORGAN, last_actor_mode="human",
             corroborations=2),
        dict(id=CE_ROOM_CHANGE, type="event.room_change", status="resolved",
             severity="medium", idempotency_key="roomchg-cse214-20261111-0910",
             source_feed="solar", occurred_at=_dt(9,10),
             entity_refs=[{"type":"section","id":"CSE-214-01"},{"type":"room","id":"LE-201"},{"type":"room","id":"JAV-101"}],
             payload={"section":"CSE-214-01","from_room":"LE-201","to_room":"JAV-101","reason":"Projector replacement"},
             classification="institutional",
             last_actor=ACADOPS_TAYLOR, last_actor_mode="human",
             corroborations=1),
        dict(id=CE_CAREER_FAIR, type="event.reschedule", status="reported",
             severity="low", idempotency_key="careerfair-reschedule-20261111",
             source_feed="campus_events", occurred_at=_dt(12,15),
             entity_refs=[{"type":"campus_event","id":"vd-ce-01"}],
             payload={"event_id":"vd-ce-01","new_date":"2026-11-11","new_start":"14:00","new_end":"17:00"},
             classification="public",
             last_actor=ORG_RILEY, last_actor_mode="human",
             corroborations=0),
        dict(id=CE_WIFI, type="incident.wifi_degraded", status="reported",
             severity="medium", idempotency_key="wifi-mel-20261111-1120",
             source_feed="it_monitor", occurred_at=_dt(11,20),
             entity_refs=[{"type":"building","id":"MEL"},{"type":"service","id":"svc-wifi"}],
             payload={"building":"MEL","affected_aps":["ap-MEL-2","ap-MEL-3"],"packet_loss_pct":18},
             classification="institutional",
             last_actor=IT_CASEY, last_actor_mode="human",
             corroborations=1),
    ]
    for e in events:
        existing = db.query(CanonicalEvent).filter_by(idempotency_key=e["idempotency_key"]).first()
        if existing:
            continue
        db.add(CanonicalEvent(
            id=e["id"], tenant_id=TENANT, type=e["type"], status=e["status"],
            severity=e["severity"], idempotency_key=e["idempotency_key"],
            source_feed=e["source_feed"], occurred_at=e["occurred_at"],
            received_at=e["occurred_at"] + timedelta(seconds=30),
            entity_refs_json=json.dumps(e["entity_refs"]),
            payload_json=json.dumps(e["payload"]),
            classification=e["classification"],
            data_origin="synthetic", schema_version="event-envelope/1",
            corroborations=e["corroborations"],
            last_actor=e["last_actor"], last_actor_mode=e["last_actor_mode"],
        ))
    db.flush()


def _upsert_work_items(db) -> None:
    items = [
        dict(id="vd-wi-01", canonical_event_id=CE_HVAC,
             workflow_type="incident_response", status="triage",
             owner=FACILITIES_MORGAN, team=TEAM_FAC_1, version=3,
             payload={"room":"JAV-101","temperature_c":27.8,"affected_sections":["CSE-214-01","MAT-203-01"],"students_affected":168},
             required_next=["resolution_steps","estimated_restore_time"]),
        dict(id="vd-wi-02", canonical_event_id=CE_HVAC,
             workflow_type="room_reassignment", status="impact_assessed",
             owner=ACADOPS_TAYLOR, team=TEAM_ACADOPS, version=2,
             payload={"original_room":"JAV-101","replacement_room":"JAV-102","sections_moved":["MAT-203-01"]},
             required_next=["notify_instructor","confirm_room_unlock"]),
        dict(id="vd-wi-03", canonical_event_id=CE_WIFI,
             workflow_type="service_disruption", status="triage",
             owner=IT_CASEY, team=TEAM_IT_2, version=1,
             payload={"service":"svc-wifi","building":"MEL","affected_aps":["ap-MEL-2","ap-MEL-3"],"packet_loss_pct":18},
             required_next=["root_cause","estimated_restore_time"]),
        dict(id="vd-wi-04", canonical_event_id=CE_ROOM_CHANGE,
             workflow_type="course_update", status="resolved",
             owner=FAC_JORDAN, team=TEAM_ACADOPS, version=4,
             payload={"section":"CSE-214-01","room_change":"LE-201 → JAV-101","notification_sent":True},
             required_next=[]),
    ]
    for i in items:
        if db.get(WorkItem, i["id"]):
            continue
        db.add(WorkItem(
            id=i["id"], tenant_id=TENANT,
            canonical_event_id=i["canonical_event_id"],
            workflow_type=i["workflow_type"], status=i["status"],
            version=i["version"],
            owner_person_id=i["owner"], assigned_team_id=i["team"],
            payload_json=json.dumps(i["payload"]),
            required_next_fields_json=json.dumps(i["required_next"]),
        ))
    db.flush()
    # Transitions for vd-wi-01
    trans = [
        dict(id="vd-wt-01a", wi="vd-wi-01", frm="reported", to="triage",
             actor=FACILITIES_MORGAN, role="facilities", mode="human",
             rationale="HVAC fault confirmed on sensor. Dispatching technician.",
             at=_dt(10,8)),
        dict(id="vd-wt-01b", wi="vd-wi-01", frm="triage", to="impact_assessed",
             actor=FACILITIES_MORGAN, role="facilities", mode="human",
             rationale="Estimated 2-hour repair window. Cooling not restorable before 12:30.",
             at=_dt(10,25)),
        dict(id="vd-wt-02a", wi="vd-wi-02", frm="reported", to="triage",
             actor=ACADOPS_TAYLOR, role="academic_ops", mode="human",
             rationale="Room JAV-102 confirmed available for MAT 203 at 12:30.",
             at=_dt(10,30)),
        dict(id="vd-wt-02b", wi="vd-wi-02", frm="triage", to="impact_assessed",
             actor=ACADOPS_TAYLOR, role="academic_ops", mode="human",
             rationale="SOLAR updated. Faculty notified. Students notified via LMS.",
             at=_dt(10,38)),
        dict(id="vd-wt-04a", wi="vd-wi-04", frm="reported", to="resolved",
             actor=FAC_JORDAN, role="faculty", mode="human",
             rationale="Room change announcement posted. Students confirmed via LMS.",
             at=_dt(9,15)),
    ]
    for t in trans:
        if db.get(WorkItemTransition, t["id"]):
            continue
        db.add(WorkItemTransition(
            id=t["id"], work_item_id=t["wi"], from_status=t["frm"], to_status=t["to"],
            actor_id=t["actor"], actor_role=t["role"], actor_mode=t["mode"],
            rationale=t["rationale"], effects_json="{}",
            virtual_time=t["at"],
        ))
    db.flush()


def _w(*texts: str, feed: str = "detector") -> list[dict]:
    """Build WhyItem-compatible dicts from plain text strings."""
    return [{"feed": feed, "text": t} for t in texts]


def _a(action_id: str, atype: str, **params) -> dict:
    """Build ActionSpec-compatible dict."""
    return {"id": action_id, "type": atype, "params": params, "external": False, "simulated": False}


def _a_sim(action_id: str, atype: str, **params) -> dict:
    """Build simulated ActionSpec-compatible dict."""
    return {"id": action_id, "type": atype, "params": params, "external": False, "simulated": True}


def _upsert_moves(db) -> None:
    import hashlib
    moves = [
        # ── Student moves ──────────────────────────────────────────────────
        dict(id="vd-mv-01", key="deadline:vd-task-01", kind="deadline_alert",
             audience="student", status="proposed", policy="auto", urgency="urgent",
             impact="high", title="⚠️  Assignment due TONIGHT — CSE 213 PA3",
             summary="CSE 213 Programming Assignment 3 is due tonight at 11:59 PM. You have 120 min estimated work remaining.",
             why=_w("Due date: tonight 11:59 PM", "Status: in_progress", "Estimated: 120 min remaining"),
             actions=[_a("mv01-a1","open_task", task_id="vd-task-01"),
                      _a("mv01-a2","add_study_block", minutes=120)],
             canonical_event_id=None),
        dict(id="vd-mv-02", key="ingest:vd-sig-004", kind="task_created",
             audience="student", status="executed_simulated", policy="auto", urgency="today",
             impact="medium", title="Quiz prep task created — MAT 203 Quiz 4",
             summary="New task created: 'Prepare for MAT 203 Quiz 4' (90 min, due Thursday 12:30 PM) based on Brightspace announcement.",
             why=_w("Announcement: Quiz 4 on Thursday", "Course: MAT 203", "Estimated: 90 min",
                    feed="brightspace"),
             actions=[_a_sim("mv02-a1","view_task", task_id="vd-task-03")],
             canonical_event_id=None),
        dict(id="vd-mv-03", key="change:cse214:vd-sig-005", kind="calendar_update",
             audience="student", status="executed_simulated", policy="auto", urgency="now",
             impact="medium", title="CSE 214 room updated → Javits 101",
             summary="Your calendar has been updated. CSE 214 is now in Javits 101 (was LE 201). Leave library by 9:51 AM (6 min walk + 3 min buffer).",
             why=_w("Room change signal from SOLAR", "Walking time MEL→JAV: 6 min", "Buffer: 3 min",
                    feed="solar"),
             actions=[_a_sim("mv03-a1","update_calendar", commitment="c-cse214", new_room="JAV-101"),
                      _a_sim("mv03-a2","set_reminder", at="09:51", text="Leave for Javits 101 — CSE 214")],
             canonical_event_id=CE_ROOM_CHANGE),
        dict(id="vd-mv-04", key="disruption:inc-hvac-jav101:student", kind="disruption_info",
             audience="student", status="proposed", policy="info", urgency="now",
             impact="low", title="ℹ️  Javits 101 is hot — MAT 203 may move",
             summary="Cooling fault in JAV 101 (27.8 °C, rising). Your MAT 203 class at 12:30 uses this room — an update is expected.",
             why=_w("HVAC fault signal from building_ops", "Your MAT 203 is scheduled in JAV-101",
                    "Facilities team notified", feed="building_ops"),
             actions=[_a("mv04-a1","watch_for_update", canonical_event_id=CE_HVAC)],
             canonical_event_id=CE_HVAC),
        dict(id="vd-mv-05", key="change:mat203:vd-sig-008", kind="calendar_update",
             audience="student", status="executed_simulated", policy="auto", urgency="now",
             impact="medium", title="MAT 203 room updated → Javits 102",
             summary="MAT 203 has been moved to Javits 102 (same building). No extra walking needed. Your calendar is updated.",
             why=_w("Room change signal from SOLAR", "Same building — no route change",
                    "Caused by: HVAC fault in JAV-101", feed="solar"),
             actions=[_a_sim("mv05-a1","update_calendar", commitment="c-mat203", new_room="JAV-102")],
             canonical_event_id=CE_HVAC),
        dict(id="vd-mv-06", key="disruption:weather:rain-1400", kind="weather_alert",
             audience="student", status="executed_simulated", policy="auto", urgency="today",
             impact="low", title="🌧  Rain 2:00–5:00 PM — bring an umbrella",
             summary="85% chance of rain from 2:00 to 5:00 PM. Your walk to CSE 316 (JAV→CS, 5 min, outdoors) is during this window.",
             why=_w("Weather feed: rain 14:00-17:00, 85%", "CSE 316 walk: JAV→CS, 5 min outdoors",
                    "Career Fair also during rain window", feed="weather"),
             actions=[_a_sim("mv06-a1","set_reminder", at="13:50",
                             text="Grab your umbrella — rain expected from 2 PM")],
             canonical_event_id=None),
        dict(id="vd-mv-07", key="conflict:vd-ce-01:c-cse316", kind="schedule_conflict",
             audience="student", status="proposed", policy="ask", urgency="today",
             impact="medium", title="Career Fair vs CSE 316 — you can do both",
             summary="Career Fair moved to today 2:00–5:00 PM. Your CSE 316 is at 3:00 PM. You can attend the fair 2:00–2:45 PM (must leave by 2:49). On approval: a visit block and leave-by reminder will be added.",
             why=_w("Career Fair: 14:00-17:00 today", "CSE 316: 15:00-16:20 in CS-2311",
                    "Walking JAV→CS: 5 min", "Earliest arrival: 13:58 after MAT 203",
                    feed="campus_events"),
             actions=[_a_sim("mv07-a1","add_calendar_block",
                             title="Career Fair visit", start="14:00", end="14:45"),
                      _a_sim("mv07-a2","set_reminder", at="14:49",
                             text="Leave Career Fair → CSE 316")],
             canonical_event_id=CE_CAREER_FAIR),
        dict(id="vd-mv-08", key="group:vd-task-04:slot", kind="group_meeting",
             audience="student", status="proposed", policy="ask", urgency="today",
             impact="medium", title="Team meeting slot found — CSE 316 report",
             summary="All four CSE 316 teammates are free 5:15–6:15 PM. Melville Study Room 3 is available (4:30–6:30 PM slot). On approval: room booking (SIMULATED), draft invites created.",
             why=_w("CSE 316 group report due in 3 days",
                    "Teammates Priya/Marcus/Dana all free at 17:15",
                    "MEL Study Room 3 available 16:30-18:30", feed="library_rooms"),
             actions=[_a_sim("mv08-a1","book_room_simulated",
                             room="MEL-SR3", start="17:15", end="18:15"),
                      _a_sim("mv08-a2","draft_invites", to=["Priya","Marcus","Dana"]),
                      _a_sim("mv08-a3","add_calendar_block",
                             title="CSE 316 Team Meeting", start="17:15", end="18:15")],
             canonical_event_id=None),
        # ── Staff moves ────────────────────────────────────────────────────
        dict(id="vd-mv-09", key="ops:inc-hvac-jav101", kind="ops_incident",
             audience="staff", status="proposed", policy="ask", urgency="now",
             impact="high", title="🔧  HVAC fault — Javits 101 needs immediate action",
             summary="Cooling fault in JAV-101 at 10:05 AM (27.8 °C, rising). Impact: 2 sections, 168 students (78 now in CSE 214, 90 in MAT 203 at 12:30). Only viable swap: move MAT 203 to JAV-102 (capacity 120, available). LE-201 projector out, CS-2311 too small (60 cap).",
             why=_w("HVAC fault at 10:05 AM — 27.8°C and rising",
                    "CSE-214 (78 students): in room RIGHT NOW",
                    "MAT-203 (90 students): 12:30 PM in same room",
                    "JAV-102: capacity 120, free at 12:30",
                    "LE-201: unavailable (projector fault)",
                    "CS-2311: capacity 60 — too small for 90 students",
                    feed="building_ops"),
             actions=[_a("mv09-a1","reassign_room",
                         section="MAT-203-01", from_room="JAV-101", to_room="JAV-102"),
                      _a("mv09-a2","notify_instructor", person_id=FAC_SAM),
                      _a("mv09-a3","notify_students", section="MAT-203-01"),
                      _a("mv09-a4","file_service_request", service_id="svc-hvac")],
             canonical_event_id=CE_HVAC),
        dict(id="vd-mv-10", key="ops:wifi-mel", kind="ops_incident",
             audience="staff", status="proposed", policy="ask", urgency="today",
             impact="medium", title="📶  Wi-Fi degraded — Melville Library floors 2–3",
             summary="Access points MEL-2 and MEL-3 reporting 18% packet loss since 11:20 AM. ~85 active sessions affected. Recommend restart and monitoring.",
             why=_w("AP health alert: ap-MEL-2 and ap-MEL-3",
                    "Packet loss: 18% (threshold: 5%)",
                    "Active sessions: ~85",
                    "Library peak hours: 10 AM–6 PM",
                    feed="it_monitor"),
             actions=[_a("mv10-a1","restart_ap", ap_id="ap-MEL-2"),
                      _a("mv10-a2","restart_ap", ap_id="ap-MEL-3"),
                      _a("mv10-a3","create_service_request", service_id="svc-wifi")],
             canonical_event_id=CE_WIFI),
    ]
    for m in moves:
        if db.get(Move, m["id"]):
            continue
        fp = hashlib.sha1(f"{m['title']}{m['summary']}".encode()).hexdigest()[:10]
        db.add(Move(
            id=m["id"], key=m["key"], kind=m["kind"],
            audience=m["audience"], status=m["status"],
            policy=m["policy"], urgency=m["urgency"], impact=m["impact"],
            title=m["title"], summary=m["summary"],
            why=json.dumps(m["why"]),
            actions=json.dumps(m["actions"]),
            fingerprint=fp,
            scenario_id="disrupted_tuesday",
            canonical_event_id=m.get("canonical_event_id"),
            created_at=NOW, updated_at=NOW,
        ))
    db.flush()


def _upsert_notifications(db) -> None:
    notifs = [
        dict(id="vd-notif-01", recipient=STUDENT_ALEX, kind="room_change",
             title="CSE 214 has moved to Javits 101",
             body="Your 10:00 AM CSE 214 class is now in Javits 101 (was LE 201). Leave by 9:51 AM from Melville Library.",
             why=[{"rel":"affects_section","entity_type":"section","entity_id":"CSE-214-01","text":"CSE 214 is enrolled"}],
             state="unread", canonical_event_id=CE_ROOM_CHANGE, ik="notif-roomchg-alex-cse214"),
        dict(id="vd-notif-02", recipient=STUDENT_ALEX, kind="room_change",
             title="MAT 203 relocated to Javits 102",
             body="Your 12:30 PM MAT 203 class has been moved to Javits 102 (same building). No extra travel needed.",
             why=[{"rel":"affects_section","entity_type":"section","entity_id":"MAT-203-01","text":"MAT 203 is enrolled"}],
             state="unread", canonical_event_id=CE_HVAC, ik="notif-roomchg-alex-mat203"),
        dict(id="vd-notif-03", recipient=FAC_SAM, kind="course_update",
             title="Action needed: MAT 203 room change approved",
             body="MAT 203 (12:30 PM) has been relocated to Javits 102 due to the HVAC fault in Javits 101. Please confirm with your students.",
             why=[{"rel":"instructor_of","entity_type":"section","entity_id":"MAT-203-01","text":"Instructor of MAT 203"}],
             state="unread", requires_ack=True, canonical_event_id=CE_HVAC, ik="notif-roomchg-fac-sam-mat203"),
        dict(id="vd-notif-04", recipient=FACILITIES_MORGAN, kind="incident_status",
             title="HVAC fault in Javits 101 — work order created",
             body="Service request SR-2026-0847 filed. Technician dispatch ETA: 11:00 AM. Estimated restore: 1:00 PM.",
             why=[{"rel":"assigned_to","entity_type":"team","entity_id":TEAM_FAC_1,"text":"Facilities team for Javits"}],
             state="read", canonical_event_id=CE_HVAC, ik="notif-hvac-facilities-morgan"),
        dict(id="vd-notif-05", recipient=IT_CASEY, kind="incident_status",
             title="Wi-Fi degraded — Melville floors 2–3",
             body="APs ap-MEL-2 and ap-MEL-3 showing 18% packet loss. Recommend restart. Ticket created.",
             why=[{"rel":"owns_service","entity_type":"service","entity_id":"svc-wifi","text":"IT owns campus Wi-Fi"}],
             state="unread", canonical_event_id=CE_WIFI, ik="notif-wifi-it-casey"),
        dict(id="vd-notif-06", recipient=ACADOPS_TAYLOR, kind="course_update",
             title="Room reassignment complete — MAT 203 → JAV-102",
             body="SOLAR has been updated. Faculty and students notified. Work item closed.",
             why=[{"rel":"managed_by","entity_type":"team","entity_id":TEAM_ACADOPS,"text":"Academic Ops managed this reassignment"}],
             state="read", canonical_event_id=CE_HVAC, ik="notif-roomchg-acadops-taylor"),
    ]
    for n in notifs:
        if db.get(Notification, n["id"]):
            continue
        db.add(Notification(
            id=n["id"], recipient_person_id=n["recipient"], kind=n["kind"],
            title=n["title"], body=n["body"],
            why_json=json.dumps(n["why"]),
            state=n["state"], requires_ack=n.get("requires_ack", False),
            data_origin="synthetic",
            canonical_event_id=n.get("canonical_event_id"),
            work_item_id=None,
            idempotency_key=n["ik"],
            created_at=NOW,
        ))
    db.flush()


def _upsert_service_requests(db) -> None:
    srs = [
        dict(id="vd-sr-01", requester=FACILITIES_MORGAN, service="svc-hvac",
             title="HVAC failure — Javits 101 cooling unit unresponsive",
             body="Cooling unit in JAV-101 has stopped responding. Temperature reading 27.8 °C at 10:05 AM and rising. Two classes scheduled in this room today (CSE 214 at 10 AM, MAT 203 at 12:30 PM). Urgent repair needed.",
             status="in_progress", team=TEAM_FAC_1, version=2,
             canonical_event_id=CE_HVAC),
        dict(id="vd-sr-02", requester=IT_CASEY, service="svc-wifi",
             title="Wi-Fi degraded — Melville Library floors 2–3",
             body="Access points ap-MEL-2 and ap-MEL-3 reporting 18% packet loss since 11:20 AM. ~85 student sessions affected. AP restart attempted at 11:35 AM — issue persists.",
             status="triaged", team=TEAM_IT_2, version=1,
             canonical_event_id=CE_WIFI),
        dict(id="vd-sr-03", requester=STUDENT_ALEX, service="svc-lms",
             title="Unable to access CSE 213 Assignment 3 submission portal",
             body="Clicking the submission link in Brightspace shows an error: 'Assignment not found'. I can see the assignment description but cannot submit. Using Chrome 130 on macOS.",
             status="submitted", team=TEAM_IT_2, version=1,
             canonical_event_id=None),
    ]
    for s in srs:
        if db.get(ServiceRequest, s["id"]):
            continue
        db.add(ServiceRequest(
            id=s["id"], tenant_id=TENANT,
            requester_person_id=s["requester"],
            service_id=s["service"], title=s["title"], body=s["body"],
            status=s["status"], assigned_team_id=s["team"],
            version=s["version"], data_origin="synthetic",
            canonical_event_id=s.get("canonical_event_id"),
        ))
    db.flush()


def _upsert_threads(db) -> None:
    threads = [
        dict(id="vd-thr-01", canonical_event_id=CE_HVAC, wi_id="vd-wi-01",
             title="HVAC Fault — Javits 101 response thread",
             messages=[
                 (FACILITIES_MORGAN, "Fault confirmed on BMS. Dispatch requested. ETA 11 AM."),
                 (ACADOPS_TAYLOR,    "JAV-102 is free at 12:30. I'll update SOLAR now."),
                 (FAC_SAM,           "Confirmed. I'll post a note to students in the LMS."),
                 (FACILITIES_MORGAN, "Technician on site. Compressor fault — part ordered. Restore ETA 1 PM."),
             ]),
        dict(id="vd-thr-02", canonical_event_id=CE_WIFI, wi_id="vd-wi-03",
             title="Wi-Fi degraded — Melville floors 2–3",
             messages=[
                 (IT_CASEY,          "APs restarted at 11:35 AM. Issue persists — escalating to network team."),
                 (IT_CASEY,          "Network team reviewing switch port configuration. ETA 30 min."),
             ]),
    ]
    for t in threads:
        if db.get(Thread, t["id"]):
            continue
        thread = Thread(
            id=t["id"], canonical_event_id=t["canonical_event_id"],
            work_item_id=t["wi_id"], title=t["title"],
        )
        db.add(thread)
        db.flush()
        for i, (author, body) in enumerate(t["messages"]):
            db.add(ThreadMessage(
                id=f"{t['id']}-msg-{i:02d}",
                thread_id=t["id"], author_person_id=author,
                body=body, data_origin="synthetic",
                created_at=NOW + timedelta(minutes=i*5),
            ))
    db.flush()


def _upsert_course_updates(db) -> None:
    updates = [
        dict(id="vd-cu-01", section="CSE-214-01", author=FAC_JORDAN,
             text="Due to a room change, today's CSE 214 lecture (10:00 AM) will be held in Javits 101 instead of LE 201. Please arrive a few minutes early as the room is larger. All course materials remain unchanged.",
             status="published",
             extracted={"title":"Room change: CSE 214 → Javits 101","due_date":None,"est_minutes":0,"confidence":0.97,"quote":"Javits 101 instead of LE 201"},
             canonical_event_id=CE_ROOM_CHANGE),
        dict(id="vd-cu-02", section="MAT-203-01", author=FAC_SAM,
             text="Update: MAT 203 (12:30 PM today) has been moved to Javits 102 due to a building issue in Javits 101. Same building, different room. Please check your calendar.",
             status="published",
             extracted={"title":"Room change: MAT 203 → Javits 102","due_date":None,"est_minutes":0,"confidence":0.98,"quote":"moved to Javits 102"},
             canonical_event_id=CE_HVAC),
        dict(id="vd-cu-03", section="CSE-213-01", author=FAC_JORDAN,
             text="Reminder: Programming Assignment 3 is due TONIGHT at 11:59 PM. Please submit through Brightspace. If you encounter submission issues, contact the IT Service Desk immediately.",
             status="previewed",
             extracted={"title":"Assignment 3 due tonight","due_date":"2026-11-11","due_time":"23:59","est_minutes":0,"confidence":0.99,"quote":"due TONIGHT at 11:59 PM"},
             canonical_event_id=None),
    ]
    for u in updates:
        if db.get(CourseUpdate, u["id"]):
            continue
        db.add(CourseUpdate(
            id=u["id"], section_id=u["section"], author_person_id=u["author"],
            text=u["text"], status=u["status"],
            extracted_json=json.dumps(u["extracted"]),
            canonical_event_id=u.get("canonical_event_id"),
            tenant_id=TENANT,
        ))
    db.flush()


def _upsert_scenario_runs(db) -> None:
    if db.get(ScenarioRun, "vd-scenario-run-01"):
        return
    inputs = {
        "scenario_type": "classroom_outage",
        "room_id": "JAV-101",
        "fault_type": "hvac_fault",
        "temperature_c": 27.8,
        "affected_sections": ["CSE-214-01","MAT-203-01"],
        "anchor_time": "10:05"
    }
    result = {
        "options": [
            {"id": "opt-jav102", "label": "Move MAT 203 → Javits 102",
             "score": 0.94, "feasible": True,
             "impacts": {"capacity_ok":True,"walking_minutes":0,"notification_lag_min":5}},
            {"id": "opt-cs2311", "label": "Move MAT 203 → CS 2311",
             "score": 0.41, "feasible": False,
             "impacts": {"capacity_ok":False,"capacity":60,"required":90}},
            {"id": "opt-reschedule", "label": "Reschedule MAT 203",
             "score": 0.18, "feasible": True,
             "impacts": {"capacity_ok":True,"walking_minutes":0,"student_disruption":"high"}},
        ],
        "recommended_option_id": "opt-jav102",
        "confidence": 0.94,
        "reasoning": "JAV-102 has sufficient capacity (120 ≥ 90), is in the same building (no travel change), and is free at 12:30 PM. LE-201 is unavailable (projector fault). CS-2311 is too small."
    }
    db.add(ScenarioRun(
        id="vd-scenario-run-01", tenant_id=TENANT,
        canonical_event_id=CE_HVAC,
        engine_version="v1", scenario_type="classroom_outage",
        inputs_json=json.dumps(inputs),
        result_json=json.dumps(result),
        result_hash="abc123demo",
        status="promoted",
        promoted_by=ACADOPS_TAYLOR,
        promoted_at=_dt(10, 38),
        promoted_option_id="opt-jav102",
        promotion_rationale="JAV-102 confirmed available; SOLAR update issued.",
        data_origin="synthetic_simulation",
        created_by=ACADOPS_TAYLOR,
        created_at=_dt(10,28), updated_at=_dt(10,38),
    ))
    db.flush()


# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    seed_all()
