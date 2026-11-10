"""Pydantic schemas for AURORA API request/response validation."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional
from pydantic import BaseModel, Field, HttpUrl


# ─── Common ──────────────────────────────────────────────────────────────────

class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    version: str
    database: str
    ai_provider: str
    disclaimer: str = (
        "AURORA is an independent educational prototype. "
        "Not affiliated with or endorsed by Stony Brook University or IBM."
    )


# ─── UserProfile ─────────────────────────────────────────────────────────────

class UserProfileRead(BaseModel):
    id: str
    display_name: Optional[str]
    timezone: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ─── CalendarEvent ───────────────────────────────────────────────────────────

class CalendarEventCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=256)
    description: Optional[str] = None
    start_at_utc: datetime
    end_at_utc: datetime
    location_text: Optional[str] = Field(None, max_length=256)
    event_type: Literal["class", "meeting", "personal", "other"] = "other"
    source_type: Literal["ics_import", "manual", "demo", "scenario", "aurora_block"] = "manual"
    source_reference: Optional[str] = None


class CalendarEventUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=256)
    description: Optional[str] = None
    start_at_utc: Optional[datetime] = None
    end_at_utc: Optional[datetime] = None
    location_text: Optional[str] = None
    event_type: Optional[Literal["class", "meeting", "personal", "other"]] = None


class CalendarEventRead(BaseModel):
    id: str
    user_id: str
    title: str
    description: Optional[str]
    start_at_utc: datetime
    end_at_utc: datetime
    location_text: Optional[str]
    event_type: str
    source_type: str
    source_reference: Optional[str]
    last_synced_at: datetime

    model_config = {"from_attributes": True}


class ICSImportResponse(BaseModel):
    imported: int
    skipped: int
    warnings: list[str]
    events: list[CalendarEventRead]


# ─── Task ────────────────────────────────────────────────────────────────────

class TaskCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=256)
    description: Optional[str] = None
    course_label: Optional[str] = Field(None, max_length=64)
    due_at_utc: Optional[datetime] = None
    estimated_minutes: int = Field(default=30, ge=1, le=1440)
    priority: Literal["low", "normal", "high", "urgent"] = "normal"
    status: Literal["todo", "in_progress", "done"] = "todo"
    source_type: Literal["manual", "demo", "approved_connector"] = "manual"
    source_url: Optional[str] = None


class TaskUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=256)
    description: Optional[str] = None
    course_label: Optional[str] = None
    due_at_utc: Optional[datetime] = None
    estimated_minutes: Optional[int] = Field(None, ge=1, le=1440)
    priority: Optional[Literal["low", "normal", "high", "urgent"]] = None
    status: Optional[Literal["todo", "in_progress", "done"]] = None


class TaskRead(BaseModel):
    id: str
    user_id: str
    title: str
    description: Optional[str]
    course_label: Optional[str]
    due_at_utc: Optional[datetime]
    estimated_minutes: int
    priority: str
    status: str
    source_type: str
    source_url: Optional[str]
    source_signal_id: Optional[str] = None
    provenance: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ─── Announcement ────────────────────────────────────────────────────────────

class AnnouncementRead(BaseModel):
    id: str
    user_id: str
    course_label: str
    title: str
    body_summary: str
    published_at_utc: Optional[datetime]
    source_url: Optional[str]
    source_type: str
    retrieved_at_utc: datetime
    is_demo: bool = True
    is_read: bool = False
    read_at_utc: Optional[datetime] = None

    model_config = {"from_attributes": True}


class AnnouncementUpdate(BaseModel):
    is_read: bool


# ─── Campus Event ────────────────────────────────────────────────────────────

class CampusEventRead(BaseModel):
    id: str
    title: str
    description: Optional[str]
    start_at_utc: Optional[datetime]
    end_at_utc: Optional[datetime]
    location_text: Optional[str]
    source_title: str
    source_url: str
    retrieved_at_utc: datetime
    is_demo_data: bool

    model_config = {"from_attributes": True}


# ─── Daily Plan ──────────────────────────────────────────────────────────────

class PlanBlockRead(BaseModel):
    id: str
    task_id: Optional[str]
    calendar_event_id: Optional[str]
    title: str
    start_at_utc: datetime
    end_at_utc: datetime
    block_type: str
    reason: str
    is_user_edited: bool

    model_config = {"from_attributes": True}


class DailyPlanRead(BaseModel):
    id: str
    user_id: str
    plan_date: str
    timezone: str
    generated_at_utc: datetime
    algorithm_version: str
    status: str
    blocks: list[PlanBlockRead]
    unscheduled: list[dict[str, Any]] = []
    warnings: list[str] = []

    model_config = {"from_attributes": True}


class PlanGenerateRequest(BaseModel):
    plan_date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    timezone: str = "America/New_York"


# ─── Knowledge / Assistant ───────────────────────────────────────────────────

class KnowledgeSearchResult(BaseModel):
    chunk_id: str
    document_id: str
    title: str
    publisher: str
    canonical_url: str
    text: str
    last_verified_at_utc: datetime
    score: float = 0.0


class AssistantSource(BaseModel):
    title: str
    url: str
    publisher: str
    last_verified_at_utc: datetime
    excerpt: str


class AssistantAskRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=1000)
    mode: Optional[str] = "campus"   # personal | course | campus | operations | service_desk


class AssistantAskResponse(BaseModel):
    answer: str
    sources: list[AssistantSource]
    coverage: Literal["supported", "partial", "not_found"]
    coverage_score: float = 0.0
    matched_terms: list[str] = []
    updated_at: datetime
    disclaimer: str = (
        "AI-generated responses are for informational purposes only. "
        "Verify with official university sources for academic decisions."
    )


# ─── Sensor / Campus Pulse ───────────────────────────────────────────────────

class SensorReadingRead(BaseModel):
    id: str
    sensor_label: str
    metric_type: str
    value: float
    unit: str
    recorded_at_utc: datetime
    data_origin: str

    model_config = {"from_attributes": True}


class PulseSeriesPoint(BaseModel):
    recorded_at_utc: datetime
    value: float
    data_origin: str = "synthetic"


class PulseSeries(BaseModel):
    sensor_label: str
    metric_type: str
    unit: str
    capacity: Optional[float] = None
    points: list[PulseSeriesPoint]
    data_origin: str = "synthetic"


class PulseInsight(BaseModel):
    id: str
    severity: str
    sensor_label: str
    metric_type: str
    message: str
    evidence: dict[str, Any]
    recommended_human_action: str
    automated_action: Optional[str] = None
    status: str = "needs_human_review"
    data_origin: str = "synthetic"


# ─── Connector Status ────────────────────────────────────────────────────────

class ConnectorStatus(BaseModel):
    name: str
    status: Literal["connected", "demo", "unavailable"]
    description: str
    last_checked: datetime
    data_categories: list[str]
    purpose: str
    sends_to_external_model: bool = False


# ─── Dashboard ───────────────────────────────────────────────────────────────

# ─── Sim / Scenario (V2) ─────────────────────────────────────────────────────

class SimStateResponse(BaseModel):
    mode: str
    scenario_id: Optional[str]
    anchor_date: Optional[str]
    virtual_now: Optional[datetime]
    applied_signal_ids: list[str]
    director_mode: str = "off"      # "off" | "autopilot"
    active_persona: Optional[str] = None
    pending_step_ids: list[str] = []


class SignalResponse(BaseModel):
    id: str
    feed: str
    kind: str
    at_utc: datetime
    summary: str
    payload: dict
    relevance: str
    relevance_reason: Optional[str]
    data_origin: str


class FeedStatusResponse(BaseModel):
    feed: str
    last_signal_at: Optional[datetime]
    signals_seen: int
    signals_filtered: int


class SimStartRequest(BaseModel):
    scenario_id: str


class SimAdvanceRequest(BaseModel):
    minutes: Optional[int] = None
    to: Optional[str] = None          # "HH:MM"
    to_next_signal: bool = False


# ─── Dashboard ───────────────────────────────────────────────────────────────

class DashboardToday(BaseModel):
    date: str
    timezone: str
    greeting: str
    events_today: list[CalendarEventRead]
    tasks_open: list[TaskRead]
    upcoming_deadlines: list[TaskRead]
    campus_events: list[CampusEventRead]
    weather: dict[str, Any]
    connectors: list[ConnectorStatus]
    last_updated: datetime


# ─── Moves (M2) ──────────────────────────────────────────────────────────────

class WhyItem(BaseModel):
    feed: str
    signal_id: Optional[str] = None
    text: str


class ActionSpec(BaseModel):
    id: str
    type: str
    params: dict
    external: bool = False
    simulated: bool = False


class MoveResponse(BaseModel):
    id: str
    key: str
    kind: str
    audience: str
    status: str
    policy: str
    urgency: str
    impact: str
    title: str
    summary: str
    why: list[WhyItem]
    actions: list[ActionSpec]
    fingerprint: str
    created_at: datetime
    updated_at: datetime


# ─── Autonomy Policy (M3) ────────────────────────────────────────────────────

class AutonomyResponse(BaseModel):
    policy: dict[str, str]
    locked: list[str]
    note: str = (
        "Locked categories cannot be set to 'auto'. "
        "See docs/V2_BRIEF.md Section 5.5."
    )


class AutonomyUpdateRequest(BaseModel):
    category: str
    value: Literal["auto", "ask"]


# ─── Ops / Incidents (M5) ────────────────────────────────────────────────────

class OpsIncident(BaseModel):
    id: str
    room_id: str
    room_name: str
    type: str
    temperature_c: Optional[float] = None
    trend: Optional[str] = None
    reported_at_utc: datetime
    status: str  # "active" | "resolved"


class AffectedClass(BaseModel):
    commitment_id: str
    title: str
    course: str
    start: str
    end: str
    room_name: str
    enrolled: int
    status: str  # "in_session" | "not_started"
    feasible_rooms: list[dict] = []  # for not_started only


class ImpactGraph(BaseModel):
    incident: OpsIncident
    affected_classes: list[AffectedClass]
    total_students: int
    feasible_mitigations: list[dict]
    student_effect: str
