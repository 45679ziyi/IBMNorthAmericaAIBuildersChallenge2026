#!/usr/bin/env python3
"""Validate a tenant pack (tenant-pack/1). Exit code 0 = valid. No network.

Usage: python tools/validate_tenant_pack.py sample-data/tenants/*.pack.json
Checks: unique ids, referential integrity, no room or instructor double-booking, capacity rules,
walking matrix completeness, valid IANA time zone, scenario sections meet on Tuesday, exactly one feasible
alternative room for the incident, persona and audience consistency, knowledge coverage, synthetic labels.
"""
from __future__ import annotations
import itertools, json, sys
from pathlib import Path
from zoneinfo import ZoneInfo

def hm(s): h, m = s.split(":"); return int(h)*60 + int(m)

def validate(p: dict) -> list[str]:
    errs: list[str] = []
    def need(c, msg):
        if not c: errs.append(msg)
    t = p["tenant"]
    try: ZoneInfo(t["timezone"])
    except Exception: errs.append(f"invalid time zone {t['timezone']}")
    need(p.get("data_origin") == "synthetic" and t.get("data_origin") == "synthetic", "pack and tenant must be labeled synthetic")
    need(t["week_start"] in ("sunday", "monday"), "week_start")
    def ids(key, rows):
        seen = [r["id"] for r in rows]; need(len(seen) == len(set(seen)), f"duplicate ids in {key}"); return set(seen)
    B = ids("buildings", p["buildings"]); R = ids("rooms", p["rooms"]); D = ids("departments", p["departments"]); C = ids("courses", p["courses"]); S = ids("sections", p["sections"])
    ids("services", p["services"]); ids("assets", p["assets"]); ids("teams", p["teams"]); ids("orgs", p["orgs"]); ids("events", p["campus_events"]); ids("knowledge", p["knowledge"])
    fac = ids("faculty", p["people"]["faculty"]); stu = ids("students", p["people"]["students"]); stf = ids("staff", p["people"]["staff"])
    SV = {s["id"] for s in p["services"]}; T = {x["id"] for x in p["teams"]}; O = {x["id"] for x in p["orgs"]}
    # walking matrix
    for a, b in itertools.combinations(sorted(B), 2):
        need(f"{a}-{b}" in p["walking_minutes"] or f"{b}-{a}" in p["walking_minutes"], f"walking minutes missing {a}-{b}")
    need(all(isinstance(v, int) and 1 <= v <= 30 for v in p["walking_minutes"].values()), "walking minutes must be integers 1-30")
    rooms = {r["id"]: r for r in p["rooms"]}
    need(all(r["building_id"] in B for r in rooms.values()), "room.building_id")
    need(all(c["dept_id"] in D for c in p["courses"]), "course.dept_id")
    # sections
    for s in p["sections"]:
        need(s["course_id"] in C, f"section {s['id']} course"); need(s["instructor_id"] in fac, f"section {s['id']} instructor")
        need(s["enrolled"] <= s["capacity"], f"section {s['id']} enrolled > capacity")
        for m in s["meetings"]:
            need(m["room_id"] in R, f"section {s['id']} room"); need(rooms[m["room_id"]]["capacity"] >= s["enrolled"], f"section {s['id']} exceeds room capacity")
            need(hm(m["start"]) < hm(m["end"]), f"section {s['id']} times")
        need(all(x in stu for x in s["roster"]), f"section {s['id']} roster")
        need(len(s["roster"]) <= s["enrolled"], f"section {s['id']} roster larger than headcount")
    # double booking
    meets = [(s["id"], s["instructor_id"], m) for s in p["sections"] for m in s["meetings"]]
    for (s1, i1, m1), (s2, i2, m2) in itertools.combinations(meets, 2):
        if set(m1["days"]) & set(m2["days"]) and hm(m1["start"]) < hm(m2["end"]) and hm(m2["start"]) < hm(m1["end"]):
            need(m1["room_id"] != m2["room_id"], f"room double-booked: {s1} / {s2} in {m1['room_id']}")
            need(i1 != i2, f"instructor double-booked: {s1} / {s2}")
    # teams, memberships, personas
    for tm in p["teams"]:
        need(all(x in stf for x in tm["member_ids"]), f"team {tm['id']} members")
        for b in tm["scope"].get("building_ids", []): need(b in B, f"team {tm['id']} building {b}")
        for sv in tm["scope"].get("service_ids", []): need(sv in SV, f"team {tm['id']} service {sv}")
    for sv in p["services"]:
        need(sv["owner_team_id"] in T, f"service {sv['id']} owner"); need(all(b in B for b in sv["coverage_building_ids"]), f"service {sv['id']} coverage")
    allpeople = fac | stu | stf
    for k, ps in p["personas"].items():
        need(ps["person_id"] in allpeople, f"persona {k} person"); 
        if "team_id" in ps: need(ps["team_id"] in T, f"persona {k} team")
    for m in p["memberships"]:
        need(m["person_id"] in allpeople, f"membership person {m['person_id']}")
        if m.get("team_id"): need(m["team_id"] in T, "membership team")
        if m.get("org_id"): need(m["org_id"] in O, "membership org")
    for ev in p["campus_events"]: need(ev["room_id"] in R, f"event {ev['id']} room")
    for a in p["assets"]:
        need(a["building_id"] in B, f"asset {a['id']} building"); need(a["service_id"] in SV, f"asset {a['id']} service")
    need(len(p["knowledge"]) >= 8, "at least 8 knowledge documents")
    # scenario
    sc = p["scenario"]; secs = {s["id"]: s for s in p["sections"]}
    s1, s2, s3 = (secs[sc["sections"][k]] for k in ("s1", "s2", "s3"))
    for s in (s1, s2, s3): need("Tue" in s["meetings"][0]["days"], f"scenario section {s['id']} must meet on Tuesday")
    need(hm(s1["meetings"][0]["end"]) < hm(s2["meetings"][0]["start"]) < hm(s2["meetings"][0]["end"]) < hm(s3["meetings"][0]["start"]), "scenario sections must be in time order")
    ra, rb, rc = sc["rooms"]["room_a"], sc["rooms"]["room_b"], sc["rooms"]["room_c"]
    need(rooms[ra].get("available") is False, "room_a must be unavailable"); need(rooms[rb]["building_id"] != rooms[ra]["building_id"], "room change must change building")
    need(s2["meetings"][0]["room_id"] == rb, "section s2 must be in room_b (the incident room)")
    # exactly one feasible alternative for s2
    st, en = hm(s2["meetings"][0]["start"]), hm(s2["meetings"][0]["end"])
    def free(room):
        return not any(m["room_id"] == room and "Tue" in m["days"] and hm(m["start"]) < en and st < hm(m["end"]) for s in p["sections"] for m in s["meetings"] if s["id"] != s2["id"])
    feas = [r["id"] for r in rooms.values() if r["kind"] == "classroom" and r.get("available", True) and r["capacity"] >= s2["enrolled"] and r["id"] != rb and free(r["id"])]
    need(feas == [rc], f"expected exactly one feasible alternative room {rc}, found {feas}")
    need(sc["expected"]["impact"]["headcount"] == s1["enrolled"] + s2["enrolled"], "expected headcount")
    # timeline
    times = [hm(e["at"]) for e in sc["timeline"]]; need(times == sorted(times), "timeline must be in time order")
    ev_ids = [e["id"] for e in sc["timeline"]]; need(len(ev_ids) == len(set(ev_ids)), "timeline ids")
    for e in sc["timeline"]:
        if e.get("actor") not in (None, "system"): need(e["actor"] in p["personas"], f"timeline actor {e['actor']}")
    # audiences use only roster members who exist
    for k, aud in sc["expected"]["audiences"].items():
        for grp in ("students",): need(all(x in stu for x in aud.get(grp, [])), f"audience {k} students")
    # persona differentiation: someone must be filtered from the Wi-Fi event
    wifi = sc["expected"]["audiences"]["e07"]; need(len(wifi["not_notified"]) >= 1 and "student_alex" in wifi["students"], "wifi audience")
    # the incident room must be in a building that has an HVAC asset, wifi zone must include the library
    need(any(a["kind"] == "hvac_unit" and a["building_id"] == rooms[rb]["building_id"] for a in p["assets"]), "hvac asset in incident building")
    need(sc["buildings"]["library"] in next(s for s in p["services"] if s["id"] == "svc-wifi")["coverage_building_ids"], "library in wifi zone")
    need(rooms[rb]["building_id"] in next(s for s in p["services"] if s["id"] == "svc-wifi")["coverage_building_ids"], "room_b building in wifi zone (so section s2 is affected)")
    return errs

if __name__ == "__main__":
    bad = 0
    for f in sys.argv[1:]:
        errs = validate(json.loads(Path(f).read_text(encoding="utf-8")))
        print(("OK   " if not errs else "FAIL ") + f)
        for e in errs: print("   -", e)
        bad += bool(errs)
    sys.exit(1 if bad else 0)
