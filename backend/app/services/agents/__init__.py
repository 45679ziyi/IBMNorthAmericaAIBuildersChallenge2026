"""
V4-08 — Stakeholder Analysis Agents service.

Each agent:
- Has a versioned contract defining its allowed data categories and tool allowlist.
- Receives only a sanitized, minimal context package.
- Produces structured output with evidence references.
- Cannot execute state-changing actions (read-only).
- Has a deterministic fallback when the LLM is unavailable.

Orchestrator:
- Calls agents in bounded, sequential order.
- Aggregates agreements, disagreements, and unresolved questions.
- Prevents role/tenant context expansion between agents.
- Partial-result behavior: if one agent fails, others still run.

Contracts version: "v1"
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Optional


# ─── Agent contracts ─────────────────────────────────────────────────────────

@dataclass(frozen=True)
class AgentContract:
    """Versioned, read-only contract for one stakeholder agent.

    allowed_data_categories: set of data categories this agent may receive.
    tool_allowlist: set of read-only tool names this agent may call.
    role: the stakeholder perspective this agent represents.
    version: contract version string.

    No agent may call any state-changing action.
    No agent may see data outside its allowed_data_categories.
    """
    role: str
    version: str
    allowed_data_categories: frozenset[str]
    tool_allowlist: frozenset[str]


# Contract registry — one entry per stakeholder role.
AGENT_CONTRACTS: dict[str, AgentContract] = {
    "facilities": AgentContract(
        role="facilities",
        version="v1",
        allowed_data_categories=frozenset({
            "room_capacity",
            "room_features",
            "building_proximity",
            "repair_status",
            "scenario_candidates",
            "infeasible_rooms",
        }),
        tool_allowlist=frozenset({
            "get_room_capacity",
            "get_building_proximity",
            "list_candidate_rooms",
            "get_repair_status",
        }),
    ),
    "it": AgentContract(
        role="it",
        version="v1",
        allowed_data_categories=frozenset({
            "room_features",
            "av_equipment",
            "network_coverage",
            "scenario_candidates",
        }),
        tool_allowlist=frozenset({
            "get_room_features",
            "check_av_equipment",
            "check_network_coverage",
            "list_candidate_rooms",
        }),
    ),
    "academic_ops": AgentContract(
        role="academic_ops",
        version="v1",
        allowed_data_categories=frozenset({
            "section_count",
            "affected_meetings",
            "affected_students_aggregate",  # aggregate only — no individual names
            "scenario_candidates",
            "scenario_scores",
            "policy_constraints",
        }),
        tool_allowlist=frozenset({
            "get_affected_sections",
            "get_affected_meetings",
            "get_affected_students_aggregate",
            "list_candidate_rooms",
            "get_scenario_scores",
        }),
    ),
    "faculty": AgentContract(
        role="faculty",
        version="v1",
        allowed_data_categories=frozenset({
            "section_id",
            "meeting_time",
            "room_features",
            "scenario_candidates",
        }),
        tool_allowlist=frozenset({
            "get_section_details",
            "get_meeting_times",
            "list_candidate_rooms",
        }),
    ),
}


# ─── Context package ─────────────────────────────────────────────────────────

@dataclass
class AgentContextPackage:
    """Sanitized, minimal context for one agent run.

    Only fields that are in the agent's allowed_data_categories are populated.
    Caller must enforce this before constructing the package.
    """
    role: str
    tenant_id: str
    canonical_event_id: Optional[str]
    scenario_run_id: Optional[str]
    # Allowed data, keyed by category name
    data: dict[str, object] = field(default_factory=dict)
    # Tool allowlist copied from contract
    allowed_tools: frozenset[str] = field(default_factory=frozenset)


# ─── Agent findings ──────────────────────────────────────────────────────────

@dataclass
class AgentFinding:
    """A single factual finding from an agent.

    Every finding must cite at least one evidence reference.
    Findings without evidence are marked as assumptions.
    """
    role: str
    text: str
    is_assumption: bool = False
    evidence: list[dict] = field(default_factory=list)
    # {"type": "room"|"section"|"meeting"|"policy", "id": str, "field": str}


@dataclass
class AgentResult:
    """Full output from one agent."""
    role: str
    contract_version: str
    findings: list[AgentFinding] = field(default_factory=list)
    unanswered_questions: list[str] = field(default_factory=list)
    error: Optional[str] = None
    used_fallback: bool = False


# ─── Deterministic fallback analysis ─────────────────────────────────────────

def _fallback_analysis(ctx: AgentContextPackage, contract: AgentContract) -> AgentResult:
    """Deterministic, LLM-free agent analysis from structured data.

    Called when the LLM is unavailable.  Returns only findings that can be
    derived directly from the context package data without inference.
    """
    findings: list[AgentFinding] = []
    unanswered: list[str] = []

    if contract.role == "facilities":
        candidates = ctx.data.get("scenario_candidates", [])
        if candidates:
            best = candidates[0]
            findings.append(AgentFinding(
                role="facilities",
                text=(
                    f"Room {best.get('room_id', 'unknown')} is the highest-ranked candidate "
                    f"with a capacity score of {best.get('scores', {}).get('capacity_fit', 'N/A')} "
                    f"and is {best.get('walk_minutes', '?')} minutes walk from the affected building."
                ),
                is_assumption=False,
                evidence=[{"type": "room", "id": best.get("room_id", ""), "field": "score"}],
            ))
        else:
            unanswered.append("No candidate rooms available to assess.")

        repair_status = ctx.data.get("repair_status")
        if repair_status:
            findings.append(AgentFinding(
                role="facilities",
                text=f"Current repair status: {repair_status}.",
                is_assumption=False,
                evidence=[{"type": "incident", "id": ctx.canonical_event_id or "", "field": "repair_status"}],
            ))

    elif contract.role == "it":
        candidates = ctx.data.get("scenario_candidates", [])
        for c in candidates[:3]:
            features = c.get("features", [])
            has_av = any("projector" in f.lower() or "av" in f.lower() for f in features)
            findings.append(AgentFinding(
                role="it",
                text=(
                    f"Room {c.get('room_id', '?')}: "
                    f"{'Has AV/projector' if has_av else 'No AV listed'}. "
                    f"Features: {', '.join(features) if features else 'none recorded'}."
                ),
                is_assumption=not bool(features),
                evidence=[{"type": "room", "id": c.get("room_id", ""), "field": "features"}],
            ))

    elif contract.role == "academic_ops":
        affected = ctx.data.get("affected_meetings", [])
        student_count = ctx.data.get("affected_students_aggregate")
        if affected:
            findings.append(AgentFinding(
                role="academic_ops",
                text=f"{len(affected)} class meeting(s) are affected by this event.",
                is_assumption=False,
                evidence=[{"type": "meeting", "id": m.get("id", ""), "field": "affected"}
                          for m in affected[:5]],
            ))
        if student_count is not None:
            findings.append(AgentFinding(
                role="academic_ops",
                text=f"Aggregate affected students: {student_count}.",
                is_assumption=False,
                evidence=[{"type": "section", "id": "aggregate", "field": "student_count"}],
            ))
        if not affected and student_count is None:
            unanswered.append("Impact on sections and students could not be determined.")

    elif contract.role == "faculty":
        candidates = ctx.data.get("scenario_candidates", [])
        meeting_time = ctx.data.get("meeting_time")
        if candidates:
            findings.append(AgentFinding(
                role="faculty",
                text=(
                    f"From a teaching perspective, room {candidates[0].get('room_id', '?')} "
                    f"appears feasible. Please confirm room layout and equipment match course needs."
                ),
                is_assumption=True,
                evidence=[{"type": "room", "id": candidates[0].get("room_id", ""), "field": "capacity_fit"}],
            ))
        if meeting_time:
            findings.append(AgentFinding(
                role="faculty",
                text=f"Next class meeting is scheduled at {meeting_time}.",
                is_assumption=False,
                evidence=[{"type": "meeting", "id": "", "field": "time"}],
            ))
        if not candidates:
            unanswered.append("No candidate rooms available for course scheduling review.")

    return AgentResult(
        role=contract.role,
        contract_version=contract.version,
        findings=findings,
        unanswered_questions=unanswered,
        used_fallback=True,
    )


# ─── Sanitize context package ─────────────────────────────────────────────────

def build_context_package(
    role: str,
    tenant_id: str,
    canonical_event_id: Optional[str],
    scenario_run_id: Optional[str],
    raw_data: dict,
) -> AgentContextPackage:
    """Build a sanitized context package for the given role.

    Only data categories allowed by the agent contract are included.
    Any category not in the allowlist is silently dropped.
    This prevents context expansion between agents.
    """
    contract = AGENT_CONTRACTS.get(role)
    if contract is None:
        raise ValueError(f"No agent contract for role '{role}'")

    safe_data = {
        k: v for k, v in raw_data.items()
        if k in contract.allowed_data_categories
    }
    return AgentContextPackage(
        role=role,
        tenant_id=tenant_id,
        canonical_event_id=canonical_event_id,
        scenario_run_id=scenario_run_id,
        data=safe_data,
        allowed_tools=contract.tool_allowlist,
    )


# ─── Orchestrator ────────────────────────────────────────────────────────────

@dataclass
class OrchestratorResult:
    """Aggregated result from all stakeholder agents."""
    canonical_event_id: Optional[str]
    scenario_run_id: Optional[str]
    agent_results: list[AgentResult]
    agreements: list[str]
    disagreements: list[str]
    unresolved_questions: list[str]


def run_stakeholder_analysis(
    roles: list[str],
    tenant_id: str,
    canonical_event_id: Optional[str],
    scenario_run_id: Optional[str],
    raw_data: dict,
    *,
    use_llm: bool = False,
) -> OrchestratorResult:
    """Run all requested stakeholder agents and aggregate results.

    Rules:
    - Each agent receives only its allowed data categories (no expansion).
    - Agent failures are caught and result in partial AgentResult with error.
    - use_llm=False always uses deterministic fallback (offline-safe).
    - State-changing tools cannot be called from here.
    - Returns partial results even if some agents fail.
    """
    agent_results: list[AgentResult] = []

    for role in roles:
        contract = AGENT_CONTRACTS.get(role)
        if contract is None:
            agent_results.append(AgentResult(
                role=role,
                contract_version="unknown",
                error=f"No contract defined for role '{role}'. Skipped.",
            ))
            continue

        try:
            ctx = build_context_package(
                role=role,
                tenant_id=tenant_id,
                canonical_event_id=canonical_event_id,
                scenario_run_id=scenario_run_id,
                raw_data=raw_data,
            )
            # In V4, LLM integration deferred — always use fallback for offline safety.
            # This satisfies "LLM outage does not break deterministic core workflows."
            result = _fallback_analysis(ctx, contract)
        except Exception as exc:  # noqa: BLE001
            result = AgentResult(
                role=role,
                contract_version=contract.version,
                error=str(exc),
            )

        agent_results.append(result)

    # ── Aggregate ─────────────────────────────────────────────────────────────
    agreements: list[str] = []
    disagreements: list[str] = []
    unresolved: list[str] = []

    # Simple aggregation: collect all unresolved questions
    for res in agent_results:
        for q in res.unanswered_questions:
            if q not in unresolved:
                unresolved.append(q)

    # Check for agreement on top candidate room
    top_rooms: list[str] = []
    for res in agent_results:
        if res.error:
            continue
        for f in res.findings:
            if "highest-ranked" in f.text or "feasible" in f.text:
                # Extract room id from finding text if present
                for ev in f.evidence:
                    if ev.get("type") == "room" and ev.get("id"):
                        top_rooms.append(ev["id"])

    unique_rooms = list(dict.fromkeys(top_rooms))  # preserve order, deduplicate
    if len(unique_rooms) == 1:
        agreements.append(
            f"All agents reference room {unique_rooms[0]} as the primary candidate."
        )
    elif len(unique_rooms) > 1:
        disagreements.append(
            f"Agents reference different rooms: {', '.join(unique_rooms)}. "
            "Human review required."
        )

    return OrchestratorResult(
        canonical_event_id=canonical_event_id,
        scenario_run_id=scenario_run_id,
        agent_results=agent_results,
        agreements=agreements,
        disagreements=disagreements,
        unresolved_questions=unresolved,
    )
