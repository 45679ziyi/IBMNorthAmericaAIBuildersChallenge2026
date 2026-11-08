"""
Thin alias to import the campus engine's evaluate function without
creating circular import issues in the API layer.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session


def run_evaluate(db: Session, now: datetime) -> list:
    """Run the campus intelligence engine evaluate() function."""
    from app.services.campus.engine import evaluate
    return evaluate(db, now)
