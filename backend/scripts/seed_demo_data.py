"""Seed demo data into the AURORA SQLite database.

Usage (from backend/ directory with venv active):
    python -m scripts.seed_demo_data
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Allow running as a module from the backend/ directory
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db.session import SessionLocal, init_db
from app.models.models import (
    UserProfile,
    UserPreference,
    ConsentGrant,
    Task,
    Announcement,
    CampusEvent,
    KnowledgeDocument,
    KnowledgeChunk,
    SensorReading,
)
from app.core.config import settings

SAMPLE_DATA = Path(__file__).parent.parent.parent / "sample-data"


def seed(db=None, user_id: str | None = None) -> None:
    """Insert demo fixtures. Idempotent — skips records that already exist."""
    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True
    if user_id is None:
        user_id = settings.demo_user_id

    try:
        _seed_user(db, user_id)
        _seed_tasks(db, user_id)
        _seed_announcements(db, user_id)
        _seed_campus_events(db)
        _seed_knowledge(db)
        _seed_sensors(db)
        db.commit()
        print(f"✓ Demo data seeded for user {user_id}")
    finally:
        if close_db:
            db.close()


def _seed_user(db, user_id: str) -> None:
    existing = db.get(UserProfile, user_id)
    if existing:
        return
    user = UserProfile(
        id=user_id,
        display_name="Alex (Demo Student)",
        timezone="America/New_York",
    )
    db.add(user)
    db.flush()
    pref = UserPreference(
        user_id=user_id,
        day_start_time="08:00",
        day_end_time="22:00",
        preferred_focus_block_minutes=50,
        short_break_minutes=10,
        long_break_minutes=30,
        default_travel_buffer_minutes=10,
    )
    db.add(pref)
    # Consent records
    for source_type, purpose in [
        ("ics_import", "Display your imported calendar events in the planner."),
        ("brightspace_demo", "Show demo announcements (synthetic data only)."),
        ("campus_knowledge", "Answer campus questions from the public knowledge base."),
    ]:
        db.add(
            ConsentGrant(
                user_id=user_id,
                source_type=source_type,
                purpose=purpose,
                granted=True,
                granted_at=datetime.now(timezone.utc),
            )
        )
    db.flush()


def _seed_tasks(db, user_id: str) -> None:
    data = json.loads((SAMPLE_DATA / "tasks_demo.json").read_text())
    for item in data:
        if db.get(Task, item["id"]):
            continue
        due = datetime.fromisoformat(item["due_at_utc"]) if item.get("due_at_utc") else None
        task = Task(
            id=item["id"],
            user_id=user_id,
            title=item["title"],
            description=item.get("description"),
            course_label=item.get("course_label"),
            due_at_utc=due,
            estimated_minutes=item.get("estimated_minutes", 30),
            priority=item.get("priority", "normal"),
            status=item.get("status", "todo"),
            source_type=item.get("source_type", "demo"),
            source_url=item.get("source_url"),
        )
        db.add(task)
    db.flush()


def _seed_announcements(db, user_id: str) -> None:
    data = json.loads((SAMPLE_DATA / "brightspace_demo.json").read_text())
    for item in data.get("announcements", []):
        if db.get(Announcement, item["id"]):
            continue
        pub = datetime.fromisoformat(item["published_at_utc"]) if item.get("published_at_utc") else None
        ann = Announcement(
            id=item["id"],
            user_id=user_id,
            course_label=item["course_label"],
            title=item["title"],
            body_summary=item["body_summary"],
            published_at_utc=pub,
            source_url=item.get("source_url"),
            source_type=item.get("source_type", "demo"),
            is_read=False,
            read_at_utc=None,
        )
        db.add(ann)
    db.flush()


def _seed_campus_events(db) -> None:
    data = json.loads((SAMPLE_DATA / "campus_events_demo.json").read_text())
    for item in data.get("events", []):
        if db.get(CampusEvent, item["id"]):
            continue
        start = datetime.fromisoformat(item["start_at_utc"]) if item.get("start_at_utc") else None
        end = datetime.fromisoformat(item["end_at_utc"]) if item.get("end_at_utc") else None
        evt = CampusEvent(
            id=item["id"],
            title=item["title"],
            description=item.get("description"),
            start_at_utc=start,
            end_at_utc=end,
            location_text=item.get("location_text"),
            source_title=item["source_title"],
            source_url=item["source_url"],
            is_demo_data=item.get("is_demo_data", True),
        )
        db.add(evt)
    db.flush()


def _seed_knowledge(db) -> None:
    data = json.loads((SAMPLE_DATA / "campus_knowledge_demo.json").read_text())
    for doc_data in data.get("documents", []):
        existing = db.get(KnowledgeDocument, doc_data["id"])
        if existing:
            continue
        doc = KnowledgeDocument(
            id=doc_data["id"],
            title=doc_data["title"],
            publisher=doc_data["publisher"],
            canonical_url=doc_data["canonical_url"],
            content_text="\n\n".join(c["text"] for c in doc_data.get("chunks", [])),
            last_verified_at_utc=datetime.fromisoformat(doc_data["last_verified_at_utc"]),
            usage_note=doc_data.get("usage_note", ""),
            is_active=True,
        )
        db.add(doc)
        db.flush()

        for chunk_data in doc_data.get("chunks", []):
            chunk_id = f"{doc_data['id']}-chunk-{chunk_data['index']}"
            text = chunk_data["text"]
            chunk = KnowledgeChunk(
                id=chunk_id,
                document_id=doc.id,
                chunk_index=chunk_data["index"],
                text=text,
                search_text=text.lower(),
            )
            db.add(chunk)
        db.flush()

        # Index into FTS5 using same session to avoid SQLite write-lock
        from sqlalchemy import text as sql_text
        for chunk_data in doc_data.get("chunks", []):
            chunk_id = f"{doc_data['id']}-chunk-{chunk_data['index']}"
            chunk_text = chunk_data["text"]
            try:
                db.execute(
                    sql_text(
                        "INSERT OR REPLACE INTO knowledge_chunks_fts(chunk_id, text) VALUES (:cid, :txt)"
                    ),
                    {"cid": chunk_id, "txt": chunk_text},
                )
            except Exception:
                pass


def _seed_sensors(db) -> None:
    from datetime import timedelta
    data = json.loads((SAMPLE_DATA / "sensor_readings_demo.json").read_text())
    now = datetime.now(timezone.utc)
    for i, item in enumerate(data.get("readings", [])):
        reading = SensorReading(
            sensor_label=item["sensor_label"],
            metric_type=item["metric_type"],
            value=item["value"],
            unit=item["unit"],
            recorded_at_utc=now - timedelta(minutes=i * 5),
            data_origin="synthetic",
        )
        db.add(reading)
    db.flush()


if __name__ == "__main__":
    init_db()
    seed()
