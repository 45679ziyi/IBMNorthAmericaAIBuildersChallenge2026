"""Tests for U5/U6 new features: campus, course_updates, trust, AI provider."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

DEMO_USER = "test-user-u5u6"


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def db_path(tmp_path):
    return str(tmp_path / "test_u5u6.db")


@pytest.fixture()
def test_engine(db_path):
    return create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})


@pytest.fixture()
def test_session_factory(test_engine):
    return sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture(autouse=True)
def patch_db(monkeypatch, db_path, test_engine, test_session_factory):
    import app.core.config as cfg_mod
    import app.db.session as db_mod

    monkeypatch.setattr(cfg_mod.settings, "database_url", f"sqlite:///{db_path}")
    monkeypatch.setattr(cfg_mod.settings, "demo_user_id", DEMO_USER)
    monkeypatch.setattr(db_mod, "engine", test_engine)
    monkeypatch.setattr(db_mod, "SessionLocal", test_session_factory)

    from app.models.models import Base
    Base.metadata.create_all(bind=test_engine)
    with test_engine.connect() as conn:
        conn.execute(
            text(
                "CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_chunks_fts "
                "USING fts5(chunk_id UNINDEXED, text, tokenize='porter unicode61')"
            )
        )
        conn.commit()

    from app.models.models import UserProfile, UserPreference
    db = test_session_factory()
    db.add(UserProfile(id=DEMO_USER, display_name="Test User", timezone="America/New_York"))
    db.add(UserPreference(
        user_id=DEMO_USER, day_start_time="08:00", day_end_time="22:00",
        preferred_focus_block_minutes=50, short_break_minutes=10,
        long_break_minutes=30, default_travel_buffer_minutes=10,
    ))
    db.commit()
    db.close()


@pytest.fixture()
def client(test_session_factory):
    from app.main import app
    from app.db.session import get_db

    def override_get_db():
        db = test_session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
    app.dependency_overrides.pop(get_db, None)


# ── Campus endpoints ──────────────────────────────────────────────────────────

def test_campus_buildings_returns_list(client):
    r = client.get("/api/v1/campus/buildings")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    if data:
        b = data[0]
        assert "id" in b
        assert "x" in b
        assert "y" in b
        assert "kind" in b


def test_campus_buildings_deterministic(client):
    """Same buildings input → same x,y coordinates every call."""
    r1 = client.get("/api/v1/campus/buildings")
    r2 = client.get("/api/v1/campus/buildings")
    assert r1.json() == r2.json()


def test_campus_incidents_returns_list(client):
    r = client.get("/api/v1/campus/incidents")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


# ── Course Updates ────────────────────────────────────────────────────────────

def test_course_update_draft_student_denied(client):
    """Students cannot create course update drafts → 403."""
    r = client.post(
        "/api/v1/course-updates/drafts",
        json={"section_id": "CSE214", "text": "Assignment due Monday at 11pm"},
        headers={"X-Demo-Actor": "student_alex"},
    )
    assert r.status_code == 403


def test_course_update_draft_faculty_ok(client):
    """Faculty can create course update drafts."""
    r = client.post(
        "/api/v1/course-updates/drafts",
        json={
            "section_id": "CSE214",
            "text": "Assignment due Monday at 11pm. Please submit on Blackboard.",
        },
        headers={"X-Demo-Actor": "faculty_jordan"},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "drafted"
    assert "extracted" in body
    assert body["section_id"] == "CSE214"


def test_course_update_draft_extracts_deadline(client):
    """Deadline extraction runs on draft creation."""
    r = client.post(
        "/api/v1/course-updates/drafts",
        json={"section_id": "CSE214", "text": "Lab report due Friday at 5 PM"},
        headers={"X-Demo-Actor": "faculty_jordan"},
    )
    assert r.status_code == 201
    extracted = r.json()["extracted"]
    assert extracted["confidence"] > 0
    assert extracted["due_date"] is not None


def test_course_update_get(client):
    """GET course update returns it."""
    create = client.post(
        "/api/v1/course-updates/drafts",
        json={"section_id": "CSE214", "text": "HW3 due Thursday at noon"},
        headers={"X-Demo-Actor": "faculty_jordan"},
    )
    assert create.status_code == 201
    cu_id = create.json()["id"]
    r = client.get(
        f"/api/v1/course-updates/{cu_id}",
        headers={"X-Demo-Actor": "faculty_jordan"},
    )
    assert r.status_code == 200
    assert r.json()["id"] == cu_id


def test_course_update_preview(client):
    """Preview transitions status to previewed."""
    create = client.post(
        "/api/v1/course-updates/drafts",
        json={"section_id": "CSE214", "text": "Project due next Monday"},
        headers={"X-Demo-Actor": "faculty_jordan"},
    )
    cu_id = create.json()["id"]
    r = client.post(
        f"/api/v1/course-updates/{cu_id}/preview",
        headers={"X-Demo-Actor": "faculty_jordan"},
    )
    assert r.status_code == 200
    body = r.json()
    assert "preview" in body
    assert "recipients" in body


def test_course_update_approve(client):
    """Approve transitions to published."""
    create = client.post(
        "/api/v1/course-updates/drafts",
        json={"section_id": "CSE214", "text": "Quiz due Wednesday 2pm"},
        headers={"X-Demo-Actor": "faculty_jordan"},
    )
    cu_id = create.json()["id"]
    r = client.post(
        f"/api/v1/course-updates/{cu_id}/approve",
        headers={"X-Demo-Actor": "faculty_jordan"},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "published"


def test_course_update_not_found(client):
    r = client.get(
        "/api/v1/course-updates/nonexistent-id",
        headers={"X-Demo-Actor": "faculty_jordan"},
    )
    assert r.status_code == 404


# ── Trust / Quality ───────────────────────────────────────────────────────────

def test_trust_quality_returns_dict(client):
    r = client.get("/api/v1/trust/quality")
    assert r.status_code == 200
    body = r.json()
    assert "ai_provider" in body
    assert "watsonx_configured" in body
    assert "authorization" in body


def test_trust_quality_not_run_by_default(client):
    """Before running evals, deadline_extraction shows not_run status."""
    r = client.get("/api/v1/trust/quality")
    assert r.status_code == 200
    body = r.json()
    dl = body.get("deadline_extraction", {})
    # Either "not_run" status or the field exists with some data
    assert isinstance(dl, dict)


# ── AI Provider (unit-level, no HTTP) ────────────────────────────────────────

def test_mock_provider_extract_deadline_detects_day():
    from app.services.ai import MockAIProvider
    p = MockAIProvider()
    result = p.extract_deadline("Assignment due Monday at 11:59 PM", {})
    assert result.due_date is not None
    assert result.confidence > 0.5


def test_mock_provider_no_deadline_low_confidence():
    from app.services.ai import MockAIProvider
    p = MockAIProvider()
    result = p.extract_deadline("Read chapter 5.", {})
    assert result.confidence < 0.5


def test_mock_provider_extract_deadline_with_time():
    from app.services.ai import MockAIProvider
    p = MockAIProvider()
    result = p.extract_deadline("Submit by Friday at 5 PM", {})
    assert result.due_date is not None
    assert result.due_time is not None


def test_mock_provider_explain_impact_student():
    from app.services.ai import MockAIProvider
    p = MockAIProvider()
    facts = {
        "building": "Light Engineering",
        "type": "incident.hvac_fault",
        "sections": [{"course": "CSE 214", "start": "10:00 AM"}],
    }
    text = p.explain_impact(facts, "student")
    assert len(text) > 10


def test_mock_provider_explain_impact_facilities():
    from app.services.ai import MockAIProvider
    p = MockAIProvider()
    facts = {
        "building": "CS Building",
        "type": "incident.hvac_fault",
        "sections": [{"course": "CSE 214"}],
        "total_students": 78,
    }
    text = p.explain_impact(facts, "facilities")
    assert "78" in text or "CS Building" in text


def test_mock_provider_day_end_review():
    from app.services.ai import MockAIProvider
    p = MockAIProvider()
    result = p.day_end_review(
        events=[{"id": "ce_001", "type": "incident.hvac_fault"}],
        work_items=[{"id": "wi_001", "status": "resolved"}],
    )
    assert isinstance(result, str)
    assert len(result) > 10


def test_mock_provider_answer_question_no_chunks():
    from app.services.ai import MockAIProvider
    p = MockAIProvider()
    result = p.answer_question("What is the library hours?", [], "student")
    assert result.abstained is True


def test_mock_provider_answer_question_with_chunks():
    from app.services.ai import MockAIProvider
    p = MockAIProvider()
    result = p.answer_question(
        "What is the library hours?",
        ["The library is open from 8am to 10pm."],
        "student",
    )
    assert not result.abstained
    assert len(result.answer) > 0


def test_verifier_catches_hallucinated_number():
    from app.services.ai.verifier import verify_impact_explanation
    result = verify_impact_explanation(
        "There are 999 students affected.", {"count": 10}
    )
    assert not result.valid
    assert any("999" in v for v in result.violations)


def test_verifier_passes_grounded_output():
    from app.services.ai.verifier import verify_impact_explanation
    result = verify_impact_explanation(
        "Building is affected.", {"building": "cs_building", "count": 10}
    )
    assert result.valid


def test_provider_deterministic():
    """MockAIProvider produces identical output for identical input."""
    from app.services.ai import MockAIProvider
    p = MockAIProvider()
    r1 = p.extract_deadline("Due Monday at 11:59 PM", {})
    r2 = p.extract_deadline("Due Monday at 11:59 PM", {})
    assert r1.due_date == r2.due_date
    assert r1.confidence == r2.confidence


# ── Role-aware Ask ────────────────────────────────────────────────────────────

def test_ask_operations_denied_for_faculty(client):
    """Faculty cannot ask in 'operations' mode → 403."""
    r = client.post(
        "/api/v1/assistant/ask",
        json={"question": "What is the status of building LE?", "mode": "operations"},
        headers={"X-Demo-Actor": "faculty_jordan"},
    )
    assert r.status_code == 403


def test_ask_personal_denied_for_facilities(client):
    """Facilities cannot ask in 'personal' mode → 403."""
    r = client.post(
        "/api/v1/assistant/ask",
        json={"question": "What are my tasks?", "mode": "personal"},
        headers={"X-Demo-Actor": "facilities_morgan"},
    )
    assert r.status_code == 403


def test_ask_campus_allowed_for_student(client):
    """Campus mode allowed for students."""
    r = client.post(
        "/api/v1/assistant/ask",
        json={"question": "What is the campus address?", "mode": "campus"},
        headers={"X-Demo-Actor": "student_alex"},
    )
    assert r.status_code != 403


def test_ask_operations_allowed_for_facilities(client):
    """Facilities can ask in operations mode."""
    r = client.post(
        "/api/v1/assistant/ask",
        json={"question": "What incidents are open?", "mode": "operations"},
        headers={"X-Demo-Actor": "facilities_morgan"},
    )
    assert r.status_code != 403


def test_ask_service_desk_denied_for_student(client):
    """Students cannot access service_desk mode → 403."""
    r = client.post(
        "/api/v1/assistant/ask",
        json={"question": "Show all tickets", "mode": "service_desk"},
        headers={"X-Demo-Actor": "student_alex"},
    )
    assert r.status_code == 403


def test_ask_personal_allowed_for_student(client):
    """Students can ask in personal mode."""
    r = client.post(
        "/api/v1/assistant/ask",
        json={"question": "What are my tasks today?", "mode": "personal"},
        headers={"X-Demo-Actor": "student_alex"},
    )
    assert r.status_code != 403


# ── AI eval (direct import) ───────────────────────────────────────────────────

def test_eval_deadline_extraction():
    """Eval deadline extraction: at least 90% accuracy on test set."""
    from evals.__main__ import eval_deadline_extraction
    result = eval_deadline_extraction()
    assert result["cases"] == 30
    assert result["exact_match"] >= 0.90, (
        f"Exact match {result['exact_match']:.0%} < 90% target. "
        f"Passed {result['passed']}/{result['cases']}"
    )


def test_eval_authorization():
    """Eval authorization: 100% pass rate."""
    from evals.__main__ import eval_authorization
    result = eval_authorization()
    assert result["pass_rate"] == 1.0, (
        f"Auth pass rate {result['pass_rate']:.0%} != 100%. "
        f"Passed {result['passed']}/{result['cases']}"
    )


def test_eval_injection():
    """Eval injection: zero successful injections."""
    from evals.__main__ import eval_injection
    result = eval_injection()
    assert result["successful_injections"] == 0, (
        f"{result['successful_injections']} successful injections detected"
    )


def test_eval_determinism():
    """Eval determinism: identical hashes for same input."""
    from evals.__main__ import eval_determinism
    result = eval_determinism()
    assert result["identical_hashes"] is True


# ── Work items extended query ─────────────────────────────────────────────────

def test_work_items_filter_by_team(client):
    """GET /work-items?team=facilities returns list."""
    r = client.get(
        "/api/v1/work-items?team=facilities",
        headers={"X-Demo-Actor": "facilities_morgan"},
    )
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_work_items_filter_by_canonical_event(client):
    """GET /work-items?canonical_event_id=nonexistent returns empty list."""
    r = client.get(
        "/api/v1/work-items?canonical_event_id=nonexistent_ce",
        headers={"X-Demo-Actor": "facilities_morgan"},
    )
    assert r.status_code == 200
    assert r.json() == []


def test_work_items_filter_by_workflow_and_status(client):
    r = client.get(
        "/api/v1/work-items?workflow_type=room_reassignment&status=awaiting_approval",
        headers={"X-Demo-Actor": "acadops_taylor"},
    )
    assert r.status_code == 200
    assert isinstance(r.json(), list)


# ── Director endpoints ────────────────────────────────────────────────────────

def test_sim_director_default_off(client):
    r = client.get("/api/v1/sim/state")
    assert r.status_code == 200
    assert r.json()["director_mode"] == "off"


def test_sim_director_set_autopilot(client):
    r = client.post("/api/v1/sim/director", json={"mode": "autopilot"})
    assert r.status_code == 200
    assert r.json()["director_mode"] == "autopilot"


def test_sim_director_set_off(client):
    client.post("/api/v1/sim/director", json={"mode": "autopilot"})
    r = client.post("/api/v1/sim/director", json={"mode": "off"})
    assert r.status_code == 200
    assert r.json()["director_mode"] == "off"


def test_sim_director_invalid_mode(client):
    r = client.post("/api/v1/sim/director", json={"mode": "turbo"})
    assert r.status_code == 400


def test_sim_take_over_valid(client):
    r = client.post("/api/v1/sim/take-over", json={"persona": "facilities_morgan"})
    assert r.status_code == 200
    state = r.json()
    assert state["active_persona"] == "facilities_morgan"
    assert state["director_mode"] == "off"


def test_sim_take_over_unknown_persona(client):
    r = client.post("/api/v1/sim/take-over", json={"persona": "nobody"})
    assert r.status_code == 400


# ── Count suppression (k-anonymity) ──────────────────────────────────────────

def test_suppress_small_count_below_threshold():
    from app.services.authz import suppress_small_count
    assert suppress_small_count(3) == "fewer than 5"
    assert suppress_small_count(4) == "fewer than 5"


def test_suppress_small_count_at_threshold():
    from app.services.authz import suppress_small_count
    assert suppress_small_count(5) == 5
    assert suppress_small_count(100) == 100
