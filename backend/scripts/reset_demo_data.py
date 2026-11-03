"""Reset all demo data and re-seed from fixtures.

Usage (from backend/ directory with venv active):
    python -m scripts.reset_demo_data
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db.session import SessionLocal, init_db
from app.models.models import (
    Task, Announcement, CampusEvent, DailyPlan, PlanBlock,
    SensorReading, KnowledgeChunk, KnowledgeDocument,
)
from app.core.config import settings
from scripts.seed_demo_data import seed


def reset() -> None:
    init_db()
    db = SessionLocal()
    user_id = settings.demo_user_id
    try:
        # Remove plan blocks first (FK)
        db.query(PlanBlock).filter(
            PlanBlock.daily_plan_id.in_(
                db.query(DailyPlan.id).filter(DailyPlan.user_id == user_id)
            )
        ).delete(synchronize_session=False)
        db.query(DailyPlan).filter(DailyPlan.user_id == user_id).delete()
        db.query(Announcement).filter(Announcement.user_id == user_id).delete()
        db.query(Task).filter(Task.user_id == user_id, Task.source_type == "demo").delete()
        db.query(CampusEvent).delete()
        db.query(SensorReading).delete()
        db.commit()
        seed(db, user_id)
        print("✓ Demo data reset complete.")
    finally:
        db.close()


if __name__ == "__main__":
    reset()
