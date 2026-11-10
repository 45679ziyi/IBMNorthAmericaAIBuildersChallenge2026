"""
V4-08 / V4-09 — Stakeholder Agents and Resource Discovery tests.

V4-08 tests:
  - Agent contract version is "v1" for all defined roles
  - build_context_package silently drops disallowed data categories
  - Agents cannot see data outside their allowed_data_categories
  - Agent failure does not stop other agents (partial-result behavior)
  - Unknown role produces error result, not an exception
  - No state-changing tools in any contract
  - All findings have evidence references (or are marked assumption)
  - LLM outage (use_llm=False) uses deterministic fallback for all roles
  - Orchestrator aggregates agreements and unresolved questions

V4-09 tests:
  - NL query parser extracts capacity from "30 seats" pattern
  - NL query parser extracts features from "projector" keyword
  - Room discovery filters out rooms below min_capacity (hard constraint)
  - Room discovery filters out excluded rooms
  - Room discovery ranks best room first (highest total_score)
  - Discovery version is "v1"
  - No-match state is reported when no rooms pass constraints
  - Service discovery filters by role_type
  - Scoring weights sum to 1.0
  - Factor scores are between 0.0 and 1.0
  - Missing data fields are disclosed
  - Deterministic: same inputs → same output
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker


# ─── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture()
def db_path(tmp_path):
    return str(tmp_path / "test_v4_agents_disco.db")


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
    monkeypatch.setattr(cfg_mod.settings, "demo_user_id", "student_alex")
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
    db.add(UserProfile(id="student_alex", display_name="Alex", timezone="America/New_York"))
    db.add(UserPreference(
        user_id="student_alex", day_start_time="08:00", day_end_time="22:00",
        preferred_focus_block_minutes=50, short_break_minutes=10,
        long_break_minutes=30, default_travel_buffer_minutes=10,
    ))
    db.commit()
    db.close()


@pytest.fixture()
def db(test_session_factory):
    sess = test_session_factory()
    try:
        yield sess
    finally:
        sess.close()


@pytest.fixture()
def db_with_rooms(test_session_factory):
    """Seed DB with rooms via EntityLink.meta_json."""
    import json as _json
    from app.models.models import EntityLink

    rooms = [
        {"room_id": "R101", "building_id": "BLD_A", "capacity": 40, "features": ["projector", "whiteboard"]},
        {"room_id": "R202", "building_id": "BLD_A", "capacity": 25, "features": ["whiteboard"]},
        {"room_id": "R305", "building_id": "BLD_B", "capacity": 80, "features": ["projector", "av", "video_conferencing"]},
        {"room_id": "R410", "building_id": "BLD_C", "capacity": 15, "features": []},
        {"room_id": "R501", "building_id": "BLD_A", "capacity": 120, "features": ["projector"]},
    ]

    db = test_session_factory()
    for r in rooms:
        meta = _json.dumps({"capacity": r["capacity"], "features": r["features"], "name": r["room_id"]})
        db.add(EntityLink(
            from_type="room", from_id=r["room_id"],
            rel="in_building",
            to_type="building", to_id=r["building_id"],
            meta_json=meta,
        ))
    db.commit()
    db.close()

    sess = test_session_factory()
    try:
        yield sess
    finally:
        sess.close()


# ═══════════════════════════════════════════════════════════════════════════════
#  V4-08: Agent contracts
# ═══════════════════════════════════════════════════════════════════════════════

class TestV408AgentContracts:
    """V4-08: Agent contracts are versioned and define bounded data access."""

    def test_all_defined_roles_have_contracts(self):
        from app.services.agents import AGENT_CONTRACTS
        expected_roles = {"facilities", "it", "academic_ops", "faculty"}
        defined_roles = set(AGENT_CONTRACTS.keys())
        assert expected_roles <= defined_roles, (
            f"Missing agent contracts for roles: {expected_roles - defined_roles}"
        )

    def test_all_contracts_are_version_v1(self):
        from app.services.agents import AGENT_CONTRACTS
        for role, contract in AGENT_CONTRACTS.items():
            assert contract.version == "v1", (
                f"Agent contract for '{role}' must be version 'v1', got '{contract.version}'"
            )

    def test_contracts_have_non_empty_allowed_categories(self):
        from app.services.agents import AGENT_CONTRACTS
        for role, contract in AGENT_CONTRACTS.items():
            assert len(contract.allowed_data_categories) > 0, (
                f"Contract for '{role}' has empty allowed_data_categories."
            )

    def test_contracts_have_non_empty_tool_allowlist(self):
        from app.services.agents import AGENT_CONTRACTS
        for role, contract in AGENT_CONTRACTS.items():
            assert len(contract.tool_allowlist) > 0, (
                f"Contract for '{role}' has empty tool_allowlist."
            )

    def test_no_state_changing_tools_in_any_contract(self):
        """V4-08: No agent contract may include state-changing tool names."""
        from app.services.agents import AGENT_CONTRACTS
        state_changing_keywords = {
            "create", "delete", "update", "modify", "write", "approve",
            "promote", "transition", "commit", "post", "patch",
        }
        for role, contract in AGENT_CONTRACTS.items():
            for tool in contract.tool_allowlist:
                tool_lower = tool.lower()
                for kw in state_changing_keywords:
                    assert kw not in tool_lower, (
                        f"Agent contract for '{role}' contains potentially state-changing "
                        f"tool '{tool}' (contains keyword '{kw}'). "
                        "Agents must be read-only."
                    )


# ═══════════════════════════════════════════════════════════════════════════════
#  V4-08: Context package sanitization
# ═══════════════════════════════════════════════════════════════════════════════

class TestV408ContextSanitization:
    """V4-08: build_context_package drops disallowed categories."""

    def test_disallowed_data_categories_are_dropped(self):
        from app.services.agents import build_context_package

        # Give 'facilities' agent data that includes student names (not in contract)
        raw_data = {
            "room_capacity": {"R101": 40},
            "scenario_candidates": [],
            "student_personal_data": [{"id": "s1", "name": "Alice"}],  # NOT allowed
            "personal_schedule": {"id": "s1", "courses": []},           # NOT allowed
        }
        ctx = build_context_package(
            role="facilities",
            tenant_id="sbu_demo",
            canonical_event_id="ce_test",
            scenario_run_id=None,
            raw_data=raw_data,
        )
        assert "student_personal_data" not in ctx.data, (
            "student_personal_data must be dropped for facilities agent."
        )
        assert "personal_schedule" not in ctx.data, (
            "personal_schedule must be dropped for facilities agent."
        )
        assert "room_capacity" in ctx.data, (
            "room_capacity should be kept for facilities agent."
        )

    def test_each_agent_sees_only_its_own_categories(self):
        from app.services.agents import build_context_package, AGENT_CONTRACTS

        shared_raw = {
            "room_capacity": {"R1": 30},
            "section_count": 5,
            "affected_meetings": [],
            "affected_students_aggregate": 42,
            "av_equipment": {"R1": ["projector"]},
            "scenario_candidates": [],
            "repair_status": "in_progress",
            "meeting_time": "14:00",
        }

        for role in ("facilities", "it", "academic_ops", "faculty"):
            contract = AGENT_CONTRACTS[role]
            ctx = build_context_package(
                role=role, tenant_id="sbu_demo",
                canonical_event_id=None, scenario_run_id=None,
                raw_data=shared_raw,
            )
            for category in ctx.data:
                assert category in contract.allowed_data_categories, (
                    f"Category '{category}' appeared in context for '{role}' "
                    "but is not in its allowed_data_categories."
                )

    def test_unknown_role_raises_value_error(self):
        from app.services.agents import build_context_package

        with pytest.raises(ValueError, match="No agent contract"):
            build_context_package(
                role="superadmin",
                tenant_id="sbu_demo",
                canonical_event_id=None,
                scenario_run_id=None,
                raw_data={},
            )


# ═══════════════════════════════════════════════════════════════════════════════
#  V4-08: Deterministic fallback analysis
# ═══════════════════════════════════════════════════════════════════════════════

class TestV408DeterministicFallback:
    """V4-08: Fallback analysis works without LLM and produces findings."""

    def test_facilities_fallback_with_candidates(self):
        from app.services.agents import build_context_package, AGENT_CONTRACTS, _fallback_analysis

        raw_data = {
            "room_capacity": {"R101": 40},
            "scenario_candidates": [
                {"room_id": "R101", "scores": {"capacity_fit": 0.9}, "walk_minutes": 3}
            ],
            "repair_status": "in_progress",
        }
        ctx = build_context_package("facilities", "sbu_demo", "ce_1", None, raw_data)
        contract = AGENT_CONTRACTS["facilities"]
        result = _fallback_analysis(ctx, contract)

        assert result.role == "facilities"
        assert result.used_fallback is True
        assert len(result.findings) >= 1, "Facilities fallback must produce at least 1 finding"

    def test_academic_ops_fallback_with_meetings(self):
        from app.services.agents import build_context_package, AGENT_CONTRACTS, _fallback_analysis

        raw_data = {
            "affected_meetings": [{"id": "m1"}, {"id": "m2"}],
            "affected_students_aggregate": 34,
            "scenario_candidates": [],
            "section_count": 2,
        }
        ctx = build_context_package("academic_ops", "sbu_demo", "ce_1", None, raw_data)
        contract = AGENT_CONTRACTS["academic_ops"]
        result = _fallback_analysis(ctx, contract)

        texts = " ".join(f.text for f in result.findings)
        assert "2" in texts, "academic_ops findings should mention 2 affected meetings"

    def test_all_findings_have_evidence_or_assumption_flag(self):
        from app.services.agents import build_context_package, AGENT_CONTRACTS, _fallback_analysis

        raw_data = {
            "scenario_candidates": [
                {"room_id": "R202", "scores": {}, "walk_minutes": 5}
            ],
        }
        for role in ("facilities", "it", "academic_ops", "faculty"):
            ctx = build_context_package(role, "sbu_demo", None, None, raw_data)
            contract = AGENT_CONTRACTS[role]
            result = _fallback_analysis(ctx, contract)
            for finding in result.findings:
                assert finding.evidence or finding.is_assumption, (
                    f"Finding for '{role}' has no evidence and is not marked as assumption: "
                    f"'{finding.text}'"
                )


# ═══════════════════════════════════════════════════════════════════════════════
#  V4-08: Orchestrator — partial results and aggregation
# ═══════════════════════════════════════════════════════════════════════════════

class TestV408Orchestrator:
    """V4-08: Orchestrator produces partial results and aggregates correctly."""

    def test_unknown_role_in_roles_list_produces_error_not_exception(self):
        from app.services.agents import run_stakeholder_analysis

        result = run_stakeholder_analysis(
            roles=["facilities", "superadmin", "it"],
            tenant_id="sbu_demo",
            canonical_event_id="ce_x",
            scenario_run_id=None,
            raw_data={"scenario_candidates": []},
        )
        # superadmin should produce an error result, not crash the whole run
        roles_in_results = {r.role for r in result.agent_results}
        assert "superadmin" in roles_in_results
        superadmin_result = next(r for r in result.agent_results if r.role == "superadmin")
        assert superadmin_result.error is not None

        # facilities and it should still have results
        assert "facilities" in roles_in_results
        assert "it" in roles_in_results

    def test_orchestrator_returns_all_requested_roles(self):
        from app.services.agents import run_stakeholder_analysis

        roles = ["facilities", "it", "academic_ops"]
        result = run_stakeholder_analysis(
            roles=roles,
            tenant_id="sbu_demo",
            canonical_event_id=None,
            scenario_run_id=None,
            raw_data={"scenario_candidates": []},
        )
        result_roles = {r.role for r in result.agent_results}
        for r in roles:
            assert r in result_roles, f"Role '{r}' missing from orchestrator results."

    def test_llm_outage_fallback_does_not_crash(self):
        """V4-08: use_llm=False always uses deterministic fallback — no LLM call."""
        from app.services.agents import run_stakeholder_analysis

        result = run_stakeholder_analysis(
            roles=["facilities", "academic_ops"],
            tenant_id="sbu_demo",
            canonical_event_id="ce_test",
            scenario_run_id="run_test",
            raw_data={
                "scenario_candidates": [{"room_id": "R101", "scores": {}, "walk_minutes": 3}],
                "affected_meetings": [{"id": "m1"}],
                "affected_students_aggregate": 12,
            },
            use_llm=False,
        )
        assert result is not None
        # All results should use fallback
        for r in result.agent_results:
            if not r.error:
                assert r.used_fallback is True, (
                    f"Agent '{r.role}' should use fallback when use_llm=False."
                )

    def test_context_not_expanded_between_agents(self):
        """V4-08: Each agent receives only its own categories — no cross-contamination."""
        from app.services.agents import AGENT_CONTRACTS, build_context_package

        # academic_ops has student data; facilities should NOT get it
        raw = {
            "affected_students_aggregate": 50,  # academic_ops only
            "room_capacity": {"R1": 30},         # facilities only
            "scenario_candidates": [],
        }
        facilities_ctx = build_context_package("facilities", "sbu_demo", None, None, raw)
        assert "affected_students_aggregate" not in facilities_ctx.data

        acadops_ctx = build_context_package("academic_ops", "sbu_demo", None, None, raw)
        assert "affected_students_aggregate" in acadops_ctx.data


# ═══════════════════════════════════════════════════════════════════════════════
#  V4-09: NL query parser
# ═══════════════════════════════════════════════════════════════════════════════

class TestV409NLParser:
    """V4-09: Natural-language query parser creates draft structured query."""

    def test_capacity_extracted_from_seats_pattern(self):
        from app.services.discovery import parse_room_query_from_nl
        query, summary = parse_room_query_from_nl("I need a room for 30 students")
        assert query.min_capacity == 30, f"Expected min_capacity=30, got {query.min_capacity}"
        assert "30" in summary

    def test_capacity_extracted_from_capacity_word(self):
        from app.services.discovery import parse_room_query_from_nl
        query, _ = parse_room_query_from_nl("find a room with capacity 50")
        assert query.min_capacity == 50

    def test_projector_feature_extracted(self):
        from app.services.discovery import parse_room_query_from_nl
        query, summary = parse_room_query_from_nl("needs a room with projector and whiteboard")
        assert "projector" in query.required_features
        assert "whiteboard" in query.required_features

    def test_large_room_inferred_capacity(self):
        from app.services.discovery import parse_room_query_from_nl
        query, summary = parse_room_query_from_nl("looking for a large lecture room")
        assert query.min_capacity >= 50, (
            f"'large' should infer min_capacity >= 50, got {query.min_capacity}"
        )

    def test_small_room_inferred_capacity(self):
        from app.services.discovery import parse_room_query_from_nl
        query, _ = parse_room_query_from_nl("need a small meeting room")
        assert 0 < query.min_capacity <= 20

    def test_no_features_in_plain_query(self):
        from app.services.discovery import parse_room_query_from_nl
        query, _ = parse_room_query_from_nl("find any available room")
        # No specific features expected
        assert isinstance(query.required_features, list)

    def test_empty_query_returns_default_query(self):
        from app.services.discovery import parse_room_query_from_nl
        query, summary = parse_room_query_from_nl("")
        assert query.min_capacity == 0
        assert query.required_features == []


# ═══════════════════════════════════════════════════════════════════════════════
#  V4-09: Room discovery — hard constraints
# ═══════════════════════════════════════════════════════════════════════════════

class TestV409RoomHardConstraints:
    """V4-09: Hard constraints filter before scoring."""

    def test_rooms_below_min_capacity_are_infeasible(self, db_with_rooms):
        from app.services.discovery import RoomQuery, discover_rooms

        query = RoomQuery(min_capacity=50)
        result = discover_rooms(db_with_rooms, query)

        candidate_ids = {c.resource_id for c in result.candidates}
        # R202 (25), R410 (15) are below 50 and must be infeasible
        assert "R202" not in candidate_ids, "R202 (cap=25) must be infeasible for min_cap=50"
        assert "R410" not in candidate_ids, "R410 (cap=15) must be infeasible for min_cap=50"

        infeasible_ids = {r.resource_id for r in result.infeasible}
        assert "R202" in infeasible_ids
        assert "R410" in infeasible_ids

    def test_excluded_rooms_are_removed(self, db_with_rooms):
        from app.services.discovery import RoomQuery, discover_rooms

        query = RoomQuery(exclude_rooms={"R101", "R305"})
        result = discover_rooms(db_with_rooms, query)

        candidate_ids = {c.resource_id for c in result.candidates}
        assert "R101" not in candidate_ids, "R101 is excluded"
        assert "R305" not in candidate_ids, "R305 is excluded"

    def test_required_feature_filters_rooms_without_it(self, db_with_rooms):
        from app.services.discovery import RoomQuery, discover_rooms

        query = RoomQuery(required_features=["video_conferencing"])
        result = discover_rooms(db_with_rooms, query)

        candidate_ids = {c.resource_id for c in result.candidates}
        # Only R305 has video_conferencing
        assert "R305" in candidate_ids
        # R101 (no video_conferencing) should be infeasible
        assert "R101" not in candidate_ids


# ═══════════════════════════════════════════════════════════════════════════════
#  V4-09: Room discovery — soft scoring
# ═══════════════════════════════════════════════════════════════════════════════

class TestV409RoomScoring:
    """V4-09: Soft scoring produces explainable, deterministic results."""

    def test_best_room_ranked_first(self, db_with_rooms):
        from app.services.discovery import RoomQuery, discover_rooms

        query = RoomQuery(min_capacity=30)
        result = discover_rooms(db_with_rooms, query)

        assert len(result.candidates) >= 2
        scores = [c.total_score for c in result.candidates]
        assert scores == sorted(scores, reverse=True), (
            "Candidates must be sorted by total_score descending."
        )
        assert result.candidates[0].rank == 1

    def test_factor_scores_between_0_and_1(self, db_with_rooms):
        from app.services.discovery import RoomQuery, discover_rooms

        query = RoomQuery(min_capacity=20, preferred_building="BLD_A")
        result = discover_rooms(db_with_rooms, query)

        for c in result.candidates:
            for factor, score in c.factor_scores.items():
                assert 0.0 <= score <= 1.0, (
                    f"Factor score '{factor}' for room {c.resource_id} = {score} "
                    "must be between 0.0 and 1.0"
                )

    def test_total_score_is_between_0_and_1(self, db_with_rooms):
        from app.services.discovery import RoomQuery, discover_rooms

        query = RoomQuery()
        result = discover_rooms(db_with_rooms, query)
        for c in result.candidates:
            assert 0.0 <= c.total_score <= 1.0

    def test_weights_sum_to_1(self):
        from app.services.discovery import ROOM_WEIGHTS
        total = sum(ROOM_WEIGHTS.values())
        assert abs(total - 1.0) < 1e-9, (
            f"ROOM_WEIGHTS must sum to 1.0, got {total}"
        )

    def test_same_building_gets_higher_proximity_score(self, db_with_rooms):
        from app.services.discovery import RoomQuery, discover_rooms

        query = RoomQuery(min_capacity=20, preferred_building="BLD_A")
        result = discover_rooms(db_with_rooms, query)

        bld_a_candidates = [c for c in result.candidates if c.resource_id in {"R101", "R202", "R501"}]
        bld_b_candidates = [c for c in result.candidates if c.resource_id == "R305"]

        if bld_a_candidates and bld_b_candidates:
            avg_a_proximity = sum(
                c.factor_scores.get("building_proximity", 0) for c in bld_a_candidates
            ) / len(bld_a_candidates)
            bld_b_proximity = bld_b_candidates[0].factor_scores.get("building_proximity", 0)
            assert avg_a_proximity > bld_b_proximity, (
                "BLD_A rooms should have higher proximity score than BLD_B "
                "when preferred_building=BLD_A and no walking_minutes provided."
            )

    def test_discovery_is_deterministic(self, db_with_rooms):
        """V4-09: Same inputs produce same outputs."""
        from app.services.discovery import RoomQuery, discover_rooms

        query = RoomQuery(min_capacity=20, required_features=["projector"],
                          preferred_building="BLD_A")
        result1 = discover_rooms(db_with_rooms, query)
        result2 = discover_rooms(db_with_rooms, query)

        ids1 = [c.resource_id for c in result1.candidates]
        ids2 = [c.resource_id for c in result2.candidates]
        assert ids1 == ids2, "Discovery must be deterministic for same inputs."

    def test_discovery_version_is_v1(self, db_with_rooms):
        from app.services.discovery import RoomQuery, discover_rooms, DISCOVERY_VERSION

        query = RoomQuery()
        result = discover_rooms(db_with_rooms, query)
        assert result.discovery_version == "v1"
        assert DISCOVERY_VERSION == "v1"

    def test_no_match_reason_when_all_fail_constraints(self, db_with_rooms):
        from app.services.discovery import RoomQuery, discover_rooms

        # Impossible capacity — no room has 9999 seats
        query = RoomQuery(min_capacity=9999)
        result = discover_rooms(db_with_rooms, query)
        assert result.candidates == []
        assert result.no_match_reason is not None
        assert len(result.no_match_reason) > 0

    def test_missing_data_disclosed_when_capacity_unknown(self, db_with_rooms, test_session_factory):
        """V4-09: Room with no capacity metadata reports missing_data."""
        import json as _json
        from app.models.models import EntityLink
        from app.services.discovery import RoomQuery, discover_rooms

        # Add a room with no capacity
        db_setup = test_session_factory()
        db_setup.add(EntityLink(
            from_type="room", from_id="R_NOCAP",
            rel="in_building",
            to_type="building", to_id="BLD_A",
            meta_json=_json.dumps({"features": ["whiteboard"]}),  # no capacity
        ))
        db_setup.commit()
        db_setup.close()

        query = RoomQuery(min_capacity=0)
        result = discover_rooms(db_with_rooms, query)

        nocap = next((c for c in result.candidates if c.resource_id == "R_NOCAP"), None)
        if nocap:
            assert "room_capacity" in nocap.missing_data, (
                "Room with unknown capacity must disclose 'room_capacity' in missing_data."
            )
