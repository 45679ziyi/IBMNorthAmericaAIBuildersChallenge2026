"""SQLAlchemy ORM models for AURORA."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    from datetime import timezone
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class UserProfile(Base):
    __tablename__ = "user_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    display_name: Mapped[str | None] = mapped_column(String(128))
    timezone: Mapped[str] = mapped_column(String(64), default="America/New_York")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    preferences: Mapped[list[UserPreference]] = relationship(back_populates="user", cascade="all, delete-orphan")
    calendar_events: Mapped[list[CalendarEvent]] = relationship(back_populates="user", cascade="all, delete-orphan")
    tasks: Mapped[list[Task]] = relationship(back_populates="user", cascade="all, delete-orphan")
    announcements: Mapped[list[Announcement]] = relationship(back_populates="user", cascade="all, delete-orphan")
    consent_grants: Mapped[list[ConsentGrant]] = relationship(back_populates="user", cascade="all, delete-orphan")
    daily_plans: Mapped[list[DailyPlan]] = relationship(back_populates="user", cascade="all, delete-orphan")


class UserPreference(Base):
    __tablename__ = "user_preferences"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("user_profiles.id"), nullable=False)
    day_start_time: Mapped[str] = mapped_column(String(8), default="08:00")
    day_end_time: Mapped[str] = mapped_column(String(8), default="22:00")
    preferred_focus_block_minutes: Mapped[int] = mapped_column(Integer, default=50)
    short_break_minutes: Mapped[int] = mapped_column(Integer, default=10)
    long_break_minutes: Mapped[int] = mapped_column(Integer, default=30)
    default_travel_buffer_minutes: Mapped[int] = mapped_column(Integer, default=10)
    preferred_study_periods: Mapped[str] = mapped_column(Text, default='["morning","afternoon"]')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    user: Mapped[UserProfile] = relationship(back_populates="preferences")


class ConsentGrant(Base):
    __tablename__ = "consent_grants"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("user_profiles.id"), nullable=False)
    source_type: Mapped[str] = mapped_column(String(64))
    purpose: Mapped[str] = mapped_column(String(256))
    granted: Mapped[bool] = mapped_column(Boolean, default=False)
    granted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[UserProfile] = relationship(back_populates="consent_grants")


class CalendarEvent(Base):
    __tablename__ = "calendar_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("user_profiles.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(256))
    description: Mapped[str | None] = mapped_column(Text)
    start_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    location_text: Mapped[str | None] = mapped_column(String(256))
    event_type: Mapped[str] = mapped_column(
        Enum("class", "meeting", "personal", "other", name="event_type_enum"), default="other"
    )
    source_type: Mapped[str] = mapped_column(
        Enum("ics_import", "manual", "demo", name="event_source_enum"), default="manual"
    )
    source_reference: Mapped[str | None] = mapped_column(String(512))
    last_synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    user: Mapped[UserProfile] = relationship(back_populates="calendar_events")


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("user_profiles.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(256))
    description: Mapped[str | None] = mapped_column(Text)
    course_label: Mapped[str | None] = mapped_column(String(64))
    due_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    estimated_minutes: Mapped[int] = mapped_column(Integer, default=30)
    priority: Mapped[str] = mapped_column(
        Enum("low", "normal", "high", "urgent", name="priority_enum"), default="normal"
    )
    status: Mapped[str] = mapped_column(
        Enum("todo", "in_progress", "done", name="task_status_enum"), default="todo"
    )
    source_type: Mapped[str] = mapped_column(
        Enum("manual", "demo", "approved_connector", name="task_source_enum"), default="manual"
    )
    source_url: Mapped[str | None] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    user: Mapped[UserProfile] = relationship(back_populates="tasks")


class Announcement(Base):
    __tablename__ = "announcements"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("user_profiles.id"), nullable=False)
    course_label: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(256))
    body_summary: Mapped[str] = mapped_column(Text)
    published_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_url: Mapped[str | None] = mapped_column(String(512))
    source_type: Mapped[str] = mapped_column(
        Enum("demo", "approved_connector", name="ann_source_enum"), default="demo"
    )
    retrieved_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    user: Mapped[UserProfile] = relationship(back_populates="announcements")


class CampusEvent(Base):
    __tablename__ = "campus_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    title: Mapped[str] = mapped_column(String(256))
    description: Mapped[str | None] = mapped_column(Text)
    start_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    end_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    location_text: Mapped[str | None] = mapped_column(String(256))
    source_title: Mapped[str] = mapped_column(String(256))
    source_url: Mapped[str] = mapped_column(String(512))
    retrieved_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    is_demo_data: Mapped[bool] = mapped_column(Boolean, default=True)


class KnowledgeDocument(Base):
    __tablename__ = "knowledge_documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    title: Mapped[str] = mapped_column(String(256))
    publisher: Mapped[str] = mapped_column(String(256))
    canonical_url: Mapped[str] = mapped_column(String(512))
    content_text: Mapped[str] = mapped_column(Text)
    retrieved_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    last_verified_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    usage_note: Mapped[str] = mapped_column(String(512), default="Public information — curated allowlist")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    chunks: Mapped[list[KnowledgeChunk]] = relationship(back_populates="document", cascade="all, delete-orphan")


class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    document_id: Mapped[str] = mapped_column(String(36), ForeignKey("knowledge_documents.id"), nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    search_text: Mapped[str] = mapped_column(Text)  # lowercased + stripped for FTS
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    document: Mapped[KnowledgeDocument] = relationship(back_populates="chunks")


class DailyPlan(Base):
    __tablename__ = "daily_plans"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("user_profiles.id"), nullable=False)
    plan_date: Mapped[str] = mapped_column(String(10))  # YYYY-MM-DD
    timezone: Mapped[str] = mapped_column(String(64), default="America/New_York")
    generated_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    algorithm_version: Mapped[str] = mapped_column(String(32), default="v1")
    status: Mapped[str] = mapped_column(
        Enum("draft", "accepted", "rejected", name="plan_status_enum"), default="draft"
    )

    user: Mapped[UserProfile] = relationship(back_populates="daily_plans")
    blocks: Mapped[list[PlanBlock]] = relationship(back_populates="plan", cascade="all, delete-orphan")


class PlanBlock(Base):
    __tablename__ = "plan_blocks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    daily_plan_id: Mapped[str] = mapped_column(String(36), ForeignKey("daily_plans.id"), nullable=False)
    task_id: Mapped[str | None] = mapped_column(String(36))
    calendar_event_id: Mapped[str | None] = mapped_column(String(36))
    title: Mapped[str] = mapped_column(String(256))
    start_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    block_type: Mapped[str] = mapped_column(
        Enum("fixed_event", "task", "break", "suggestion", name="block_type_enum"), default="task"
    )
    reason: Mapped[str] = mapped_column(Text, default="")
    is_user_edited: Mapped[bool] = mapped_column(Boolean, default=False)

    plan: Mapped[DailyPlan] = relationship(back_populates="blocks")


class SourceReference(Base):
    __tablename__ = "source_references"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    source_type: Mapped[str] = mapped_column(String(64))
    source_title: Mapped[str] = mapped_column(String(256))
    source_url: Mapped[str] = mapped_column(String(512))
    retrieved_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    last_verified_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    trust_level: Mapped[str] = mapped_column(
        Enum("official", "user_imported", "demo", "other", name="trust_level_enum"), default="other"
    )


class SensorReading(Base):
    """Demo-only synthetic sensor data. data_origin must always be 'synthetic'."""

    __tablename__ = "sensor_readings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    sensor_label: Mapped[str] = mapped_column(String(128))
    metric_type: Mapped[str] = mapped_column(
        Enum("temperature", "air_quality", "occupancy_count", "device_health", name="metric_type_enum")
    )
    value: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(32))
    recorded_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    data_origin: Mapped[str] = mapped_column(String(32), default="synthetic")


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str | None] = mapped_column(String(36))
    action: Mapped[str] = mapped_column(String(128))
    resource_type: Mapped[str] = mapped_column(String(64))
    resource_id: Mapped[str | None] = mapped_column(String(36))
    result: Mapped[str] = mapped_column(String(32))
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
