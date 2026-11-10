"""
World dataclass for the AURORA campus intelligence engine.

The World is a pure, immutable snapshot built from the DB on each evaluate()
call. It is NOT stored. All campus wall-clock times on the anchor date.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from typing import Optional

import pytz
from sqlalchemy.orm import Session

from app.core.config import settings

_CAMPUS_TZ = pytz.timezone("America/New_York")
_CAMPUS_OPEN = time(8, 0)
_CAMPUS_CLOSE = time(20, 0)


# ─── Domain dataclasses ───────────────────────────────────────────────────────

@dataclass
class Commitment:
    id: str
    title: str
    course: str
    kind: str               # "class" | "aurora_block"
    start: time             # campus wall time
    end: time               # campus wall time
    room_id: str
    building_id: str
    enrolled: int


@dataclass
class World:
    anchor_date: date
    commitments: list[Commitment]                           # sorted by start
    tasks: list                                             # ORM Task objects
    saved_events: list                                      # ORM CalendarEvent objects
    teammates: list[dict]
    room_availability: dict[str, list[tuple[time, time]]]  # room_id -> slots
    walking_minutes: dict[str, int]                        # both A-B and B-A
    walking_buffer: int
    covered_routes: list[str]                              # "A-B" only (canonical)
    applied_signals: list                                  # ORM Signal, sorted by at_utc
    campus_hours: tuple[time, time]
    buildings: dict[str, dict]                             # id -> {name}
    rooms: dict[str, dict]                                 # id -> {name, capacity, ...}
    scenario: dict                                         # full fixture for engine use

    # ── Helpers ──────────────────────────────────────────────────────────────

    def walk_minutes(self, place_a: str, place_b: str) -> int:
        """Return 0 if same building, else look up the matrix gracefully."""
        if place_a == place_b:
            return 0
        key = f"{place_a}-{place_b}"
        return self.walking_minutes.get(key, 0)

    def is_covered_route(self, place_a: str, place_b: str) -> bool:
        """Return True if the route between two buildings is covered (indoor)."""
        if place_a == place_b:
            return True
        key1 = f"{place_a}-{place_b}"
        key2 = f"{place_b}-{place_a}"
        return key1 in self.covered_routes or key2 in self.covered_routes

    def free_windows(self, now: datetime) -> list[tuple[datetime, datetime]]:
        """
        Compute usable free windows between hard commitments.

        Hard commitments: classes + accepted aurora_blocks.
        Between consecutive commitments the usable window is:
          start = prev_end + buffer (if different building) else + 0; rounded UP to 5 min
          end   = next_start - walk(prev_building, next_building) - buffer; rounded DOWN to 5 min
        Keep only windows >= 30 min, within campus hours.
        """
        campus_open = _CAMPUS_TZ.localize(
            datetime(self.anchor_date.year, self.anchor_date.month, self.anchor_date.day,
                     self.campus_hours[0].hour, self.campus_hours[0].minute)
        )
        campus_close = _CAMPUS_TZ.localize(
            datetime(self.anchor_date.year, self.anchor_date.month, self.anchor_date.day,
                     self.campus_hours[1].hour, self.campus_hours[1].minute)
        )

        # Convert now to campus-aware
        if now.tzinfo is None:
            now_aware = now.replace(tzinfo=timezone.utc).astimezone(_CAMPUS_TZ)
        else:
            now_aware = now.astimezone(_CAMPUS_TZ)

        effective_start = max(campus_open, now_aware)

        # Build sorted commitment list as (start_dt, end_dt, building)
        slots: list[tuple[datetime, datetime, str]] = []
        for c in self.commitments:
            s = _CAMPUS_TZ.localize(
                datetime(self.anchor_date.year, self.anchor_date.month, self.anchor_date.day,
                         c.start.hour, c.start.minute)
            )
            e = _CAMPUS_TZ.localize(
                datetime(self.anchor_date.year, self.anchor_date.month, self.anchor_date.day,
                         c.end.hour, c.end.minute)
            )
            slots.append((s, e, c.building_id))

        slots.sort(key=lambda x: x[0])

        windows: list[tuple[datetime, datetime]] = []

        # ── Window before first commitment ────────────────────────────────
        if slots:
            first_start, first_end, first_bld = slots[0]
            # Walk from effective_start "location" to first class — we don't
            # know the exact prior location here, so we use 0 for the window-
            # start offset (the detectors use start_place from persona).
            w_start = _round_up_5(effective_start)
            # Must arrive at first_start: w_end = first_start − buffer (no walk needed for first window)
            w_end = _round_down_5(first_start - timedelta(minutes=self.walking_buffer))
            if w_end > w_start and (w_end - w_start).total_seconds() >= 1800:
                windows.append((w_start, w_end))
        else:
            # No classes: entire campus hours
            w_start = _round_up_5(effective_start)
            w_end = _round_down_5(campus_close)
            if w_end > w_start and (w_end - w_start).total_seconds() >= 1800:
                windows.append((w_start, w_end))
            return windows

        # ── Windows between consecutive commitments ───────────────────────
        for i in range(len(slots) - 1):
            _, prev_end, prev_bld = slots[i]
            next_start, _, next_bld = slots[i + 1]

            walk = self.walk_minutes(prev_bld, next_bld)
            # Start: after prev_end + buffer if moving buildings, else +0; rounded up to 5 min
            extra_start = self.walking_buffer if prev_bld != next_bld else 0
            w_start = _round_up_5(prev_end + timedelta(minutes=extra_start))

            # End: next_start − walk − buffer; rounded DOWN to 5 min
            w_end = _round_down_5(next_start - timedelta(minutes=walk + self.walking_buffer))

            if w_end > w_start and (w_end - w_start).total_seconds() >= 1800:
                windows.append((w_start, w_end))

        # ── Window after last commitment ──────────────────────────────────
        _, last_end, last_bld = slots[-1]
        w_start = _round_up_5(last_end + timedelta(minutes=self.walking_buffer))
        w_end = _round_down_5(campus_close)
        if w_end > w_start and (w_end - w_start).total_seconds() >= 1800:
            windows.append((w_start, w_end))

        # Filter: only windows >= 30 min and not entirely before now
        return [
            (s, e) for (s, e) in windows
            if e > effective_start and (e - s).total_seconds() >= 1800
        ]


# ─── Rounding helpers ─────────────────────────────────────────────────────────

def _round_up_5(dt: datetime) -> datetime:
    """Round a datetime UP to the nearest 5 minutes."""
    minutes = dt.hour * 60 + dt.minute
    remainder = minutes % 5
    if remainder == 0 and dt.second == 0 and dt.microsecond == 0:
        return dt.replace(second=0, microsecond=0)
    add = (5 - remainder) % 5
    if add == 0:
        add = 5 if (dt.second > 0 or dt.microsecond > 0) else 0
    result = dt.replace(second=0, microsecond=0) + timedelta(minutes=add)
    return result


def _round_down_5(dt: datetime) -> datetime:
    """Round a datetime DOWN to the nearest 5 minutes."""
    minutes = dt.hour * 60 + dt.minute
    remainder = minutes % 5
    return dt.replace(minute=(minutes - remainder) % 60,
                      hour=(minutes - remainder) // 60,
                      second=0, microsecond=0)


# ─── Builder ──────────────────────────────────────────────────────────────────

def build_world(db: Session) -> Optional[World]:
    """
    Build the World from the database and the loaded scenario.
    Returns None if not in scenario mode.
    """
    from app.models.models import CalendarEvent, Signal, SimState, Task
    from app.services.campus.scenario import load_scenario

    state = db.get(SimState, 1)
    if state is None or state.mode != "scenario" or not state.scenario_id:
        return None

    scenario = load_scenario(state.scenario_id)
    anchor = date.fromisoformat(state.anchor_date)
    user_id = settings.demo_user_id

    # ── Walking matrix (both directions) ──────────────────────────────────
    walking: dict[str, int] = {}
    for key, minutes in scenario.get("walking_minutes", {}).items():
        a, b = key.split("-")
        walking[f"{a}-{b}"] = minutes
        walking[f"{b}-{a}"] = minutes

    # ── Buildings ─────────────────────────────────────────────────────────
    buildings: dict[str, dict] = {b["id"]: b for b in scenario.get("buildings", [])}

    # ── Rooms ─────────────────────────────────────────────────────────────
    rooms: dict[str, dict] = {r["id"]: r for r in scenario.get("rooms", [])}

    # ── Commitments from CalendarEvent rows on anchor date ────────────────
    anchor_start = _local_to_utc(anchor, time(0, 0))
    anchor_end = _local_to_utc(anchor, time(23, 59))

    class_events = (
        db.query(CalendarEvent)
        .filter(
            CalendarEvent.user_id == user_id,
            CalendarEvent.event_type == "class",
            CalendarEvent.source_type.in_(["scenario", "aurora_block"]),
            CalendarEvent.start_at_utc >= anchor_start.replace(tzinfo=None),
            CalendarEvent.start_at_utc <= anchor_end.replace(tzinfo=None),
        )
        .all()
    )

    commitments: list[Commitment] = []
    for ev in class_events:
        # Convert UTC → campus wall time
        start_local = _utc_to_local(ev.start_at_utc)
        end_local = _utc_to_local(ev.end_at_utc)

        # Determine room/building
        room_id = ev.location_text or ""
        # location_text might be a room name like "Javits 101" or room id like "JAV-101"
        # Normalize: try to find by name first, then by id
        actual_room_id = _resolve_room_id(room_id, rooms)
        building_id = _building_from_room(actual_room_id, rooms)

        kind = "aurora_block" if ev.source_type == "aurora_block" else "class"
        commitments.append(Commitment(
            id=ev.source_reference or ev.id,
            title=ev.title,
            course=ev.description.replace("Course: ", "") if ev.description else "",
            kind=kind,
            start=start_local.time(),
            end=end_local.time(),
            room_id=actual_room_id,
            building_id=building_id,
            enrolled=_enrolled_from_scenario(scenario, ev.source_reference or ""),
        ))

    commitments.sort(key=lambda c: c.start)

    # ── Tasks ─────────────────────────────────────────────────────────────
    # D1 fix: during a scenario, only use tasks seeded by the scenario
    # (provenance='scenario') or explicitly approved from connectors.
    # Exclude source_type='demo' tasks (legacy seed data) which have
    # absolute due dates that pre-date the scenario and generate spurious
    # deadline_risk moves such as "deadline:task-demo-*".
    tasks = (
        db.query(Task)
        .filter(
            Task.user_id == user_id,
            Task.status != "done",
            Task.source_type.notin_(["demo"]),
        )
        .all()
    )

    # ── Saved events (non-class calendar events on anchor date) ───────────
    saved_events = (
        db.query(CalendarEvent)
        .filter(
            CalendarEvent.user_id == user_id,
            CalendarEvent.source_type == "scenario",
            CalendarEvent.event_type != "class",
        )
        .all()
    )

    # ── Applied signals ───────────────────────────────────────────────────
    applied_signals = (
        db.query(Signal)
        .order_by(Signal.at_utc)
        .all()
    )

    # ── Room availability from scenario fixture ────────────────────────────
    room_avail: dict[str, list[tuple[time, time]]] = {}
    for room_id, slots in scenario.get("room_availability", {}).items():
        parsed = []
        for slot in slots:
            h0, m0 = map(int, slot[0].split(":"))
            h1, m1 = map(int, slot[1].split(":"))
            parsed.append((time(h0, m0), time(h1, m1)))
        room_avail[room_id] = parsed

    # ── Campus hours ──────────────────────────────────────────────────────
    day = scenario.get("day", {})
    open_h, open_m = map(int, day.get("campus_open", "08:00").split(":"))
    close_h, close_m = map(int, day.get("campus_close", "20:00").split(":"))
    campus_hours = (time(open_h, open_m), time(close_h, close_m))

    return World(
        anchor_date=anchor,
        commitments=commitments,
        tasks=list(tasks),
        saved_events=list(saved_events),
        teammates=scenario.get("teammates", []),
        room_availability=room_avail,
        walking_minutes=walking,
        walking_buffer=scenario.get("walking_buffer_minutes", 3),
        covered_routes=scenario.get("covered_routes", []),
        applied_signals=applied_signals,
        campus_hours=campus_hours,
        buildings=buildings,
        rooms=rooms,
        scenario=scenario,
    )


# ─── Internal helpers ─────────────────────────────────────────────────────────

def _local_to_utc(anchor: date, t: time) -> datetime:
    local_dt = _CAMPUS_TZ.localize(datetime(anchor.year, anchor.month, anchor.day, t.hour, t.minute))
    return local_dt.astimezone(timezone.utc)


def _utc_to_local(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(_CAMPUS_TZ)


def _resolve_room_id(location_text: str, rooms: dict[str, dict]) -> str:
    """Try to resolve a room name or id to the canonical room id."""
    if location_text in rooms:
        return location_text
    for rid, rdata in rooms.items():
        if rdata.get("name", "") == location_text:
            return rid
    # Fall back: try to extract building prefix from "JAV-101" style
    return location_text


def _building_from_room(room_id: str, rooms: dict[str, dict]) -> str:
    """Extract building id from room data or room_id."""
    if room_id in rooms:
        bld = rooms[room_id].get("building", "")
        if bld:
            return bld
    # Heuristic: first segment before '-'
    if "-" in room_id:
        return room_id.split("-")[0]
    return room_id


def _enrolled_from_scenario(scenario: dict, commitment_id: str) -> int:
    for c in scenario.get("commitments", []):
        if c["id"] == commitment_id:
            return c.get("enrolled", 0)
    return 0
