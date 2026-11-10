"""Tenant pack loader — U2.

validate_pack(pack)  → list[str]   (same rules as tools/validate_tenant_pack.py)
load_pack(path, force=False) → TenantRecord

Idempotency: if the pack hash is unchanged, load_pack is a no-op.
If the hash differs, the old tenant DB is backed up and fully rebuilt.
Never silently drops data.
"""
from __future__ import annotations

import hashlib
import itertools
import json
import shutil
import datetime as dt
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session

from app.db.control import (
    TenantRecord,
    get_control_session,
    tenant_db_path,
    _ensure_dirs,
)
from app.models.models import (
    Base,
    EntityLink,
    KnowledgeChunk,
    KnowledgeDocument,
    Person,
    RoleAssignment,
    Team,
    TeamMembership,
    TenantConfig,
)


# ── Validation ─────────────────────────────────────────────────────────────────

def _hm(s: str) -> int:
    h, m = s.split(":")
    return int(h) * 60 + int(m)


def validate_pack(pack: dict) -> list[str]:
    """Return a list of validation error strings (empty = valid)."""
    from zoneinfo import ZoneInfo

    errs: list[str] = []

    def need(cond: bool, msg: str) -> None:
        if not cond:
            errs.append(msg)

    t = pack.get("tenant", {})

    # Time zone
    try:
        ZoneInfo(t["timezone"])
    except Exception:
        errs.append(f"invalid time zone {t.get('timezone')}")

    # Data origin labels
    need(
        pack.get("data_origin") == "synthetic" and t.get("data_origin") == "synthetic",
        "pack and tenant must be labeled synthetic",
    )
    need(t.get("week_start") in ("sunday", "monday"), "week_start must be 'sunday' or 'monday'")

    # Unique ID helpers
    def ids(key: str, rows: list) -> set:
        seen = [r["id"] for r in rows]
        need(len(seen) == len(set(seen)), f"duplicate ids in {key}")
        return set(seen)

    B = ids("buildings", pack.get("buildings", []))
    R = ids("rooms", pack.get("rooms", []))
    D = ids("departments", pack.get("departments", []))
    C = ids("courses", pack.get("courses", []))
    S = ids("sections", pack.get("sections", []))
    ids("services", pack.get("services", []))
    ids("assets", pack.get("assets", []))
    ids("teams", pack.get("teams", []))
    ids("orgs", pack.get("orgs", []))
    ids("events", pack.get("campus_events", []))
    ids("knowledge", pack.get("knowledge", []))

    ppl = pack.get("people", {})
    fac = ids("faculty", ppl.get("faculty", []))
    stu = ids("students", ppl.get("students", []))
    stf = ids("staff", ppl.get("staff", []))

    SV = {s["id"] for s in pack.get("services", [])}
    T = {x["id"] for x in pack.get("teams", [])}
    O = {x["id"] for x in pack.get("orgs", [])}

    # Walking matrix
    for a, b in itertools.combinations(sorted(B), 2):
        need(
            f"{a}-{b}" in pack.get("walking_minutes", {})
            or f"{b}-{a}" in pack.get("walking_minutes", {}),
            f"walking minutes missing {a}-{b}",
        )
    need(
        all(isinstance(v, int) and 1 <= v <= 30 for v in pack.get("walking_minutes", {}).values()),
        "walking minutes must be integers 1-30",
    )

    rooms = {r["id"]: r for r in pack.get("rooms", [])}
    need(all(r["building_id"] in B for r in rooms.values()), "room.building_id")
    need(all(c["dept_id"] in D for c in pack.get("courses", [])), "course.dept_id")

    # Sections
    for s in pack.get("sections", []):
        need(s["course_id"] in C, f"section {s['id']} course")
        need(s["instructor_id"] in fac, f"section {s['id']} instructor")
        need(s["enrolled"] <= s["capacity"], f"section {s['id']} enrolled > capacity")
        for m in s.get("meetings", []):
            need(m["room_id"] in R, f"section {s['id']} room")
            need(
                rooms[m["room_id"]]["capacity"] >= s["enrolled"],
                f"section {s['id']} exceeds room capacity",
            )
            need(_hm(m["start"]) < _hm(m["end"]), f"section {s['id']} times")
        need(all(x in stu for x in s.get("roster", [])), f"section {s['id']} roster")
        need(len(s.get("roster", [])) <= s["enrolled"], f"section {s['id']} roster larger than headcount")

    # Double booking
    meets = [
        (s["id"], s["instructor_id"], m)
        for s in pack.get("sections", [])
        for m in s.get("meetings", [])
    ]
    for (s1, i1, m1), (s2, i2, m2) in itertools.combinations(meets, 2):
        if (
            set(m1["days"]) & set(m2["days"])
            and _hm(m1["start"]) < _hm(m2["end"])
            and _hm(m2["start"]) < _hm(m1["end"])
        ):
            need(m1["room_id"] != m2["room_id"], f"room double-booked: {s1} / {s2} in {m1['room_id']}")
            need(i1 != i2, f"instructor double-booked: {s1} / {s2}")

    # Teams and services
    for tm in pack.get("teams", []):
        need(all(x in stf for x in tm.get("member_ids", [])), f"team {tm['id']} members")
        for b in tm.get("scope", {}).get("building_ids", []):
            need(b in B, f"team {tm['id']} building {b}")
        for sv in tm.get("scope", {}).get("service_ids", []):
            need(sv in SV, f"team {tm['id']} service {sv}")
    for sv in pack.get("services", []):
        need(sv["owner_team_id"] in T, f"service {sv['id']} owner")
        need(all(b in B for b in sv.get("coverage_building_ids", [])), f"service {sv['id']} coverage")

    # Personas
    allpeople = fac | stu | stf
    for k, ps in pack.get("personas", {}).items():
        need(ps["person_id"] in allpeople, f"persona {k} person")
        if "team_id" in ps:
            need(ps["team_id"] in T, f"persona {k} team")

    # Memberships
    for m in pack.get("memberships", []):
        need(m["person_id"] in allpeople, f"membership person {m['person_id']}")
        if m.get("team_id"):
            need(m["team_id"] in T, "membership team")
        if m.get("org_id"):
            need(m["org_id"] in O, "membership org")

    # Events and assets
    for ev in pack.get("campus_events", []):
        need(ev["room_id"] in R, f"event {ev['id']} room")
    for a in pack.get("assets", []):
        need(a["building_id"] in B, f"asset {a['id']} building")
        need(a["service_id"] in SV, f"asset {a['id']} service")

    need(len(pack.get("knowledge", [])) >= 8, "at least 8 knowledge documents")

    # Scenario
    sc = pack.get("scenario", {})
    secs = {s["id"]: s for s in pack.get("sections", [])}
    try:
        s1, s2, s3 = (secs[sc["sections"][k]] for k in ("s1", "s2", "s3"))
        for s in (s1, s2, s3):
            need("Tue" in s["meetings"][0]["days"], f"scenario section {s['id']} must meet on Tuesday")
        need(
            _hm(s1["meetings"][0]["end"]) < _hm(s2["meetings"][0]["start"])
            < _hm(s2["meetings"][0]["end"]) < _hm(s3["meetings"][0]["start"]),
            "scenario sections must be in time order",
        )
        ra, rb, rc = sc["rooms"]["room_a"], sc["rooms"]["room_b"], sc["rooms"]["room_c"]
        need(rooms[ra].get("available") is False, "room_a must be unavailable")
        need(rooms[rb]["building_id"] != rooms[ra]["building_id"], "room change must change building")
        need(s2["meetings"][0]["room_id"] == rb, "section s2 must be in room_b (the incident room)")

        # Exactly one feasible alternative
        st_min, en_min = _hm(s2["meetings"][0]["start"]), _hm(s2["meetings"][0]["end"])
        def _free(room_id: str) -> bool:
            return not any(
                m["room_id"] == room_id
                and "Tue" in m["days"]
                and _hm(m["start"]) < en_min
                and st_min < _hm(m["end"])
                for sec in pack.get("sections", [])
                for m in sec.get("meetings", [])
                if sec["id"] != s2["id"]
            )
        feas = [
            r["id"]
            for r in rooms.values()
            if r["kind"] == "classroom"
            and r.get("available", True)
            and r["capacity"] >= s2["enrolled"]
            and r["id"] != rb
            and _free(r["id"])
        ]
        need(feas == [rc], f"expected exactly one feasible alternative room {rc}, found {feas}")
        need(
            sc["expected"]["impact"]["headcount"] == s1["enrolled"] + s2["enrolled"],
            "expected headcount",
        )

        # Timeline order
        times = [_hm(e["at"]) for e in sc.get("timeline", [])]
        need(times == sorted(times), "timeline must be in time order")
        ev_ids = [e["id"] for e in sc.get("timeline", [])]
        need(len(ev_ids) == len(set(ev_ids)), "timeline ids")
        for e in sc.get("timeline", []):
            if e.get("actor") not in (None, "system"):
                need(e["actor"] in pack.get("personas", {}), f"timeline actor {e['actor']}")

        # Audience students exist
        for k, aud in sc["expected"]["audiences"].items():
            need(
                all(x in stu for x in aud.get("students", [])),
                f"audience {k} students",
            )

        # Wi-Fi persona differentiation
        wifi = sc["expected"]["audiences"].get("e07", {})
        need(
            len(wifi.get("not_notified", [])) >= 1 and "student_alex" in wifi.get("students", []),
            "wifi audience",
        )

        # HVAC and WiFi coverage
        need(
            any(
                a["kind"] == "hvac_unit" and a["building_id"] == rooms[rb]["building_id"]
                for a in pack.get("assets", [])
            ),
            "hvac asset in incident building",
        )
        wifi_svc = next((s for s in pack.get("services", []) if s["id"] == "svc-wifi"), None)
        if wifi_svc:
            need(
                sc["buildings"]["library"] in wifi_svc["coverage_building_ids"],
                "library in wifi zone",
            )
            need(
                rooms[rb]["building_id"] in wifi_svc["coverage_building_ids"],
                "room_b building in wifi zone (so section s2 is affected)",
            )
    except (KeyError, IndexError, TypeError) as exc:
        errs.append(f"scenario structure error: {exc}")

    return errs


# ── Pack hash ──────────────────────────────────────────────────────────────────

def _pack_hash(raw_bytes: bytes) -> str:
    return hashlib.sha256(raw_bytes).hexdigest()[:16]


# ── DB initialisation for a tenant ────────────────────────────────────────────

def _init_tenant_db(engine) -> None:
    """Create all tables and the FTS virtual table in a fresh tenant DB."""
    Base.metadata.create_all(bind=engine)
    with engine.connect() as conn:
        conn.execute(
            text(
                "CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_chunks_fts "
                "USING fts5(chunk_id UNINDEXED, text, tokenize='porter unicode61')"
            )
        )
        conn.commit()


# ── Entity link helper ─────────────────────────────────────────────────────────

def _add_link(db: Session, from_type: str, from_id: str, rel: str, to_type: str, to_id: str) -> None:
    existing = (
        db.query(EntityLink)
        .filter_by(from_type=from_type, from_id=from_id, rel=rel, to_type=to_type, to_id=to_id)
        .first()
    )
    if existing is None:
        db.add(EntityLink(from_type=from_type, from_id=from_id, rel=rel, to_type=to_type, to_id=to_id))


# ── Main loader ────────────────────────────────────────────────────────────────

def load_pack(pack_path: str | Path, force: bool = False) -> TenantRecord:
    """Load a tenant pack into the database.

    Returns the TenantRecord (created or existing).

    Idempotency:
      - Same hash   → no-op, returns existing record.
      - Different hash (or force=True) → backup old DB, rebuild from scratch.
    """
    _ensure_dirs()
    pack_path = Path(pack_path)
    raw = pack_path.read_bytes()
    h = _pack_hash(raw)
    pack: dict = json.loads(raw)
    tenant_id: str = pack["tenant"]["id"]

    ctrl_db = get_control_session()
    try:
        rec: TenantRecord | None = ctrl_db.get(TenantRecord, tenant_id)

        if rec is not None and rec.pack_hash == h and not force:
            # Unchanged — no-op
            return rec

        db_dest = tenant_db_path(tenant_id)

        # Backup existing DB if it exists and hash changed
        if db_dest.exists():
            import app.db.control as _ctrl_mod
            ts = dt.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            backup_dir = _ctrl_mod._BACKUPS_DIR / f"{tenant_id}_{ts}"
            backup_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(db_dest, backup_dir / f"{tenant_id}.db")

        # Invalidate cached engine so a fresh one is created
        from app.core.tenancy import _invalidate_engine
        _invalidate_engine(tenant_id)

        # Create a fresh tenant DB
        engine = create_engine(
            f"sqlite:///{db_dest}",
            connect_args={"check_same_thread": False},
            echo=False,
        )
        _init_tenant_db(engine)
        SL = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        db = SL()

        try:
            _load_entities(db, pack)
            db.commit()
        finally:
            db.close()
        engine.dispose()

        # Update or create control record
        if rec is None:
            rec = TenantRecord(
                id=tenant_id,
                name=pack["tenant"]["name"],
                status="active",
                db_path=str(db_dest),
                pack_version=pack.get("schema_version", "tenant-pack/1"),
                pack_hash=h,
                is_default=(tenant_id == "sbu_demo"),
            )
            ctrl_db.add(rec)
        else:
            rec.name = pack["tenant"]["name"]
            rec.pack_hash = h
            rec.pack_version = pack.get("schema_version", "tenant-pack/1")
            rec.db_path = str(db_dest)
            rec.status = "active"
            rec.updated_at = dt.datetime.utcnow()

        ctrl_db.commit()
        ctrl_db.refresh(rec)
        return rec
    finally:
        ctrl_db.close()


# ── Entity loading ─────────────────────────────────────────────────────────────

def _load_entities(db: Session, pack: dict) -> None:
    """Load all entities from the pack into the tenant DB session."""
    t = pack["tenant"]

    # ── TenantConfig ──────────────────────────────────────────────────────────
    db.query(TenantConfig).delete()
    db.add(TenantConfig(
        tenant_id=t["id"],
        timezone=t["timezone"],
        clock=t.get("clock", "12h"),
        week_start=t.get("week_start", "sunday"),
        course_code_format=t.get("course_code_format", "{d} {n}"),
        room_code_format=t.get("room_code_format", "{b} {r}"),
        credit_unit=t.get("credit_unit", "credits"),
        role_vocabulary=json.dumps(t.get("role_vocabulary", {})),
        min_cell_size=5,
        extra_json=json.dumps({k: v for k, v in t.items()
                               if k not in ("id", "name", "timezone", "clock", "week_start",
                                            "course_code_format", "room_code_format",
                                            "credit_unit", "role_vocabulary", "data_origin")}),
    ))

    # ── People ────────────────────────────────────────────────────────────────
    ppl = pack.get("people", {})
    _load_people(db, ppl)

    # ── Teams ─────────────────────────────────────────────────────────────────
    _load_teams(db, pack.get("teams", []))

    # ── Memberships ───────────────────────────────────────────────────────────
    _load_memberships(db, pack.get("memberships", []))

    # ── Personas (alias → person mapping for KNOWN_PERSONAS) ─────────────────
    # Personas in the pack map display names; we store them as Person rows
    _load_personas(db, pack.get("personas", {}), ppl)

    # ── Knowledge ─────────────────────────────────────────────────────────────
    _load_knowledge(db, pack.get("knowledge", []))

    # ── Entity links (Section 4.3) ────────────────────────────────────────────
    _load_entity_links(db, pack)


def _load_people(db: Session, ppl: dict) -> None:
    for person in ppl.get("faculty", []):
        if db.get(Person, person["id"]) is None:
            db.add(Person(
                id=person["id"],
                display_name=person.get("display", person["id"]),
                role="faculty",
                email_local=person.get("email"),
                data_origin="synthetic",
            ))
    for person in ppl.get("staff", []):
        if db.get(Person, person["id"]) is None:
            db.add(Person(
                id=person["id"],
                display_name=person.get("display", person["id"]),
                role=person.get("role", "staff"),
                email_local=person.get("email"),
                data_origin="synthetic",
            ))
    for person in ppl.get("students", []):
        if db.get(Person, person["id"]) is None:
            db.add(Person(
                id=person["id"],
                display_name=person.get("display", person["id"]),
                role="student",
                email_local=person.get("email"),
                data_origin="synthetic",
            ))


def _load_teams(db: Session, teams: list) -> None:
    for tm in teams:
        if db.get(Team, tm["id"]) is None:
            scope = tm.get("scope", {})
            scope_type = "building"
            scope_id = None
            if scope.get("building_ids"):
                scope_id = ",".join(scope["building_ids"])
                scope_type = "building"
            elif scope.get("service_ids"):
                scope_id = ",".join(scope["service_ids"])
                scope_type = "service"
            db.add(Team(
                id=tm["id"],
                name=tm.get("name", tm["id"]),
                role_type=tm.get("role", "facilities"),
                scope_type=scope_type,
                scope_id=scope_id,
                data_origin="synthetic",
            ))


def _load_memberships(db: Session, memberships: list) -> None:
    for m in memberships:
        if m.get("team_id"):
            existing = db.query(TeamMembership).filter_by(
                person_id=m["person_id"], team_id=m["team_id"]
            ).first()
            if existing is None:
                db.add(TeamMembership(
                    person_id=m["person_id"],
                    team_id=m["team_id"],
                    is_lead=m.get("is_lead", False),
                ))


def _load_personas(db: Session, personas: dict, ppl: dict) -> None:
    """Update display names for persona keys that already exist as Person rows.

    The pack's personas dict maps canonical persona keys (e.g. 'student_alex')
    to their detailed info.  _load_people already loaded all person rows using
    the raw person IDs from people.faculty/staff/students.  Here we ensure
    the persona key itself is also addressable — only if it differs from the
    underlying person_id AND doesn't already exist.
    """
    db.flush()  # make sure _load_people inserts are visible
    for persona_key, ps in personas.items():
        pid = ps.get("person_id", persona_key)
        # Ensure the underlying person row exists (may have been seeded by _load_people)
        if db.get(Person, pid) is None:
            db.add(Person(
                id=pid,
                display_name=ps.get("display", persona_key),
                role=ps.get("role", "student"),
                data_origin="synthetic",
            ))
        # If the persona_key differs from the person_id AND doesn't yet exist,
        # add a row so persona lookups by key work (e.g. 'student_alex' → stf-10)
        if persona_key != pid and db.get(Person, persona_key) is None:
            db.add(Person(
                id=persona_key,
                display_name=ps.get("display", persona_key),
                role=ps.get("role", "student"),
                data_origin="synthetic",
            ))


def _load_knowledge(db: Session, knowledge: list) -> None:
    """Load knowledge items as KnowledgeDocument + KnowledgeChunk rows with FTS."""
    for item in knowledge:
        doc_id = item["id"]
        # Delete existing to allow reload
        existing = db.query(KnowledgeDocument).filter_by(id=doc_id).first()
        if existing is not None:
            db.delete(existing)
            db.flush()

        content = item.get("text", "")
        if not content and item.get("sections"):
            parts = []
            for sec in item["sections"]:
                parts.append(sec.get("heading", ""))
                parts.append(sec.get("body", ""))
            content = "\n".join(p for p in parts if p)

        doc = KnowledgeDocument(
            id=doc_id,
            title=item.get("title", doc_id),
            publisher=item.get("publisher", ""),
            canonical_url=f"pack:/{doc_id}",
            content_text=content,
            usage_note="Synthetic demo data",
            is_active=True,
        )
        db.add(doc)
        db.flush()

        # Single chunk per document
        chunk_id = f"{doc_id}-c0"
        chunk = KnowledgeChunk(
            id=chunk_id,
            document_id=doc_id,
            chunk_index=0,
            text=content,
            search_text=content.lower().strip(),
        )
        db.add(chunk)
        db.flush()

        # FTS index
        db.execute(
            text("INSERT OR REPLACE INTO knowledge_chunks_fts(chunk_id, text) VALUES (:cid, :t)"),
            {"cid": chunk_id, "t": content.lower()},
        )


def _load_entity_links(db: Session, pack: dict) -> None:
    """Build entity_links from pack relationships (Section 4.3)."""
    # room in_building building
    for room in pack.get("rooms", []):
        _add_link(db, "room", room["id"], "in_building", "building", room["building_id"])

    # section meets_in room; section taught_by person
    for sec in pack.get("sections", []):
        for meeting in sec.get("meetings", []):
            _add_link(db, "section", sec["id"], "meets_in", "room", meeting["room_id"])
        _add_link(db, "section", sec["id"], "taught_by", "person", sec["instructor_id"])
        # student enrolled_in section
        for student_id in sec.get("roster", []):
            _add_link(db, "student", student_id, "enrolled_in", "section", sec["id"])

    # asset located_in room (use building as proxy if no room_id)
    for asset in pack.get("assets", []):
        if asset.get("room_id"):
            _add_link(db, "asset", asset["id"], "located_in", "room", asset["room_id"])
        else:
            _add_link(db, "asset", asset["id"], "located_in", "building", asset["building_id"])

    # service covers building
    for svc in pack.get("services", []):
        for bid in svc.get("coverage_building_ids", []):
            _add_link(db, "service", svc["id"], "covers", "building", bid)

    # team scoped_to building|service|department
    for tm in pack.get("teams", []):
        scope = tm.get("scope", {})
        for bid in scope.get("building_ids", []):
            _add_link(db, "team", tm["id"], "scoped_to", "building", bid)
        for sid in scope.get("service_ids", []):
            _add_link(db, "team", tm["id"], "scoped_to", "service", sid)
        for did in scope.get("dept_ids", []):
            _add_link(db, "team", tm["id"], "scoped_to", "department", did)
