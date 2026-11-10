"""SQLAlchemy ORM models for AURORA."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

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


def _ce_id() -> str:
    """Generate a canonical event ID with ce_ prefix."""
    return "ce_" + uuid.uuid4().hex[:12]


def _wi_id() -> str:
    """Generate a work item ID with wi_ prefix."""
    return "wi_" + uuid.uuid4().hex[:12]


def _wt_id() -> str:
    """Generate a work item transition ID with wt_ prefix."""
    return "wt_" + uuid.uuid4().hex[:12]


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    from app.core.clock import get_now
    return get_now()


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
        Enum("class", "meeting", "personal", "other", "aurora_block", name="event_type_enum"), default="other"
    )
    source_type: Mapped[str] = mapped_column(
        Enum("ics_import", "manual", "demo", "scenario", "aurora_block", name="event_source_enum"), default="manual"
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
    source_signal_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    provenance: Mapped[str] = mapped_column(String, default="manual")
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
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    read_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

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


class SimState(Base):
    """Single-row table tracking the scenario runner state."""
    __tablename__ = "sim_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    mode: Mapped[str] = mapped_column(String, default="real")          # "real" | "scenario"
    scenario_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    anchor_date: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # YYYY-MM-DD
    virtual_now: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    applied_signal_ids: Mapped[str] = mapped_column(String, default="[]")  # JSON array
    # U3: Director mode
    director_mode: Mapped[str] = mapped_column(String, default="off")  # "autopilot" | "off"
    active_persona: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # JSON array of step IDs that have been executed (human or autopilot)
    executed_step_ids: Mapped[str] = mapped_column(String, default="[]")


class Signal(Base):
    """Signals ingested from feed adapters during a scenario run."""
    __tablename__ = "signals"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    feed: Mapped[str] = mapped_column(String)
    kind: Mapped[str] = mapped_column(String)
    at_utc: Mapped[datetime] = mapped_column(DateTime)
    summary: Mapped[str] = mapped_column(String)
    payload: Mapped[str] = mapped_column(String, default="{}")          # JSON
    relevance: Mapped[str] = mapped_column(String, default="relevant")  # "relevant" | "filtered"
    relevance_reason: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    data_origin: Mapped[str] = mapped_column(String, default="synthetic")
    scenario_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    canonical_event_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)


class ActionLog(Base):
    """Audit log of actions executed against a Move."""
    __tablename__ = "action_log"

    id: Mapped[str] = mapped_column(String, primary_key=True)           # uuid4 hex
    move_id: Mapped[str] = mapped_column(String, ForeignKey("moves.id"))
    action_type: Mapped[str] = mapped_column(String)
    params: Mapped[str] = mapped_column(String, default="{}")           # JSON
    status: Mapped[str] = mapped_column(String, default="executed")     # executed | executed_simulated | draft_only | undone
    simulated: Mapped[bool] = mapped_column(Boolean, default=False)
    undo_payload: Mapped[str] = mapped_column(String, default="{}")     # JSON
    result_text: Mapped[str] = mapped_column(String, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class Reminder(Base):
    """User reminders created by the autonomy engine or manually."""
    __tablename__ = "reminders"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    text: Mapped[str] = mapped_column(String)
    at_utc: Mapped[datetime] = mapped_column(DateTime)
    fired: Mapped[bool] = mapped_column(Boolean, default=False)
    move_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    scenario_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)


class AutonomyPolicy(Base):
    """Single-row table storing the demo user's autonomy policy as JSON."""
    __tablename__ = "autonomy_policy"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Stored as JSON; one row per user (always user_id=1 in the prototype)
    policy_json: Mapped[str] = mapped_column(String, default="{}")


# ── U1: Identity models ────────────────────────────────────────────────────────

class Person(Base):
    """A persona in the tenant — student, faculty, facilities, IT, etc."""
    __tablename__ = "people"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)   # e.g. "student_alex"
    display_name: Mapped[str] = mapped_column(String(128))
    role: Mapped[str] = mapped_column(String(64))                    # student | faculty | facilities | it | academic_ops | org_organizer
    email_local: Mapped[str | None] = mapped_column(String(128), nullable=True)
    data_origin: Mapped[str] = mapped_column(String(32), default="synthetic")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class Team(Base):
    """A team in the tenant (facilities, IT, academic operations, etc.)."""
    __tablename__ = "teams"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    role_type: Mapped[str] = mapped_column(String(64))              # facilities | it | academic_ops | advising | org
    scope_type: Mapped[str] = mapped_column(String(32), default="building")  # building | service | department | campus
    scope_id: Mapped[str | None] = mapped_column(String(64), nullable=True)  # the building/service/dept ID
    data_origin: Mapped[str] = mapped_column(String(32), default="synthetic")


class TeamMembership(Base):
    """Maps a person to a team."""
    __tablename__ = "team_memberships"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    person_id: Mapped[str] = mapped_column(String(64))
    team_id: Mapped[str] = mapped_column(String(64))
    is_lead: Mapped[bool] = mapped_column(Boolean, default=False)


class RoleAssignment(Base):
    """Assigns a role to a person within an optional scope."""
    __tablename__ = "role_assignments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    person_id: Mapped[str] = mapped_column(String(64))
    role: Mapped[str] = mapped_column(String(64))
    scope_type: Mapped[str | None] = mapped_column(String(32), nullable=True)  # campus | building | dept | service
    scope_id: Mapped[str | None] = mapped_column(String(64), nullable=True)


class Move(Base):
    """AI-proposed action moves generated by the campus intelligence engine."""
    __tablename__ = "moves"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    key: Mapped[str] = mapped_column(String, index=True)    # unique business key
    kind: Mapped[str] = mapped_column(String)               # detector name
    audience: Mapped[str] = mapped_column(String)           # "student" | "staff"
    status: Mapped[str] = mapped_column(String, default="proposed")
    policy: Mapped[str] = mapped_column(String)             # "auto" | "ask" | "info"
    urgency: Mapped[str] = mapped_column(String, default="today")
    impact: Mapped[str] = mapped_column(String, default="medium")
    title: Mapped[str] = mapped_column(String)
    summary: Mapped[str] = mapped_column(String)
    why: Mapped[str] = mapped_column(String, default="[]")          # JSON list
    actions: Mapped[str] = mapped_column(String, default="[]")      # JSON list
    fingerprint: Mapped[str] = mapped_column(String, default="")    # sha1 of title+summary+actions
    scenario_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    canonical_event_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    dismissed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


# ── U2: Tenant pack models ──────────────────────────────────────────────────────

class TenantConfig(Base):
    """Tenant configuration loaded from pack — one row per tenant DB."""
    __tablename__ = "tenant_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64))
    timezone: Mapped[str] = mapped_column(String(64))
    clock: Mapped[str] = mapped_column(String(8), default="12h")        # "12h" | "24h"
    week_start: Mapped[str] = mapped_column(String(16), default="sunday")
    course_code_format: Mapped[str] = mapped_column(String(64), default="{d} {n}")
    room_code_format: Mapped[str] = mapped_column(String(64), default="{b} {r}")
    credit_unit: Mapped[str] = mapped_column(String(32), default="credits")
    role_vocabulary: Mapped[str] = mapped_column(String, default="{}")  # JSON
    min_cell_size: Mapped[int] = mapped_column(Integer, default=5)
    extra_json: Mapped[str] = mapped_column(String, default="{}")       # JSON for future keys


class EntityLink(Base):
    """Directed relationship between two campus entities (Section 4.3)."""
    __tablename__ = "entity_links"
    __table_args__ = (
        UniqueConstraint("from_type", "from_id", "rel", "to_type", "to_id",
                         name="uq_entity_link"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    from_type: Mapped[str] = mapped_column(String(64))   # e.g. "room"
    from_id: Mapped[str] = mapped_column(String(64))
    rel: Mapped[str] = mapped_column(String(64))         # e.g. "in_building"
    to_type: Mapped[str] = mapped_column(String(64))     # e.g. "building"
    to_id: Mapped[str] = mapped_column(String(64))
    # V4-05: optional JSON blob for entity attributes (capacity, features, name, meetings…)
    meta_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


# ── V4-05: Scenario models ─────────────────────────────────────────────────────

class ScenarioRun(Base):
    """A what-if scenario run. Does NOT mutate canonical state.

    Records inputs, computed results, and promotion status.
    A scenario run is always read-only until explicitly promoted by an
    authorized actor — promotion writes a separate decision audit record.
    """
    __tablename__ = "scenario_runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), default="sbu_demo")
    canonical_event_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    engine_version: Mapped[str] = mapped_column(String(32), default="v1")
    scenario_type: Mapped[str] = mapped_column(String(64), default="classroom_outage")
    inputs_json: Mapped[str] = mapped_column(Text, default="{}")   # typed input params
    result_json: Mapped[str] = mapped_column(Text, default="{}")   # full ScenarioResult
    result_hash: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="computed")
    # computed | stale | promoted | cancelled
    promoted_by: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    promoted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    promoted_option_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    promotion_rationale: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    data_origin: Mapped[str] = mapped_column(String(32), default="synthetic_simulation")
    created_by: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


# ── U3: Canonical event models ─────────────────────────────────────────────────

class CanonicalEvent(Base):
    """Envelope for a campus event ingested from any feed or report."""
    __tablename__ = "canonical_events"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_ce_id)
    tenant_id: Mapped[str] = mapped_column(String(64), default="sbu_demo")
    type: Mapped[str] = mapped_column(String(128))          # e.g. "incident.hvac_fault"
    status: Mapped[str] = mapped_column(String(64), default="reported")
    # reported | triage | impact_assessed | mitigated | resolved | closed
    severity: Mapped[str] = mapped_column(String(32), default="medium")  # high | medium | low
    correlation_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    source_feed: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    source_record_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    occurred_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    received_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    entity_refs_json: Mapped[str] = mapped_column(Text, default="[]")   # JSON array of {type, id}
    classification: Mapped[str] = mapped_column(String(32), default="institutional")
    # public | institutional | personal | restricted
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    data_origin: Mapped[str] = mapped_column(String(32), default="synthetic")
    schema_version: Mapped[str] = mapped_column(String(32), default="event-envelope/1")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    corroborations: Mapped[int] = mapped_column(Integer, default=0)
    last_actor: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    last_actor_mode: Mapped[str] = mapped_column(String(16), default="human")  # human | autopilot

    work_items: Mapped[list["WorkItem"]] = relationship(back_populates="canonical_event",
                                                         cascade="all, delete-orphan")


class WorkItem(Base):
    """Workflow work item — one per canonical event × workflow type."""
    __tablename__ = "work_items"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_wi_id)
    canonical_event_id: Mapped[Optional[str]] = mapped_column(
        String(64), ForeignKey("canonical_events.id"), nullable=True
    )
    workflow_type: Mapped[str] = mapped_column(String(64))
    # course_update | incident_response | room_reassignment | service_disruption
    # | service_request | event_change
    status: Mapped[str] = mapped_column(String(64))
    version: Mapped[int] = mapped_column(Integer, default=1)  # optimistic lock
    owner_person_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    assigned_team_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    tenant_id: Mapped[str] = mapped_column(String(64), default="sbu_demo")
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    required_next_fields_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    canonical_event: Mapped[Optional["CanonicalEvent"]] = relationship(back_populates="work_items")
    transitions: Mapped[list["WorkItemTransition"]] = relationship(
        back_populates="work_item", cascade="all, delete-orphan"
    )


class WorkItemTransition(Base):
    """Audit log of all workflow transitions."""
    __tablename__ = "work_item_transitions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_wt_id)
    work_item_id: Mapped[str] = mapped_column(String(64), ForeignKey("work_items.id"), nullable=False)
    from_status: Mapped[str] = mapped_column(String(64))
    to_status: Mapped[str] = mapped_column(String(64))
    actor_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    actor_role: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    actor_mode: Mapped[str] = mapped_column(String(16), default="human")  # human | autopilot
    rationale: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    effects_json: Mapped[str] = mapped_column(Text, default="{}")
    virtual_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    work_item: Mapped["WorkItem"] = relationship(back_populates="transitions")


# ─── U4: Notification + NotificationPref + AccessLog ─────────────────────────

class Notification(Base):
    """In-app notification record with why[] evidence path."""
    __tablename__ = "notifications"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    canonical_event_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    work_item_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    recipient_person_id: Mapped[str] = mapped_column(String(64), nullable=False)
    kind: Mapped[str] = mapped_column(
        String(64), default="system"
    )  # course_update | incident_status | service_disruption | room_change | event_change | system
    title: Mapped[str] = mapped_column(String(256))
    body: Mapped[str] = mapped_column(Text, default="")
    why_json: Mapped[str] = mapped_column(
        Text, default="[]"
    )  # JSON array: [{rel, entity_type, entity_id, text}]
    state: Mapped[str] = mapped_column(
        String(32), default="unread"
    )  # unread | read | acknowledged
    requires_ack: Mapped[bool] = mapped_column(Boolean, default=False)
    data_origin: Mapped[str] = mapped_column(String(32), default="synthetic")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    read_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    # V4-03: idempotency key to prevent duplicate notifications on retry
    idempotency_key: Mapped[Optional[str]] = mapped_column(
        String(128), nullable=True, unique=False, index=True
    )


class NotificationPref(Base):
    """Per-person notification preference by category."""
    __tablename__ = "notification_prefs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    person_id: Mapped[str] = mapped_column(String(64), nullable=False)
    category: Mapped[str] = mapped_column(
        String(64), nullable=False
    )  # course_update | incident_status | service_disruption | room_change | event_change | system
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class AccessLog(Base):
    """Audit trail of who accessed what data and why."""
    __tablename__ = "access_log"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    actor_id: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_role: Mapped[str] = mapped_column(String(64), nullable=False)
    purpose: Mapped[str] = mapped_column(
        String(128), nullable=False
    )  # course_management | inbox_view | reach_map
    resource_type: Mapped[str] = mapped_column(
        String(64), nullable=False
    )  # notification_reach | section_roster | service_request
    record_count: Mapped[int] = mapped_column(Integer, default=0)
    canonical_event_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    person_id_accessed: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    virtual_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


# ─── U4: Thread + ThreadMessage ───────────────────────────────────────────────

class Thread(Base):
    """Discussion thread attached to a canonical event, work item, or service request."""
    __tablename__ = "threads"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    canonical_event_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    work_item_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    service_request_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    title: Mapped[str] = mapped_column(String(256), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    messages: Mapped[list["ThreadMessage"]] = relationship(
        back_populates="thread", cascade="all, delete-orphan"
    )


class ThreadMessage(Base):
    """A single message in a thread. Body is stored escaped and length-capped."""
    __tablename__ = "thread_messages"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    thread_id: Mapped[str] = mapped_column(String(64), ForeignKey("threads.id"), nullable=False)
    author_person_id: Mapped[str] = mapped_column(String(64), nullable=False)
    body: Mapped[str] = mapped_column(Text)  # UNTRUSTED: must be HTML-escaped before storage
    data_origin: Mapped[str] = mapped_column(String(32), default="synthetic")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    thread: Mapped["Thread"] = relationship(back_populates="messages")


# ─── U4: ServiceRequest ───────────────────────────────────────────────────────

class ServiceRequest(Base):
    """Service request with status-machine and team routing."""
    __tablename__ = "service_requests"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String(64), default="sbu_demo")
    requester_person_id: Mapped[str] = mapped_column(String(64), nullable=False)
    service_id: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(256))
    body: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(
        String(32), default="submitted"
    )  # submitted | triaged | in_progress | resolved | closed
    assigned_team_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    # V4-03 (Finding N): optional link to the canonical event that triggered this request
    canonical_event_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    data_origin: Mapped[str] = mapped_column(String(32), default="synthetic")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


# ─── U5-5: CourseUpdate ────────────────────────────────────────────────────────

class CourseUpdate(Base):
    """Faculty course update draft with AI-extracted deadline."""
    __tablename__ = "course_updates"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    section_id: Mapped[str] = mapped_column(String(64), nullable=False)
    author_person_id: Mapped[str] = mapped_column(String(64), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), default="drafted"
    )  # drafted | previewed | approved | published
    extracted_json: Mapped[str] = mapped_column(
        Text, default="{}"
    )  # {title, due_date, due_time, est_minutes, confidence, quote}
    canonical_event_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    ai_run_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    tenant_id: Mapped[str] = mapped_column(String(64), default="sbu_demo")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


# ─── U6-3: AIRun ─────────────────────────────────────────────────────────────

class AIRun(Base):
    """Audit record for an AI task run."""
    __tablename__ = "ai_runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_uuid)
    task: Mapped[str] = mapped_column(String(64))         # deadline_extraction | impact_explanation | qa | day_end_review
    provider: Mapped[str] = mapped_column(String(32), default="mock")
    input_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    validated: Mapped[bool] = mapped_column(Boolean, default=False)
    fallback_used: Mapped[bool] = mapped_column(Boolean, default=True)
    latency_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    tenant_id: Mapped[str] = mapped_column(String(64), default="sbu_demo")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
