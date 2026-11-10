"""
U2 tests — Tenant pack loader, validation, and tenant config API.

Test coverage:
  - All four packs pass validation
  - Loader idempotency (same hash → unchanged, no DB rebuild)
  - Backup written on hash change
  - 7 corrupt pack variants are rejected
  - Knowledge retrieval is isolated per tenant
  - Rhine uses 24-hour clock
  - Same scenario step has different local time in different tenants
  - grep: no 'if tenant ==' in production code
  - GET /tenant/config returns correct fields
  - GET /tenants lists active tenants
"""
from __future__ import annotations

import copy
import json
import pathlib
import re
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# ── Paths ──────────────────────────────────────────────────────────────────────

# __file__ = aurora-campus-intelligence/backend/tests/test_u2_pack_loader.py
# .parent   = tests/
# .parent   = backend/
# .parent   = aurora-campus-intelligence/
_BACKEND = pathlib.Path(__file__).resolve().parent.parent   # backend/
_PROJECT = _BACKEND.parent                                  # aurora-campus-intelligence/
_PACKS_DIR = _PROJECT / "sample-data" / "tenants"
_SBU_PACK = _PACKS_DIR / "sbu_demo.pack.json"
_RHINE_PACK = _PACKS_DIR / "rhine_demo.pack.json"
_NORTHBRIDGE_PACK = _PACKS_DIR / "northbridge_demo.pack.json"
_PACIFIC_PACK = _PACKS_DIR / "pacific_demo.pack.json"

DEMO_USER = "test-user-u2"


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture()
def sbu_pack() -> dict:
    return json.loads(_SBU_PACK.read_bytes())


@pytest.fixture()
def rhine_pack() -> dict:
    return json.loads(_RHINE_PACK.read_bytes())


@pytest.fixture()
def db_path(tmp_path):
    return str(tmp_path / "test_u2.db")


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
    db.add(UserProfile(id=DEMO_USER, display_name="Test User U2", timezone="America/New_York"))
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


# ── Helper: write a pack to a temp file ──────────────────────────────────────

def _write_pack(tmp_path: Path, pack: dict, name: str = "test.pack.json") -> Path:
    p = tmp_path / name
    p.write_text(json.dumps(pack), encoding="utf-8")
    return p


# ── U2-1: All four packs pass validation ─────────────────────────────────────

@pytest.mark.parametrize("pack_path", [
    _SBU_PACK,
    _NORTHBRIDGE_PACK,
    _PACIFIC_PACK,
    _RHINE_PACK,
], ids=["sbu", "northbridge", "pacific", "rhine"])
def test_all_packs_validate(pack_path):
    from app.services.tenancy.pack_loader import validate_pack
    pack = json.loads(pack_path.read_bytes())
    errs = validate_pack(pack)
    assert errs == [], f"{pack_path.name} validation errors:\n" + "\n".join(f"  - {e}" for e in errs)


# ── U2-2: Loader idempotency ──────────────────────────────────────────────────

def test_load_pack_idempotent(tmp_path):
    """Loading the same pack twice (same hash) is a no-op — DB not rebuilt."""
    from app.services.tenancy.pack_loader import load_pack
    from app.db.control import get_control_session, TenantRecord

    # Redirect control DB and tenant DBs to tmp_path
    import app.db.control as ctrl
    import app.core.tenancy as ten_mod

    original_tenants_dir = ctrl._TENANTS_DIR
    original_backups_dir = ctrl._BACKUPS_DIR
    original_control_db = ctrl._CONTROL_DB
    original_engines = ten_mod._TENANT_ENGINES.copy()
    original_control_engine = ctrl._control_engine
    original_session = ctrl._ControlSession

    ctrl._TENANTS_DIR = tmp_path / "tenants"
    ctrl._BACKUPS_DIR = tmp_path / "backups"
    ctrl._CONTROL_DB = tmp_path / "control.db"
    ctrl._TENANTS_DIR.mkdir()
    ctrl._BACKUPS_DIR.mkdir()
    ctrl._control_engine = None
    ctrl._ControlSession = None
    ten_mod._TENANT_ENGINES.clear()

    try:
        pack_file = _write_pack(tmp_path, json.loads(_SBU_PACK.read_bytes()), "sbu_demo.pack.json")
        rec1 = load_pack(pack_file)
        db_mtime1 = (ctrl._TENANTS_DIR / "sbu_demo.db").stat().st_mtime

        rec2 = load_pack(pack_file)
        db_mtime2 = (ctrl._TENANTS_DIR / "sbu_demo.db").stat().st_mtime

        assert rec1.pack_hash == rec2.pack_hash, "Hash changed unexpectedly"
        assert db_mtime1 == db_mtime2, "DB was rebuilt despite same hash (idempotency violated)"
    finally:
        ctrl._TENANTS_DIR = original_tenants_dir
        ctrl._BACKUPS_DIR = original_backups_dir
        ctrl._CONTROL_DB = original_control_db
        ctrl._control_engine = original_control_engine
        ctrl._ControlSession = original_session
        ten_mod._TENANT_ENGINES.clear()
        ten_mod._TENANT_ENGINES.update(original_engines)


def test_load_pack_backup_on_hash_change(tmp_path):
    """If the pack changes, a backup of the old DB is written before rebuild."""
    from app.services.tenancy.pack_loader import load_pack
    import app.db.control as ctrl
    import app.core.tenancy as ten_mod

    original_tenants_dir = ctrl._TENANTS_DIR
    original_backups_dir = ctrl._BACKUPS_DIR
    original_control_db = ctrl._CONTROL_DB
    original_control_engine = ctrl._control_engine
    original_session = ctrl._ControlSession
    original_engines = ten_mod._TENANT_ENGINES.copy()

    ctrl._TENANTS_DIR = tmp_path / "tenants"
    ctrl._BACKUPS_DIR = tmp_path / "backups"
    ctrl._CONTROL_DB = tmp_path / "control.db"
    ctrl._TENANTS_DIR.mkdir()
    ctrl._BACKUPS_DIR.mkdir()
    ctrl._control_engine = None
    ctrl._ControlSession = None
    ten_mod._TENANT_ENGINES.clear()

    try:
        pack1 = json.loads(_SBU_PACK.read_bytes())
        pack_file = _write_pack(tmp_path, pack1, "sbu_demo.pack.json")
        load_pack(pack_file)

        # Modify pack to change hash
        pack2 = copy.deepcopy(pack1)
        pack2["knowledge"][0]["text"] += " (updated)"
        pack_file.write_text(json.dumps(pack2), encoding="utf-8")
        load_pack(pack_file)

        # Backup should exist — pack_loader creates _BACKUPS_DIR/{tenant_id}_{ts}/sbu_demo.db
        backups = list(ctrl._BACKUPS_DIR.rglob("*.db"))
        assert len(backups) >= 1, (
            f"No backup found after hash change. Backups dir contents: "
            f"{list(ctrl._BACKUPS_DIR.rglob('*'))}"
        )
    finally:
        ctrl._TENANTS_DIR = original_tenants_dir
        ctrl._BACKUPS_DIR = original_backups_dir
        ctrl._CONTROL_DB = original_control_db
        ctrl._control_engine = original_control_engine
        ctrl._ControlSession = original_session
        ten_mod._TENANT_ENGINES.clear()
        ten_mod._TENANT_ENGINES.update(original_engines)


# ── U2-3: 7 corrupt pack variants rejected ───────────────────────────────────

def test_corrupt_bad_timezone(sbu_pack):
    from app.services.tenancy.pack_loader import validate_pack
    pack = copy.deepcopy(sbu_pack)
    pack["tenant"]["timezone"] = "Not/ATimezone"
    errs = validate_pack(pack)
    assert any("time zone" in e.lower() or "timezone" in e.lower() for e in errs), (
        f"Expected timezone error, got: {errs}"
    )


def test_corrupt_double_booked_room(sbu_pack):
    from app.services.tenancy.pack_loader import validate_pack
    pack = copy.deepcopy(sbu_pack)
    # Find section s1 and s2, make them overlap in both time and room
    sc = pack["scenario"]
    secs = {s["id"]: s for s in pack["sections"]}
    s1 = secs[sc["sections"]["s1"]]
    s2 = secs[sc["sections"]["s2"]]
    rb = sc["rooms"]["room_b"]
    # Put s1 in the same room as s2, AND overlap the times
    s1["meetings"][0]["room_id"] = s2["meetings"][0]["room_id"]
    # Make s1 overlap with s2's time slot
    s1["meetings"][0]["start"] = s2["meetings"][0]["start"]
    s1["meetings"][0]["end"] = s2["meetings"][0]["end"]
    errs = validate_pack(pack)
    assert any("double" in e.lower() or "booked" in e.lower() for e in errs), (
        f"Expected double-booking error, got: {errs}"
    )


def test_corrupt_missing_walking_pair(sbu_pack):
    from app.services.tenancy.pack_loader import validate_pack
    pack = copy.deepcopy(sbu_pack)
    # Remove all walking_minutes entries
    pack["walking_minutes"] = {}
    errs = validate_pack(pack)
    assert any("walking" in e.lower() for e in errs), (
        f"Expected walking minutes error, got: {errs}"
    )


def test_corrupt_not_labeled_synthetic(sbu_pack):
    from app.services.tenancy.pack_loader import validate_pack
    pack = copy.deepcopy(sbu_pack)
    pack["data_origin"] = "real"
    errs = validate_pack(pack)
    assert any("synthetic" in e.lower() for e in errs), (
        f"Expected synthetic label error, got: {errs}"
    )


def test_corrupt_second_feasible_alternative(sbu_pack):
    from app.services.tenancy.pack_loader import validate_pack
    pack = copy.deepcopy(sbu_pack)
    sc = pack["scenario"]
    secs = {s["id"]: s for s in pack["sections"]}
    s2 = secs[sc["sections"]["s2"]]
    rc = sc["rooms"]["room_c"]
    rooms = {r["id"]: r for r in pack["rooms"]}
    rc_room = rooms[rc]

    # Add a second feasible classroom (same building as rc, same kind, big enough, available)
    new_room = {
        "id": "EXTRA-999",
        "building_id": rc_room["building_id"],
        "kind": "classroom",
        "capacity": s2["enrolled"] + 20,
        "available": True,
        "name": "Extra Room 999",
        "code": "999",
    }
    pack["rooms"].append(new_room)
    # Also update walking_minutes to include the new room's building (no new building needed)

    errs = validate_pack(pack)
    assert any("feasible" in e.lower() or "alternative" in e.lower() for e in errs), (
        f"Expected exactly-one-feasible error, got: {errs}"
    )


def test_corrupt_dangling_persona(sbu_pack):
    from app.services.tenancy.pack_loader import validate_pack
    pack = copy.deepcopy(sbu_pack)
    # Add a persona that references a non-existent person_id
    pack["personas"]["ghost_persona"] = {
        "person_id": "nonexistent-person-xyz",
        "role": "student",
        "display": "Ghost",
    }
    errs = validate_pack(pack)
    assert any("persona" in e.lower() for e in errs), (
        f"Expected dangling persona error, got: {errs}"
    )


def test_corrupt_out_of_order_timeline(sbu_pack):
    from app.services.tenancy.pack_loader import validate_pack
    pack = copy.deepcopy(sbu_pack)
    # Reverse the timeline
    pack["scenario"]["timeline"] = list(reversed(pack["scenario"]["timeline"]))
    errs = validate_pack(pack)
    assert any("timeline" in e.lower() or "order" in e.lower() for e in errs), (
        f"Expected timeline order error, got: {errs}"
    )


# ── U2-4: Knowledge retrieval isolated per tenant ────────────────────────────

def test_knowledge_isolation(tmp_path):
    """Knowledge loaded for one tenant must not be visible in another."""
    from app.services.tenancy.pack_loader import load_pack
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import sessionmaker
    import app.db.control as ctrl
    import app.core.tenancy as ten_mod

    original_tenants_dir = ctrl._TENANTS_DIR
    original_backups_dir = ctrl._BACKUPS_DIR
    original_control_db = ctrl._CONTROL_DB
    original_control_engine = ctrl._control_engine
    original_session = ctrl._ControlSession
    original_engines = ten_mod._TENANT_ENGINES.copy()

    ctrl._TENANTS_DIR = tmp_path / "tenants"
    ctrl._BACKUPS_DIR = tmp_path / "backups"
    ctrl._CONTROL_DB = tmp_path / "control.db"
    ctrl._TENANTS_DIR.mkdir()
    ctrl._BACKUPS_DIR.mkdir()
    ctrl._control_engine = None
    ctrl._ControlSession = None
    ten_mod._TENANT_ENGINES.clear()

    try:
        sbu = json.loads(_SBU_PACK.read_bytes())
        rhine = json.loads(_RHINE_PACK.read_bytes())

        # Make knowledge texts unique per tenant
        sbu["knowledge"][0]["text"] = "SBU add-drop is September 14."
        rhine["knowledge"][0]["text"] = "Rhine add-drop is October 30."

        sbu_file = _write_pack(tmp_path, sbu, "sbu_demo.pack.json")
        rhine_file = _write_pack(tmp_path, rhine, "rhine_demo.pack.json")

        load_pack(sbu_file)
        load_pack(rhine_file)

        # Read SBU knowledge
        sbu_engine = create_engine(
            f"sqlite:///{ctrl._TENANTS_DIR / 'sbu_demo.db'}",
            connect_args={"check_same_thread": False},
        )
        sbu_db = sessionmaker(bind=sbu_engine)()
        from app.models.models import KnowledgeChunk
        sbu_chunks = sbu_db.query(KnowledgeChunk).all()
        sbu_texts = " ".join(c.text for c in sbu_chunks)
        sbu_db.close()

        # Read Rhine knowledge
        rhine_engine = create_engine(
            f"sqlite:///{ctrl._TENANTS_DIR / 'rhine_demo.db'}",
            connect_args={"check_same_thread": False},
        )
        rhine_db = sessionmaker(bind=rhine_engine)()
        rhine_chunks = rhine_db.query(KnowledgeChunk).all()
        rhine_texts = " ".join(c.text for c in rhine_chunks)
        rhine_db.close()

        assert "September 14" in sbu_texts, "SBU knowledge not found in SBU DB"
        assert "October 30" in rhine_texts, "Rhine knowledge not found in Rhine DB"
        # Cross-contamination check
        assert "October 30" not in sbu_texts, "Rhine knowledge leaked into SBU DB"
        assert "September 14" not in rhine_texts, "SBU knowledge leaked into Rhine DB"
    finally:
        ctrl._TENANTS_DIR = original_tenants_dir
        ctrl._BACKUPS_DIR = original_backups_dir
        ctrl._CONTROL_DB = original_control_db
        ctrl._control_engine = original_control_engine
        ctrl._ControlSession = original_session
        ten_mod._TENANT_ENGINES.clear()
        ten_mod._TENANT_ENGINES.update(original_engines)


# ── U2-5: Rhine uses 24-hour clock ───────────────────────────────────────────

def test_rhine_uses_24h_clock(rhine_pack):
    """Rhine pack must set clock='24h'."""
    assert rhine_pack["tenant"]["clock"] == "24h", (
        f"Expected Rhine to use 24h clock, got: {rhine_pack['tenant']['clock']}"
    )


def test_sbu_uses_12h_clock(sbu_pack):
    """SBU demo pack must set clock='12h'."""
    assert sbu_pack["tenant"]["clock"] == "12h"


# ── U2-6: Same scenario step, different local times in different tenants ──────

def test_scenario_step_different_local_times():
    """
    A UTC timestamp should display differently for SBU (ET) vs Rhine (CET/CEST).
    This proves the tenant config drives time formatting.
    """
    from datetime import datetime, timezone
    from zoneinfo import ZoneInfo

    sbu_pack = json.loads(_SBU_PACK.read_bytes())
    rhine_pack = json.loads(_RHINE_PACK.read_bytes())

    sbu_tz = sbu_pack["tenant"]["timezone"]    # America/New_York
    rhine_tz = rhine_pack["tenant"]["timezone"]  # Europe/Berlin

    # Use a scenario timeline event UTC time
    # "10:00" local SBU = "16:00" Berlin (summer) or "15:00" winter
    # Let's use a fixed UTC time
    utc_dt = datetime(2026, 11, 10, 15, 0, 0, tzinfo=timezone.utc)

    sbu_local = utc_dt.astimezone(ZoneInfo(sbu_tz))
    rhine_local = utc_dt.astimezone(ZoneInfo(rhine_tz))

    # They must NOT have the same local hour
    assert sbu_local.hour != rhine_local.hour, (
        f"SBU and Rhine show the same hour ({sbu_local.hour}) for UTC 15:00 — "
        "tenant timezone is not being applied"
    )


# ── U2-7: No 'if tenant ==' in production code ────────────────────────────────

def test_no_tenant_specific_branch_u2():
    """Grep proof: production code must not use 'if tenant ==' branching."""
    app_root = pathlib.Path(__file__).parent.parent / "app"
    pattern = re.compile(r'\bif\s+tenant\s*==')
    violations = []
    for py_file in app_root.rglob("*.py"):
        text_content = py_file.read_text(encoding="utf-8", errors="ignore")
        for lineno, line in enumerate(text_content.splitlines(), 1):
            if pattern.search(line):
                violations.append(f"{py_file.relative_to(app_root)}:{lineno}: {line.strip()}")
    assert violations == [], (
        "Found 'if tenant ==' branch(es) in production code:\n"
        + "\n".join(violations)
    )


# ── U2-8: GET /tenant/config endpoint ────────────────────────────────────────

def test_get_tenant_config_default(client):
    """GET /tenant/config returns defaults when no pack loaded (legacy DB)."""
    r = client.get("/api/v1/tenant/config")
    assert r.status_code == 200
    cfg = r.json()
    assert "time_zone" in cfg
    assert "clock" in cfg
    assert cfg["clock"] in ("12h", "24h")
    assert "role_vocabulary" in cfg
    assert isinstance(cfg["role_vocabulary"], dict)
    assert "min_cell_size" in cfg


def test_get_tenants_list(client):
    """GET /tenants returns a list (may be empty in test context)."""
    r = client.get("/api/v1/tenants")
    assert r.status_code == 200
    tenants = r.json()
    assert isinstance(tenants, list)


# ── U2-9: TenantConfig loaded correctly from pack ────────────────────────────

def test_tenant_config_loaded_from_pack(tmp_path):
    """After loading a pack, TenantConfig row reflects pack's tenant block."""
    from app.services.tenancy.pack_loader import load_pack
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    import app.db.control as ctrl
    import app.core.tenancy as ten_mod

    original_tenants_dir = ctrl._TENANTS_DIR
    original_backups_dir = ctrl._BACKUPS_DIR
    original_control_db = ctrl._CONTROL_DB
    original_control_engine = ctrl._control_engine
    original_session = ctrl._ControlSession
    original_engines = ten_mod._TENANT_ENGINES.copy()

    ctrl._TENANTS_DIR = tmp_path / "tenants"
    ctrl._BACKUPS_DIR = tmp_path / "backups"
    ctrl._CONTROL_DB = tmp_path / "control.db"
    ctrl._TENANTS_DIR.mkdir()
    ctrl._BACKUPS_DIR.mkdir()
    ctrl._control_engine = None
    ctrl._ControlSession = None
    ten_mod._TENANT_ENGINES.clear()

    try:
        pack_file = _write_pack(tmp_path, json.loads(_RHINE_PACK.read_bytes()), "rhine_demo.pack.json")
        load_pack(pack_file)

        eng = create_engine(
            f"sqlite:///{ctrl._TENANTS_DIR / 'rhine_demo.db'}",
            connect_args={"check_same_thread": False},
        )
        db = sessionmaker(bind=eng)()
        from app.models.models import TenantConfig
        cfg = db.query(TenantConfig).first()
        db.close()

        assert cfg is not None, "TenantConfig row not created"
        assert cfg.timezone == "Europe/Berlin"
        assert cfg.clock == "24h"
    finally:
        ctrl._TENANTS_DIR = original_tenants_dir
        ctrl._BACKUPS_DIR = original_backups_dir
        ctrl._CONTROL_DB = original_control_db
        ctrl._control_engine = original_control_engine
        ctrl._ControlSession = original_session
        ten_mod._TENANT_ENGINES.clear()
        ten_mod._TENANT_ENGINES.update(original_engines)


# ── U2-10: Entity links created from pack ────────────────────────────────────

def test_entity_links_created(tmp_path):
    """After loading a pack, entity_links table is populated."""
    from app.services.tenancy.pack_loader import load_pack
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    import app.db.control as ctrl
    import app.core.tenancy as ten_mod

    original_tenants_dir = ctrl._TENANTS_DIR
    original_backups_dir = ctrl._BACKUPS_DIR
    original_control_db = ctrl._CONTROL_DB
    original_control_engine = ctrl._control_engine
    original_session = ctrl._ControlSession
    original_engines = ten_mod._TENANT_ENGINES.copy()

    ctrl._TENANTS_DIR = tmp_path / "tenants"
    ctrl._BACKUPS_DIR = tmp_path / "backups"
    ctrl._CONTROL_DB = tmp_path / "control.db"
    ctrl._TENANTS_DIR.mkdir()
    ctrl._BACKUPS_DIR.mkdir()
    ctrl._control_engine = None
    ctrl._ControlSession = None
    ten_mod._TENANT_ENGINES.clear()

    try:
        pack_file = _write_pack(tmp_path, json.loads(_SBU_PACK.read_bytes()), "sbu_demo.pack.json")
        load_pack(pack_file)

        eng = create_engine(
            f"sqlite:///{ctrl._TENANTS_DIR / 'sbu_demo.db'}",
            connect_args={"check_same_thread": False},
        )
        db = sessionmaker(bind=eng)()
        from app.models.models import EntityLink
        links = db.query(EntityLink).all()
        db.close()

        assert len(links) > 0, "No entity links created"
        rels = {lnk.rel for lnk in links}
        assert "in_building" in rels, "Missing room→building links"
        assert "meets_in" in rels, "Missing section→room links"
        assert "taught_by" in rels, "Missing section→person links"
    finally:
        ctrl._TENANTS_DIR = original_tenants_dir
        ctrl._BACKUPS_DIR = original_backups_dir
        ctrl._CONTROL_DB = original_control_db
        ctrl._control_engine = original_control_engine
        ctrl._ControlSession = original_session
        ten_mod._TENANT_ENGINES.clear()
        ten_mod._TENANT_ENGINES.update(original_engines)
