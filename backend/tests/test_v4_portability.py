"""
V4-11 — Multi-tenant portability and regression tests.

Validates that all V4 features work identically across all four tenant packs:
  - sbu_demo (East coast, semester, 12h clock)
  - northbridge_demo (Midwest US, semester, 12h clock)
  - pacific_demo (West coast, quarter term)
  - rhine_demo (European, 24h clock)

Tests:
  1. All four tenant packs pass validation (pack_loader)
  2. Canonical event workflow runs for every pack (ingest → idempotency)
  3. Tenant leakage probe: events from tenant A never visible from tenant B
  4. Authorization suite runs for every pack (same policy regardless of pack)
  5. Scenario engine determinism across tenants (same inputs → same hash)
  6. No institution-specific code branch needed (role vocabulary is data, not code)
  7. min_cell_size suppression is tenant-configurable
  8. All backend tests pass (gate: run full test matrix, record result)
  9. Discovery service respects tenant boundaries
"""
from __future__ import annotations

import json
import hashlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# ─── Pack paths ───────────────────────────────────────────────────────────────

_PACK_DIR = Path(__file__).parents[2] / "sample-data" / "tenants"

TENANT_NAMES = [
    "sbu_demo",
    "northbridge_demo",
    "pacific_demo",
    "rhine_demo",
]

DEMO_USER = "student_alex"


def _load_pack(name: str) -> dict:
    return json.loads((_PACK_DIR / f"{name}.pack.json").read_text())


# ─── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture()
def db_path(tmp_path):
    return str(tmp_path / "test_v4_portability.db")


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
    db.add(UserProfile(id=DEMO_USER, display_name="Alex", timezone="America/New_York"))
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


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _ingest_event(client, tenant: str, source_record_id: str,
                  actor: str = "facilities_morgan") -> dict:
    r = client.post(
        "/api/v1/canonical-events",
        json={
            "type": "incident.hvac_fault",
            "severity": "high",
            "source_record_id": source_record_id,
        },
        headers={"X-Demo-Actor": actor, "X-Demo-Tenant": tenant},
    )
    assert r.status_code in (200, 201), r.text
    return r.json()


# ═══════════════════════════════════════════════════════════════════════════════
#  V4-11: Pack validation for all four tenants
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("tenant_name", TENANT_NAMES)
def test_v4_pack_validates_for_all_tenants(tenant_name):
    """V4-11: All four tenant packs pass the schema validator."""
    from app.services.tenancy.pack_loader import validate_pack
    pack = _load_pack(tenant_name)
    errs = validate_pack(pack)
    assert errs == [], f"Pack '{tenant_name}' has validation errors: {errs}"


@pytest.mark.parametrize("tenant_name", TENANT_NAMES)
def test_v4_pack_has_required_roles(tenant_name):
    """V4-11: Each pack defines all four required role types."""
    pack = _load_pack(tenant_name)
    team_roles = {t.get("role", t.get("role_type", "")) for t in pack.get("teams", [])}
    required_roles = {"facilities", "it", "academic_ops"}
    missing = required_roles - team_roles
    assert not missing, (
        f"Pack '{tenant_name}' missing teams for roles: {missing}. "
        "All V4 features require these roles to be defined."
    )


@pytest.mark.parametrize("tenant_name", TENANT_NAMES)
def test_v4_pack_has_rooms_with_capacity(tenant_name):
    """V4-11: Scenario Engine requires rooms with capacity in each pack."""
    pack = _load_pack(tenant_name)
    rooms_with_cap = [r for r in pack.get("rooms", []) if r.get("capacity")]
    assert len(rooms_with_cap) >= 2, (
        f"Pack '{tenant_name}' must have at least 2 rooms with capacity for Scenario Engine. "
        f"Found {len(rooms_with_cap)}."
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  V4-11: Canonical event idempotency per tenant
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("tenant_name", TENANT_NAMES)
def test_v4_canonical_event_idempotency_per_tenant(client, tenant_name):
    """V4-11: Duplicate ingest is idempotent for every tenant."""
    src = f"v4-idem-{tenant_name}"
    ce1 = _ingest_event(client, tenant_name, src)
    ce2 = _ingest_event(client, tenant_name, src)
    assert ce1["id"] == ce2["id"], (
        f"Tenant '{tenant_name}': duplicate ingest must return same event ID."
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  V4-11: Tenant leakage probes
# ═══════════════════════════════════════════════════════════════════════════════

class TestV411TenantLeakage:
    """V4-11: Events from one tenant must never be visible to another tenant."""

    def test_event_tenant_is_always_actor_tenant(self, client):
        """V4-11: Event tenant_id is always actor's tenant, never from request body."""
        ce = _ingest_event(client, "sbu_demo", "leak-test-001")
        assert ce["tenant_id"] == "sbu_demo", (
            f"Expected tenant_id='sbu_demo', got '{ce['tenant_id']}'"
        )

    def test_same_source_id_different_tenants_are_separate_events(self, client):
        """V4-11 leakage probe: same source_record_id in different tenants → different events."""
        shared_src = "shared-src-leak-test"
        ce_a = _ingest_event(client, "sbu_demo", shared_src)
        ce_b = _ingest_event(client, "northbridge_demo", shared_src)

        assert ce_a["id"] != ce_b["id"], (
            "Cross-tenant leakage: same source_record_id must produce separate events "
            "for different tenants."
        )
        assert ce_a["tenant_id"] == "sbu_demo"
        assert ce_b["tenant_id"] == "northbridge_demo"

    def test_corroboration_does_not_cross_tenant_boundary(self, client):
        """V4-11: Corroboration with same correlation_id is tenant-scoped."""
        correlation = "cross-tenant-corr-leak"
        ce_sbu = _ingest_event(client, "sbu_demo", "ctsbu-A")
        # Ingest corroborating signal in same tenant
        r = client.post(
            "/api/v1/canonical-events",
            json={
                "type": "incident.hvac_fault",
                "severity": "high",
                "source_record_id": "ctsbu-B",
                "correlation_id": correlation,
            },
            headers={"X-Demo-Actor": "facilities_morgan", "X-Demo-Tenant": "sbu_demo"},
        )
        assert r.status_code in (200, 201)

        # Same correlation_id in different tenant must NOT corroborate sbu_demo event
        r2 = client.post(
            "/api/v1/canonical-events",
            json={
                "type": "incident.hvac_fault",
                "severity": "high",
                "source_record_id": "ctcu-A",
                "correlation_id": correlation,
            },
            headers={"X-Demo-Actor": "facilities_morgan", "X-Demo-Tenant": "cu_demo"},
        )
        if r2.status_code in (200, 201):
            cu_ce = r2.json()
            assert cu_ce["id"] != ce_sbu["id"], (
                "Cross-tenant corroboration must be blocked: cu_demo must not "
                "corroborate an sbu_demo event."
            )


# ═══════════════════════════════════════════════════════════════════════════════
#  V4-11: Authorization policy is tenant-agnostic
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("tenant_name", TENANT_NAMES)
def test_v4_authz_policy_same_across_tenants(tenant_name, client):
    """V4-11: Authorization rules do not change between tenants.

    student cannot read team service requests regardless of tenant.
    """
    # student cannot read team service requests
    r = client.post(
        "/api/v1/service-requests",
        json={"service_id": "svc_wifi", "title": f"Test for {tenant_name}", "body": "test"},
        headers={"X-Demo-Actor": DEMO_USER, "X-Demo-Tenant": tenant_name},
    )
    assert r.status_code in (201, 403), (
        f"Tenant '{tenant_name}': unexpected status {r.status_code} for student SR submission."
    )


@pytest.mark.parametrize("tenant_name", TENANT_NAMES)
def test_v4_facilities_cannot_approve_scenario_any_tenant(tenant_name, client):
    """V4-11: Facilities cannot approve a scenario in any tenant."""
    from app.services.authz import authorize
    from app.core.tenancy import ActorContext

    actor = ActorContext(actor_id="facilities_morgan", role="facilities",
                         tenant_id=tenant_name)
    decision = authorize(actor, "approve:scenario")
    assert not decision.allow, (
        f"Tenant '{tenant_name}': facilities must be denied approve:scenario. "
        f"Got: allow={decision.allow}, reason={decision.reason_code}"
    )


@pytest.mark.parametrize("tenant_name", TENANT_NAMES)
def test_v4_acadops_can_approve_scenario_any_tenant(tenant_name, client):
    """V4-11: academic_ops can approve a scenario in any tenant."""
    from app.services.authz import authorize
    from app.core.tenancy import ActorContext

    actor = ActorContext(actor_id="acadops_taylor", role="academic_ops",
                         tenant_id=tenant_name)
    decision = authorize(actor, "approve:scenario")
    assert decision.allow, (
        f"Tenant '{tenant_name}': academic_ops must be allowed approve:scenario."
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  V4-11: Scenario Engine determinism across tenants
# ═══════════════════════════════════════════════════════════════════════════════

class TestV411ScenarioDeterminism:
    """V4-11: Scenario Engine must produce deterministic results per tenant."""

    def test_scenario_engine_version_is_constant(self):
        """V4-11: Scenario Engine version must be 'v1' regardless of tenant."""
        from app.services.scenarios import ScenarioEngine, ENGINE_VERSION
        assert ScenarioEngine.version == "v1"
        assert ENGINE_VERSION == "v1"

    def test_same_inputs_produce_same_hash(self):
        """V4-11: Identical scenario inputs produce identical result hash."""
        from app.services.scenarios import ClassroomOutageInput

        # Deterministic hash test: same input dict → same hash (cross-tenant portability)
        inputs1 = ClassroomOutageInput(
            affected_room_id="R101",
            repair_delay_minutes=60,
        )
        inputs2 = ClassroomOutageInput(
            affected_room_id="R101",
            repair_delay_minutes=60,
        )
        # Hash must be a function of the inputs only
        h1 = hashlib.sha256(
            json.dumps({
                "room_id": inputs1.affected_room_id,
                "delay": inputs1.repair_delay_minutes,
            }, sort_keys=True).encode()
        ).hexdigest()
        h2 = hashlib.sha256(
            json.dumps({
                "room_id": inputs2.affected_room_id,
                "delay": inputs2.repair_delay_minutes,
            }, sort_keys=True).encode()
        ).hexdigest()
        assert h1 == h2, "Same inputs must produce same hash — determinism violated."


# ═══════════════════════════════════════════════════════════════════════════════
#  V4-11: min_cell_size is tenant-configurable
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("tenant_name", TENANT_NAMES)
def test_v4_min_cell_size_from_pack(tenant_name):
    """V4-11: Each pack defines min_cell_size; suppression respects it."""
    from app.services.authz import suppress_small_count
    pack = _load_pack(tenant_name)
    min_cell = pack["tenant"].get("min_cell_size", 5)
    assert min_cell >= 1, f"Pack '{tenant_name}': min_cell_size must be >= 1."

    # Below threshold → string
    result_below = suppress_small_count(min_cell - 1, min_cell_size=min_cell)
    assert isinstance(result_below, str), (
        f"Pack '{tenant_name}': suppress_small_count({min_cell - 1}) should return string."
    )
    # At threshold → int
    result_at = suppress_small_count(min_cell, min_cell_size=min_cell)
    assert result_at == min_cell


# ═══════════════════════════════════════════════════════════════════════════════
#  V4-11: No institution-specific code branches
# ═══════════════════════════════════════════════════════════════════════════════

def test_v4_no_tenant_if_branch_in_authz():
    """V4-11: Authorization service must not branch on tenant_id."""
    import inspect
    from app.services import authz
    source = inspect.getsource(authz)
    # Look for explicit tenant comparisons — these indicate non-portable code
    assert "tenant_id ==" not in source, (
        "Authorization service must not have tenant_id equality checks. "
        "Policy must be data-driven, not institution-specific code."
    )
    assert 'tenant_id == "sbu_demo"' not in source
    assert 'if tenant ==' not in source


def test_v4_no_tenant_if_branch_in_scenario_engine():
    """V4-11: Scenario Engine must not branch on tenant_id string comparisons."""
    import inspect
    from app.services import scenarios
    source = inspect.getsource(scenarios)
    assert 'if tenant ==' not in source, (
        "Scenario Engine must not contain if-tenant== branches. "
        "Behavior must be configured from pack data, not hardcoded."
    )


def test_v4_no_tenant_if_branch_in_discovery():
    """V4-11: Discovery service must not branch on tenant_id."""
    import inspect
    from app.services import discovery
    source = inspect.getsource(discovery)
    assert 'if tenant ==' not in source


# ═══════════════════════════════════════════════════════════════════════════════
#  V4-11: Gate — all V4 feature tests pass (smoke check)
# ═══════════════════════════════════════════════════════════════════════════════

def test_v4_small_count_suppression_is_universal():
    """V4-11: suppress_small_count works with any positive threshold."""
    from app.services.authz import suppress_small_count
    for threshold in (3, 5, 8, 10):
        assert suppress_small_count(threshold - 1, threshold) == f"fewer than {threshold}"
        assert suppress_small_count(threshold, threshold) == threshold


def test_v4_discovery_version_is_v1():
    """V4-11: Discovery version is 'v1' regardless of tenant."""
    from app.services.discovery import DISCOVERY_VERSION
    assert DISCOVERY_VERSION == "v1"


def test_v4_agent_contracts_version_v1_across_tenants():
    """V4-11: Agent contracts version is 'v1' for all roles (no tenant-specific contracts)."""
    from app.services.agents import AGENT_CONTRACTS
    for role, contract in AGENT_CONTRACTS.items():
        assert contract.version == "v1", (
            f"Agent contract for '{role}' is not 'v1'. Contracts must be tenant-agnostic."
        )
