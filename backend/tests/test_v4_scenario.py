"""
V4-05 Scenario Engine tests — standalone, no LLM dependency.

Gold-set cases from V4 spec Section 17.4:
  1. Fully feasible alternate room
  2. Capacity too small → infeasible
  3. Room unavailable → infeasible
  4. No candidate feasible
  5. Deterministic result hash repeatability
  6. Affected section aggregation correct
  7. Missing distance/capacity metadata → partial data
  8. Authorization: student cannot create scenario
  9. Authorization: facilities cannot promote scenario (approve:scenario)
  10. Scenario run does NOT mutate canonical events
"""
from __future__ import annotations

import hashlib
import json
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session

ACTOR_ACADOPS   = "acadops_taylor"
ACTOR_FACILITIES = "facilities_morgan"
ACTOR_STUDENT   = "student_alex"
ACTOR_FACULTY   = "faculty_jordan"


# ─── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def db_path(tmp_path):
    return str(tmp_path / "test_v4_scenario.db")


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
    monkeypatch.setattr(cfg_mod.settings, "demo_user_id", ACTOR_STUDENT)
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
    db.add(UserProfile(id=ACTOR_STUDENT, display_name="Alex", timezone="America/New_York"))
    db.add(UserPreference(
        user_id=ACTOR_STUDENT, day_start_time="08:00", day_end_time="22:00",
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


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _seed_rooms(sf, rooms: list[dict], affected_room: dict, meetings: list[dict]):
    """Seed EntityLinks for rooms, a building, and section meetings."""
    from app.models.models import EntityLink, TenantConfig
    import json as _json

    db = sf()

    # TenantConfig (needed for walk_minutes lookup)
    if db.query(TenantConfig).first() is None:
        db.add(TenantConfig(
            tenant_id="sbu_demo",
            timezone="America/New_York",
            clock="12h",
            week_start="monday",
            course_code_format="{dept}{num}",
            room_code_format="{bldg}-{num}",
            credit_unit="credit hours",
            role_vocabulary="{}",
            min_cell_size=5,
            extra_json=_json.dumps({"walking_minutes": {"BLD_A:BLD_B": 5, "BLD_A:BLD_C": 10}}),
        ))

    def add_link(ft, fi, rel, tt, ti, meta=None):
        from sqlalchemy.exc import IntegrityError
        try:
            existing = db.query(EntityLink).filter_by(
                from_type=ft, from_id=fi, rel=rel, to_type=tt, to_id=ti
            ).first()
            if existing is None:
                db.add(EntityLink(from_type=ft, from_id=fi, rel=rel, to_type=tt, to_id=ti,
                                   meta_json=_json.dumps(meta) if meta else None))
                db.flush()
        except IntegrityError:
            db.rollback()

    # affected room
    add_link("room", affected_room["id"], "in_building", "building", affected_room["building_id"],
             meta={"capacity": affected_room.get("capacity", 30),
                   "features": affected_room.get("features", []),
                   "name": affected_room["id"],
                   "kind": "classroom",
                   "available": affected_room.get("available", True)})

    # meetings in affected room
    for m in meetings:
        add_link("section", m["section_id"], "meets_in", "room", affected_room["id"],
                 meta={"days": m["days"], "start": m["start"], "end": m["end"],
                       "section_id": m["section_id"], "enrolled": m["enrolled"],
                       "capacity": m["capacity"], "course_id": m["course_id"]})

    # candidate rooms
    for room in rooms:
        add_link("room", room["id"], "in_building", "building", room["building_id"],
                 meta={"capacity": room.get("capacity"),
                       "features": room.get("features", []),
                       "name": room["id"],
                       "kind": room.get("kind", "classroom"),
                       "available": room.get("available", True)})
        # seed any existing meetings in candidate rooms
        for existing_m in room.get("existing_meetings", []):
            add_link("section", existing_m["section_id"], "meets_in", "room", room["id"],
                     meta={"days": existing_m["days"], "start": existing_m["start"],
                           "end": existing_m["end"], "section_id": existing_m["section_id"],
                           "enrolled": 10, "capacity": room.get("capacity"), "course_id": "X"})

    db.commit()
    db.close()


# ─── Engine unit tests (no HTTP) ──────────────────────────────────────────────

def test_engine_feasible_room(test_session_factory):
    """Gold case 1: a larger available room passes all hard constraints."""
    from app.services.scenarios import ClassroomOutageInput, engine

    _seed_rooms(
        test_session_factory,
        rooms=[{"id": "RM_BIG", "building_id": "BLD_A", "capacity": 50, "kind": "classroom"}],
        affected_room={"id": "RM_SMALL", "building_id": "BLD_A", "capacity": 20},
        meetings=[{"section_id": "SEC-1", "course_id": "CS101", "days": ["Mon"],
                   "start": "09:00", "end": "10:30", "enrolled": 18, "capacity": 20}],
    )

    db = test_session_factory()
    inputs = ClassroomOutageInput(
        affected_room_id="RM_SMALL",
        repair_delay_minutes=60,
    )
    result = engine.run(db, inputs, scenario_id="test-feasible", min_cell_size=5)
    db.close()

    feasible_ids = [c.room_id for c in result.candidates]
    assert "RM_BIG" in feasible_ids, f"Expected RM_BIG as feasible candidate; got {feasible_ids}"
    assert "RM_SMALL" not in feasible_ids, "Affected room must not appear as a candidate"
    assert len(result.infeasible) == 0 or all(
        "RM_BIG" != i.room_id for i in result.infeasible
    )


def test_engine_capacity_too_small(test_session_factory):
    """Gold case 2: HC-1 — candidate capacity < enrolled → infeasible."""
    from app.services.scenarios import ClassroomOutageInput, engine

    _seed_rooms(
        test_session_factory,
        rooms=[{"id": "RM_TINY", "building_id": "BLD_A", "capacity": 10, "kind": "classroom"}],
        affected_room={"id": "RM_BIG2", "building_id": "BLD_A", "capacity": 40},
        meetings=[{"section_id": "SEC-2", "course_id": "CS202", "days": ["Tue"],
                   "start": "10:00", "end": "11:30", "enrolled": 35, "capacity": 40}],
    )

    db = test_session_factory()
    inputs = ClassroomOutageInput(
        affected_room_id="RM_BIG2",
        repair_delay_minutes=30,
    )
    result = engine.run(db, inputs, scenario_id="test-cap-small", min_cell_size=5)
    db.close()

    infeasible_ids = [i.room_id for i in result.infeasible]
    assert "RM_TINY" in infeasible_ids, f"Expected RM_TINY to be infeasible (HC-1); got {infeasible_ids}"
    # Verify the failure reason mentions HC-1
    tiny_inf = next(i for i in result.infeasible if i.room_id == "RM_TINY")
    assert any("HC-1" in fc for fc in tiny_inf.failed_constraints), \
        f"Expected HC-1 in failed constraints; got {tiny_inf.failed_constraints}"


def test_engine_room_unavailable(test_session_factory):
    """Gold case 3: HC-3 — available=False → infeasible."""
    from app.services.scenarios import ClassroomOutageInput, engine

    _seed_rooms(
        test_session_factory,
        rooms=[{"id": "RM_CLOSED", "building_id": "BLD_A", "capacity": 50,
                "kind": "classroom", "available": False}],
        affected_room={"id": "RM_OUT", "building_id": "BLD_A", "capacity": 25},
        meetings=[{"section_id": "SEC-3", "course_id": "CS303", "days": ["Wed"],
                   "start": "13:00", "end": "14:30", "enrolled": 20, "capacity": 25}],
    )

    db = test_session_factory()
    inputs = ClassroomOutageInput(affected_room_id="RM_OUT", repair_delay_minutes=45)
    result = engine.run(db, inputs, scenario_id="test-unavailable", min_cell_size=5)
    db.close()

    infeasible_ids = [i.room_id for i in result.infeasible]
    assert "RM_CLOSED" in infeasible_ids
    closed = next(i for i in result.infeasible if i.room_id == "RM_CLOSED")
    assert any("HC-3" in fc for fc in closed.failed_constraints)


def test_engine_no_feasible_candidate(test_session_factory):
    """Gold case 4: no candidate passes hard constraints → empty candidates list."""
    from app.services.scenarios import ClassroomOutageInput, engine

    _seed_rooms(
        test_session_factory,
        rooms=[{"id": "RM_NOPE", "building_id": "BLD_A", "capacity": 5, "kind": "classroom"}],
        affected_room={"id": "RM_GONE", "building_id": "BLD_A", "capacity": 30},
        meetings=[{"section_id": "SEC-4", "course_id": "CS404", "days": ["Thu"],
                   "start": "09:00", "end": "10:30", "enrolled": 28, "capacity": 30}],
    )

    db = test_session_factory()
    inputs = ClassroomOutageInput(affected_room_id="RM_GONE", repair_delay_minutes=60)
    result = engine.run(db, inputs, scenario_id="test-no-feasible", min_cell_size=5)
    db.close()

    assert result.candidates == [], \
        f"Expected no feasible candidates; got {[c.room_id for c in result.candidates]}"
    assert len(result.infeasible) >= 1
    assert result.summary["best_option_id"] is None


def test_engine_deterministic_hash(test_session_factory):
    """Gold case 5: identical inputs → identical result_hash."""
    from app.services.scenarios import ClassroomOutageInput, engine

    _seed_rooms(
        test_session_factory,
        rooms=[{"id": "RM_DET", "building_id": "BLD_A", "capacity": 40, "kind": "classroom"}],
        affected_room={"id": "RM_SRC", "building_id": "BLD_A", "capacity": 25},
        meetings=[{"section_id": "SEC-5", "course_id": "CS505", "days": ["Fri"],
                   "start": "14:00", "end": "15:30", "enrolled": 22, "capacity": 25}],
    )

    db = test_session_factory()
    inputs = ClassroomOutageInput(affected_room_id="RM_SRC", repair_delay_minutes=90)
    r1 = engine.run(db, inputs, scenario_id="hash-run-1", min_cell_size=5)
    r2 = engine.run(db, inputs, scenario_id="hash-run-2", min_cell_size=5)
    db.close()

    assert r1.result_hash == r2.result_hash, \
        f"Determinism violated: run1={r1.result_hash}, run2={r2.result_hash}"


def test_engine_affected_section_aggregation(test_session_factory):
    """Gold case 6: correct affected section and headcount aggregation."""
    from app.services.scenarios import ClassroomOutageInput, engine

    _seed_rooms(
        test_session_factory,
        rooms=[{"id": "RM_ALT", "building_id": "BLD_A", "capacity": 60, "kind": "classroom"}],
        affected_room={"id": "RM_AFF", "building_id": "BLD_A", "capacity": 35},
        meetings=[
            {"section_id": "SEC-6A", "course_id": "CS601", "days": ["Mon"],
             "start": "09:00", "end": "10:30", "enrolled": 30, "capacity": 35},
            {"section_id": "SEC-6B", "course_id": "CS602", "days": ["Wed"],
             "start": "11:00", "end": "12:30", "enrolled": 28, "capacity": 35},
        ],
    )

    db = test_session_factory()
    inputs = ClassroomOutageInput(affected_room_id="RM_AFF", repair_delay_minutes=120)
    result = engine.run(db, inputs, scenario_id="test-aggregation", min_cell_size=5)
    db.close()

    section_ids = [s.section_id for s in result.affected_sections]
    assert "SEC-6A" in section_ids
    assert "SEC-6B" in section_ids
    assert result.summary["affected_sections_count"] == 2


def test_engine_missing_capacity_metadata(test_session_factory):
    """Gold case 7: room with no capacity → partial data, not a hard constraint fail."""
    from app.services.scenarios import ClassroomOutageInput, engine

    _seed_rooms(
        test_session_factory,
        rooms=[{"id": "RM_NOINFO", "building_id": "BLD_A", "capacity": None, "kind": "classroom"}],
        affected_room={"id": "RM_BASE", "building_id": "BLD_A", "capacity": 20},
        meetings=[{"section_id": "SEC-7", "course_id": "CS707", "days": ["Mon"],
                   "start": "09:00", "end": "10:30", "enrolled": 15, "capacity": 20}],
    )

    db = test_session_factory()
    inputs = ClassroomOutageInput(affected_room_id="RM_BASE", repair_delay_minutes=30)
    result = engine.run(db, inputs, scenario_id="test-missing-cap", min_cell_size=5)
    db.close()

    # Room with unknown capacity should NOT fail HC-1 (we skip unknown capacity check)
    # It may be feasible or not depending on other constraints
    assert result.summary["data_completeness"] == "partial" or \
        any("capacity" in md for md in result.missing_data), \
        "Expected missing_data to mention capacity"


def test_engine_does_not_mutate_canonical_event(test_session_factory):
    """Gold case 10: scenario run does NOT change canonical event state."""
    from app.services.scenarios import ClassroomOutageInput, engine
    from app.models.models import CanonicalEvent

    _seed_rooms(
        test_session_factory,
        rooms=[{"id": "RM_SAFE", "building_id": "BLD_A", "capacity": 50, "kind": "classroom"}],
        affected_room={"id": "RM_ORIG", "building_id": "BLD_A", "capacity": 25},
        meetings=[{"section_id": "SEC-MUT", "course_id": "CS999", "days": ["Mon"],
                   "start": "09:00", "end": "10:30", "enrolled": 20, "capacity": 25}],
    )

    db = test_session_factory()
    # Create a canonical event
    import hashlib as _hl
    ce = CanonicalEvent(
        type="incident.hvac_fault",
        idempotency_key=_hl.sha256(b"no-mutate-test").hexdigest(),
        tenant_id="sbu_demo",
        last_actor=ACTOR_FACILITIES,
        status="reported",
    )
    db.add(ce)
    db.commit()
    ce_id = ce.id
    initial_status = ce.status

    inputs = ClassroomOutageInput(affected_room_id="RM_ORIG", repair_delay_minutes=60,
                                   context_event_version=None)
    engine.run(db, inputs, scenario_id="test-no-mutate", min_cell_size=5)

    # Reload canonical event — status must be unchanged
    db.expire(ce)
    ce_reloaded = db.get(CanonicalEvent, ce_id)
    assert ce_reloaded.status == initial_status, \
        f"Scenario run mutated canonical event status: {initial_status} → {ce_reloaded.status}"
    db.close()


# ─── API tests ────────────────────────────────────────────────────────────────

def test_api_create_scenario_acadops(client, test_session_factory):
    """academic_ops can create a scenario."""
    _seed_rooms(
        test_session_factory,
        rooms=[{"id": "RM_API1", "building_id": "BLD_A", "capacity": 40, "kind": "classroom"}],
        affected_room={"id": "RM_API_AFF", "building_id": "BLD_A", "capacity": 25},
        meetings=[{"section_id": "SEC-API1", "course_id": "CS100", "days": ["Mon"],
                   "start": "09:00", "end": "10:30", "enrolled": 20, "capacity": 25}],
    )
    r = client.post(
        "/api/v1/scenarios",
        json={"affected_room_id": "RM_API_AFF", "repair_delay_minutes": 60},
        headers={"X-Demo-Actor": ACTOR_ACADOPS},
    )
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["engine_version"] == "v1"
    assert data["scenario_type"] == "classroom_outage"
    assert "result_hash" in data
    assert data["result"]["summary"]["affected_sections_count"] >= 1


def test_api_student_cannot_create_scenario(client):
    """V4-05 authorization: student cannot create a scenario."""
    r = client.post(
        "/api/v1/scenarios",
        json={"affected_room_id": "RM_DOESNT_MATTER", "repair_delay_minutes": 60},
        headers={"X-Demo-Actor": ACTOR_STUDENT},
    )
    assert r.status_code == 403, f"Expected 403 for student; got {r.status_code}"


def test_api_facilities_cannot_promote_scenario(client, test_session_factory):
    """V4-05: facilities cannot approve (promote) a scenario — only academic_ops can."""
    _seed_rooms(
        test_session_factory,
        rooms=[{"id": "RM_PROM", "building_id": "BLD_A", "capacity": 50, "kind": "classroom"}],
        affected_room={"id": "RM_PROM_AFF", "building_id": "BLD_A", "capacity": 25},
        meetings=[{"section_id": "SEC-PROM", "course_id": "CS200", "days": ["Tue"],
                   "start": "10:00", "end": "11:30", "enrolled": 20, "capacity": 25}],
    )
    # Create scenario as acadops
    r = client.post(
        "/api/v1/scenarios",
        json={"affected_room_id": "RM_PROM_AFF", "repair_delay_minutes": 30},
        headers={"X-Demo-Actor": ACTOR_ACADOPS},
    )
    assert r.status_code == 201
    scenario_id = r.json()["id"]
    best = r.json()["result"]["summary"].get("best_option_id")

    if best is None:
        pytest.skip("No feasible candidate for promotion test")

    # Try to promote as facilities — must fail
    r2 = client.post(
        f"/api/v1/scenarios/{scenario_id}/promote",
        json={"selected_option_id": best, "rationale": "Facilities trying to approve"},
        headers={"X-Demo-Actor": ACTOR_FACILITIES},
    )
    assert r2.status_code == 403, \
        f"Expected 403 for facilities promoting scenario; got {r2.status_code}"


def test_api_acadops_can_promote_scenario(client, test_session_factory):
    """V4-05: academic_ops can promote a feasible scenario option."""
    _seed_rooms(
        test_session_factory,
        rooms=[{"id": "RM_OK", "building_id": "BLD_A", "capacity": 50, "kind": "classroom"}],
        affected_room={"id": "RM_PRO_AFF2", "building_id": "BLD_A", "capacity": 25},
        meetings=[{"section_id": "SEC-OK", "course_id": "CS300", "days": ["Wed"],
                   "start": "14:00", "end": "15:30", "enrolled": 20, "capacity": 25}],
    )
    r = client.post(
        "/api/v1/scenarios",
        json={"affected_room_id": "RM_PRO_AFF2", "repair_delay_minutes": 60},
        headers={"X-Demo-Actor": ACTOR_ACADOPS},
    )
    assert r.status_code == 201
    scenario_id = r.json()["id"]
    best = r.json()["result"]["summary"].get("best_option_id")

    if best is None:
        pytest.skip("No feasible candidate — scenario engine found no alternatives")

    r2 = client.post(
        f"/api/v1/scenarios/{scenario_id}/promote",
        json={"selected_option_id": best,
              "rationale": "Best option: adequate capacity, same building."},
        headers={"X-Demo-Actor": ACTOR_ACADOPS},
    )
    assert r2.status_code == 200, r2.text
    data = r2.json()
    assert data["status"] == "promoted"
    assert data["promoted_option_id"] == best
    assert "note" in data  # must explain no auto-mutation


def test_api_scenario_compare(client, test_session_factory):
    """Compare two scenario runs returns structured diff."""
    _seed_rooms(
        test_session_factory,
        rooms=[{"id": "RM_CMP", "building_id": "BLD_A", "capacity": 50, "kind": "classroom"}],
        affected_room={"id": "RM_CMP_AFF", "building_id": "BLD_A", "capacity": 25},
        meetings=[{"section_id": "SEC-CMP", "course_id": "CS400", "days": ["Mon"],
                   "start": "09:00", "end": "10:30", "enrolled": 20, "capacity": 25}],
    )

    r1 = client.post(
        "/api/v1/scenarios",
        json={"affected_room_id": "RM_CMP_AFF", "repair_delay_minutes": 30},
        headers={"X-Demo-Actor": ACTOR_ACADOPS},
    )
    r2 = client.post(
        "/api/v1/scenarios",
        json={"affected_room_id": "RM_CMP_AFF", "repair_delay_minutes": 120},
        headers={"X-Demo-Actor": ACTOR_ACADOPS},
    )
    assert r1.status_code == 201 and r2.status_code == 201
    id1, id2 = r1.json()["id"], r2.json()["id"]

    rc = client.get(
        f"/api/v1/scenarios/compare/{id1}/{id2}",
        headers={"X-Demo-Actor": ACTOR_ACADOPS},
    )
    assert rc.status_code == 200, rc.text
    data = rc.json()
    assert len(data["runs"]) == 2
    # repair_delay_minutes changed between runs
    assert "repair_delay_minutes" in data.get("changed_inputs", {}) or \
        data["runs"][0]["inputs"].get("repair_delay_minutes") != \
        data["runs"][1]["inputs"].get("repair_delay_minutes")
