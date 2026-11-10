#!/usr/bin/env python3
"""Deterministic synthetic-university generator for AURORA.

Usage:  python tools/generate_tenant_pack.py --all --out sample-data/tenants
Every record is FICTIONAL. Same seed -> byte-identical output. No network, no real data.
"""
from __future__ import annotations
import argparse, hashlib, json, math, random
from datetime import date, timedelta
from pathlib import Path

DISCIPLINES = [  # key, title, 4 course titles
 ("cs", "Computer Science", ["Programming Fundamentals", "Data Structures", "Software Development", "Operating Systems"]),
 ("math", "Mathematics", ["Calculus I", "Calculus III", "Linear Algebra", "Probability"]),
 ("phys", "Physics", ["Mechanics", "Electricity and Magnetism", "Thermodynamics", "Quantum Physics"]),
 ("bio", "Biology", ["Cell Biology", "Genetics", "Ecology", "Physiology"]),
 ("econ", "Economics", ["Principles of Economics", "Microeconomics", "Econometrics", "Public Policy"]),
 ("writ", "Writing and Humanities", ["Academic Writing", "Rhetoric", "World Literature", "Ethics"]),
]
FIRST = ["Alex","Jordan","Morgan","Casey","Taylor","Riley","Sam","Priya","Marcus","Dana","Noor","Mateo","Lena","Kofi","Mei","Omar","Ines","Ravi","Tomas","Yara","Elif","Jonas","Aiko","Zara","Luca","Nia","Hugo","Sana","Theo","Amara"]
LAST = ["Whitaker","Okafor","Lindqvist","Moreau","Tanaka","Haddad","Castillo","Novak","Brennan","Sato","Varga","Mensah","Petrov","Duarte","Kowalski","Ibrahim","Larsen","Fontaine","Reyes","Schaefer","Adeyemi","Quinn","Rossi","Nakamura","Bergstrom","Chaudhry","Halvorsen","Mbeki","Ortega","Vance"]

PROFILES = {
 "sbu_demo": dict(
  name="SBU Demo University", short="SBU Demo", tz="America/New_York", locale="en-US", week_start="sunday", clock="12h",
  term_system="semester", term_name="Fall 2026", term=(date(2026,8,31), date(2026,12,18)), finals=(date(2026,12,14), date(2026,12,21)),
  add_drop=date(2026,9,14), withdraw=date(2026,11,6), break_=(date(2026,11,25), date(2026,11,29)), credit_unit="credits",
  dept_codes=["CSE","MAT","PHY","BIO","ECO","WRT"], code_fmt="{d} {n}", course_nums=[[101,214,316,320],[125,203,211,230],[131,132,133,251],[201,202,320,332],[108,201,301,305],[101,102,205,220]],
  room_fmt="{b} {r}", slots=["08:30-09:50","10:00-11:20","12:30-13:50","15:00-16:20","16:30-17:50"], mwf_start=["09:00","10:00","11:00","13:00","14:00"], mwf_len=50,
  roles={"faculty":"Instructor","acadops":"Academic Operations","facilities":"Facilities","it":"IT Service Desk","advising":"Advising"},
  buildings=[("LE","Light Engineering (demo)","academic",(0,0)),("CS","Computer Science Building (demo)","academic",(4,0)),("MEL","Melville Library (demo)","library",(8,3)),
             ("SAC","Student Activities Center (demo)","student",(7,6)),("JAV","Javits Lecture Center (demo)","academic",(5,4)),
             ("HUM","Humanities Hall (demo)","academic",(2,7)),("CHM","Chemistry Wing (demo)","academic",(0,4)),("REC","Recreation Center (demo)","recreation",(10,8)),("RES","Residential Commons (demo)","residential",(12,2))],
  covered=[("MEL","SAC")], wifi_zone=["JAV","MEL"], scen=dict(a="LE", b="JAV", c="CS", lib="MEL", event="SAC"),
  walk_override={("LE","CS"):4,("LE","MEL"):8,("LE","SAC"):7,("LE","JAV"):6,("CS","MEL"):9,("CS","SAC"):8,("CS","JAV"):5,("MEL","SAC"):5,("MEL","JAV"):6,("SAC","JAV"):8},
 ),
 "northbridge_demo": dict(
  name="Northbridge University (Demo)", short="Northbridge Demo", tz="America/Chicago", locale="en-US", week_start="monday", clock="12h",
  term_system="semester", term_name="Fall 2026", term=(date(2026,8,24), date(2026,12,11)), finals=(date(2026,12,7), date(2026,12,12)),
  add_drop=date(2026,9,4), withdraw=date(2026,10,30), break_=(date(2026,11,25), date(2026,11,29)), credit_unit="credit hours",
  dept_codes=["COMP","MATH","PHYS","BIOL","ECON","ENGL"], code_fmt="{d}-{n}", course_nums=[[1010,1210,2140,3320],[1110,2210,2310,3150],[1040,2060,2250,3010],[1020,2020,2120,3200],[1010,2010,3010,3300],[1000,1100,2050,2200]],
  room_fmt="{b} {r}", slots=["08:00-09:15","09:30-10:45","12:00-13:15","14:30-15:45"], mwf_start=["08:00","09:00","10:00","12:00","13:00"], mwf_len=50,
  roles={"faculty":"Professor","acadops":"Registrar Scheduling","facilities":"Physical Plant","it":"Technology Services","advising":"Student Success"},
  buildings=[("LKS","Lakeshore Hall (demo)","academic",(0,0)),("INN","Innovation Center (demo)","academic",(5,1)),("PRL","Prairie Library (demo)","library",(9,4)),
             ("UNC","Union Commons (demo)","student",(7,7)),("FND","Foundry Engineering (demo)","academic",(4,5)),("HAW","Hawthorne Science (demo)","academic",(1,6)),
             ("ART","Arts Pavilion (demo)","academic",(11,1)),("ATH","Athletic Center (demo)","recreation",(12,8)),("RSC","Residence Court (demo)","residential",(3,10))],
  covered=[("PRL","UNC")], wifi_zone=["FND","PRL"], scen=dict(a="LKS", b="FND", c="INN", lib="PRL", event="UNC"), walk_override={},
 ),
 "pacific_demo": dict(
  name="Pacific Coast University (Demo)", short="Pacific Demo", tz="America/Los_Angeles", locale="en-US", week_start="sunday", clock="12h",
  term_system="quarter", term_name="Fall Quarter 2026", term=(date(2026,9,24), date(2026,12,11)), finals=(date(2026,12,7), date(2026,12,12)),
  add_drop=date(2026,10,9), withdraw=date(2026,11,13), break_=(date(2026,11,25), date(2026,11,29)), credit_unit="units",
  dept_codes=["CS","MATH","PHYS","LIFESCI","ECON","WRIT"], code_fmt="{d} {n}", course_nums=[[31,32,33,111],[31,32,33,115],[1,5,110,112],[7,23,107,120],[1,11,101,106],[1,2,15,120]],
  room_fmt="{b}-{r}", slots=["09:00-10:20","11:00-12:20","13:30-14:50","16:00-17:20"], mwf_start=["08:00","09:00","10:00","13:00","14:00"], mwf_len=50,
  roles={"faculty":"Faculty","acadops":"Academic Scheduling","facilities":"Facilities Services","it":"IT Help Center","advising":"Academic Advising"},
  buildings=[("RWD","Redwood Hall (demo)","academic",(0,0)),("TPL","Tidepool Lab (demo)","academic",(4,2)),("SLB","Sunset Library (demo)","library",(8,5)),
             ("KSC","Kelp Student Center (demo)","student",(6,8)),("RDG","Ridge Engineering (demo)","academic",(3,6)),("PLM","Palm Court Lecture Hall (demo)","academic",(10,2)),
             ("BLF","Bluff Humanities (demo)","academic",(1,9)),("HRB","Harbor Rec (demo)","recreation",(12,9)),("CNY","Canyon Residences (demo)","residential",(13,4))],
  covered=[("SLB","KSC")], wifi_zone=["PLM","SLB"], scen=dict(a="RWD", b="PLM", c="RDG", lib="SLB", event="KSC"), walk_override={},
 ),
 "rhine_demo": dict(
  name="Rhine Valley University (Demo)", short="Rhine Demo", tz="Europe/Berlin", locale="en-GB", week_start="monday", clock="24h",
  term_system="semester", term_name="Winter Semester 2026/27", term=(date(2026,10,12), date(2027,2,12)), finals=(date(2027,2,1), date(2027,2,20)),
  add_drop=date(2026,10,30), withdraw=date(2026,12,11), break_=(date(2026,12,23), date(2027,1,6)), credit_unit="ECTS",
  dept_codes=["INF","MAT","PHY","BIO","VWL","SPR"], code_fmt="{d}-{n}", course_nums=[[101,201,301,401],[101,201,211,311],[101,102,201,301],[101,201,205,305],[101,201,301,303],[101,102,201,301]],
  room_fmt="{b}/{r}", slots=["08:15-09:45","10:15-11:45","12:15-13:45","14:15-15:45"], mwf_start=["08:00","09:00","10:00","12:00","13:00"], mwf_len=50,
  roles={"faculty":"Lecturer","acadops":"Examinations and Timetabling","facilities":"Building Services","it":"Computing Centre","advising":"Student Advisory"},
  buildings=[("HOR","Lecture Hall Complex (demo)","academic",(0,0)),("INF","Informatics Building (demo)","academic",(5,2)),("BIB","University Library (demo)","library",(9,5)),
             ("MEN","Refectory and Student Hub (demo)","student",(7,8)),("NAT","Natural Sciences Building (demo)","academic",(3,6)),("TEC","Technology Hall (demo)","academic",(11,2)),
             ("GEI","Humanities Building (demo)","academic",(1,9)),("SPO","Sports Hall (demo)","recreation",(13,9)),("WOH","Residence Quarter (demo)","residential",(14,4))],
  covered=[("BIB","MEN")], wifi_zone=["TEC","BIB"], scen=dict(a="HOR", b="TEC", c="INF", lib="BIB", event="MEN"), walk_override={},
 ),
}

def hm(s): h,m = s.split(":"); return int(h)*60+int(m)
def fm(m): return f"{m//60:02d}:{m%60:02d}"
DAY_NAMES = ["Mon","Tue","Wed","Thu","Fri"]

def build(tid: str, seed: int = 2026) -> dict:
    P = PROFILES[tid]
    rng = random.Random(f"{tid}|{seed}")
    names = [f"{f} {l}" for f in FIRST for l in LAST]; rng.shuffle(names); name_it = iter(names)
    def pname(): return next(name_it)

    # --- campus, buildings, walking
    blds = []
    for code, nm, kind, (x, y) in P["buildings"]:
        blds.append(dict(id=code, code=code, name=nm, campus_id="main", kind=kind, floors=rng.choice([2,3,4]) if kind!="residential" else 5, x=x, y=y))
    walk = {}
    for i, a in enumerate(blds):
        for b in blds[i+1:]:
            key = f"{a['id']}-{b['id']}"
            ov = P["walk_override"].get((a["id"], b["id"])) or P["walk_override"].get((b["id"], a["id"]))
            walk[key] = ov if ov else max(3, round(math.hypot(a["x"]-b["x"], a["y"]-b["y"]) * 1.05))
    S = P["scen"]
    covered = [f"{a}-{b}" for a, b in P["covered"]]

    # --- rooms
    rooms = []
    def add_room(bid, num, cap, kind, bookable=False, floor=1, feats=()):
        rooms.append(dict(id=f"{bid}-{num}", building_id=bid, floor=floor, name=P["room_fmt"].format(b=bid, r=num), capacity=cap, kind=kind, bookable=bookable, features=list(feats)))
    for b in blds:
        if b["kind"] == "academic":
            for k, cap in enumerate([30, 45, 60, 40, 24]):
                add_room(b["id"], 100 + k + 1 + (b["floors"] > 2) * 200, cap, "classroom", feats=["projector"], floor=1 + (k > 2))
            add_room(b["id"], 150, 28, "lab", feats=["lab-computers"])
        elif b["kind"] == "library":
            for k in range(4): add_room(b["id"], f"SR{k+1}", rng.choice([4, 6, 8, 8]), "study_room", bookable=True, floor=2, feats=["whiteboard"])
        elif b["kind"] == "student":
            add_room(b["id"], "BALL", 400, "event_space"); add_room(b["id"], "MTG1", 30, "meeting_room", bookable=True)
    # two large lecture rooms: the scenario room B (incident) and its only feasible alternative
    big = {}
    for key, bid in (("b", S["b"]), ("c", S["c"])):
        rid = f"{bid}-LH{'1' if key=='b' else '2'}"
        rooms.append(dict(id=rid, building_id=bid, floor=1, name=P["room_fmt"].format(b=bid, r=f"LH{'1' if key=='b' else '2'}"), capacity=120, kind="classroom", bookable=False, features=["projector", "lecture-capture"]))
        big[key] = rid
    # the room S1 starts in, deliberately unavailable (projector replacement) so the room change is forced
    rooms.append(dict(id=f"{S['a']}-201", building_id=S["a"], floor=2, name=P["room_fmt"].format(b=S["a"], r=201), capacity=80, kind="classroom", bookable=False,
                      features=["projector-under-replacement"], available=False, unavailable_reason="Projector replacement"))
    ra = rooms[-1]
    for r in rooms: r.setdefault("available", True)
    roomd = {r["id"]: r for r in rooms}

    # --- departments, courses
    depts, courses = [], []
    for (key, title, titles), code, nums in zip(DISCIPLINES, P["dept_codes"], P["course_nums"]):
        depts.append(dict(id=code, code=code, name=title))
        for t, n in zip(titles, nums):
            courses.append(dict(id=f"{code}-{n}", dept_id=code, code=P["code_fmt"].format(d=code, n=n), title=t, credits=rng.choice([3, 3, 4]) if P["credit_unit"] != "ECTS" else rng.choice([5, 6, 6, 8])))
    cby = {c["id"]: c for c in courses}

    # --- people
    people = dict(students=[], faculty=[], staff=[])
    fac_of = {}
    for d in depts:
        for _ in range(2):
            pid = f"fac-{len(people['faculty'])+1:02d}"; people["faculty"].append(dict(id=pid, display=pname(), dept_id=d["id"], title=P["roles"]["faculty"])); fac_of.setdefault(d["id"], []).append(pid)
    # --- scenario sections (fixed slots, guaranteed Tuesday)
    slots = [tuple(s.split("-")) for s in P["slots"]]
    s1s, s2s, s3s = slots[1], slots[2], slots[3] if len(slots) > 3 else slots[-1]
    cs_courses = [c for c in courses if c["dept_id"] == P["dept_codes"][0]]; ma_courses = [c for c in courses if c["dept_id"] == P["dept_codes"][1]]
    j_id, j2_id = fac_of[P["dept_codes"][0]][0], fac_of[P["dept_codes"][1]][0]
    sections = []
    def sec(cid, code, inst, enrolled, mt, room, days, tags):
        cap = max(enrolled, roomd[room]["capacity"]) if roomd[room]["capacity"] >= enrolled else enrolled
        sections.append(dict(id=f"{cid}-{code}", course_id=cid, section_code=code, term=P["term_name"], instructor_id=inst, enrolled=enrolled, capacity=min(cap, roomd[room]["capacity"]) if roomd[room]["capacity"] >= enrolled else enrolled,
                             meetings=[dict(days=days, start=mt[0], end=mt[1], room_id=room)], roster=[], tags=tags))
    TR = ["Tue", "Thu"]
    s1_room = ra["id"]
    sec(cs_courses[1]["id"], "01", j_id, 78, s1s, s1_room, TR, ["scenario", "s1"])
    sec(ma_courses[1]["id"], "01", j2_id, 90, s2s, big["b"], TR, ["scenario", "s2"])
    sec(cs_courses[2]["id"], "01", fac_of[P["dept_codes"][0]][1], 45, s3s, next(r["id"] for r in rooms if r["building_id"] == S["c"] and r["capacity"] == 45), TR, ["scenario", "s3"])
    # --- base sections (no conflicts, never use the two lecture halls or the scenario slots on Tue/Thu)
    def busy(room, days, st, en):
        for s in sections:
            for m in s["meetings"]:
                if m["room_id"] == room and set(m["days"]) & set(days) and hm(m["start"]) < en and st < hm(m["end"]): return True
        return False
    def ibusy(inst, days, st, en):
        for s in sections:
            for m in s["meetings"]:
                if s["instructor_id"] == inst and set(m["days"]) & set(days) and hm(m["start"]) < en and st < hm(m["end"]): return True
        return False
    classrooms = [r for r in rooms if r["kind"] == "classroom" and r["id"] not in big.values() and r["available"]]
    for c in courses:
        if any(s["course_id"] == c["id"] for s in sections): continue
        for sc in ("01", "02") if rng.random() < 0.35 else ("01",):
            for attempt in range(40):
                pat = rng.choice(["TR", "MWF"]); enrolled = rng.choice([18, 22, 26, 30, 34, 38, 42])
                if pat == "TR": days = TR; st, en = [hm(x) for x in rng.choice(slots)]
                else: days = ["Mon", "Wed", "Fri"]; s0 = hm(rng.choice(P["mwf_start"])); st, en = s0, s0 + P["mwf_len"]
                inst = rng.choice(fac_of[c["dept_id"]]); fits = [r for r in classrooms if r["capacity"] >= enrolled and not busy(r["id"], days, st, en)]
                if fits and not ibusy(inst, days, st, en):
                    r = rng.choice(fits); sec(c["id"], sc, inst, enrolled, (fm(st), fm(en)), r["id"], days, []); break

    # --- demo students + personas
    scen_secs = {t: next(s for s in sections if t in s["tags"]) for t in ("s1", "s2", "s3")}
    def add_student(pid, display, program): people["students"].append(dict(id=pid, display=display, program=program))
    personas = {}
    for key, nm, secs, prog in (("student_alex", "Alex Student (demo)", ("s1", "s2", "s3"), "Computer Science"), ("student_blake", "Blake Student (demo)", ("s1",), "Mathematics"),
                                ("student_casey", "Casey Student (demo)", ("s2", "s3"), "Physics"), ("student_dana", "Dana Student (demo)", ("s3",), "Biology")):
        add_student(key, nm, prog); personas[key] = dict(person_id=key, role="student", display=nm)
        for t in secs: scen_secs[t]["roster"].append(key)
    for t, n in (("s1", 8), ("s2", 8), ("s3", 6)):
        for _ in range(n):
            pid = f"stu-{len(people['students'])+1:03d}"; add_student(pid, pname(), rng.choice(["Computer Science", "Mathematics", "Biology", "Economics"])); scen_secs[t]["roster"].append(pid)
    # --- staff, teams
    teams, memberships = [], []
    def staff(role, team_label, scope, display_hint=None, persona=None):
        pid = f"stf-{len(people['staff'])+1:02d}"; disp = display_hint or pname()
        people["staff"].append(dict(id=pid, display=disp, role=role)); tid_ = f"team-{role}-{len([t for t in teams if t['role']==role])+1}"
        teams.append(dict(id=tid_, role=role, name=team_label, scope=scope, member_ids=[pid]))
        memberships.append(dict(person_id=pid, role=role, team_id=tid_)); 
        if persona: personas[persona] = dict(person_id=pid, role=role, display=disp, team_id=tid_)
        return pid
    other_blds = [b["id"] for b in blds if b["id"] not in (S["a"], S["b"])]
    staff("facilities", f"{P['roles']['facilities']}: academic core", dict(building_ids=[S["a"], S["b"], S["c"]]), "Morgan Facilities (demo)", "facilities_morgan")
    staff("facilities", f"{P['roles']['facilities']}: other buildings", dict(building_ids=other_blds))
    zone = P["wifi_zone"]
    staff("it", f"{P['roles']['it']}: campus network", dict(service_ids=["svc-wifi"], building_ids=zone), "Casey IT (demo)", "it_casey")
    staff("it", f"{P['roles']['it']}: teaching technology", dict(service_ids=["svc-lms", "svc-av"]))
    staff("academic_ops", P["roles"]["acadops"], dict(department_ids=[d["id"] for d in depts]), "Taylor Academic Ops (demo)", "acadops_taylor")
    staff("advising", P["roles"]["advising"], dict(department_ids=[d["id"] for d in depts]))
    for key, nm, fid in (("faculty_jordan", "Jordan Instructor (demo)", j_id), ("faculty_sam", "Sam Instructor (demo)", j2_id)):
        for f in people["faculty"]:
            if f["id"] == fid: f["display"] = nm
        personas[key] = dict(person_id=fid, role="faculty", display=nm)
        memberships.append(dict(person_id=fid, role="faculty"))
    # --- orgs + events
    orgs = [dict(id=f"org-{i+1}", name=n, advisor_id=rng.choice(people["faculty"])["id"]) for i, n in enumerate(["Robotics Club", "Career Network", "Debate Society", "Sustainability Collective", "Game Design Guild", "Global Students Association"])]
    personas["org_riley"] = dict(person_id="stu-org-riley", role="org_organizer", display="Riley Organizer (demo)", org_id="org-2")
    add_student("stu-org-riley", "Riley Organizer (demo)", "Economics"); memberships.append(dict(person_id="stu-org-riley", role="org_organizer", org_id="org-2"))
    t0 = P["term"][0]
    events = []
    titles = ["Fall Career Fair", "Research Showcase", "Open Mic Night", "Hack Night", "Sustainability Talk", "Study Skills Workshop", "Club Fair", "Film Screening", "Guest Lecture", "Alumni Panel", "Game Night", "Wellness Walk"]
    for i, t in enumerate(titles):
        d = P["term"][0] + timedelta(days=7*(2+i//2)+i%3+1)
        events.append(dict(id=f"ev-{i+1:02d}", title=t, org_id=orgs[i % len(orgs)]["id"], room_id=(f"{S['event']}-BALL"), date=d.isoformat(), start=rng.choice(["12:00", "14:00", "18:00", "19:00"]), duration_min=rng.choice([60, 90, 120])))
    fair = events[0]; fair.update(id="ev-fair", title="Fall Career Fair", org_id="org-2", start="14:00", duration_min=180, day_offset_from_anchor=2)

    # --- services, assets
    services = [dict(id="svc-wifi", name="Campus Wi-Fi", kind="network", owner_team_id=next(t["id"] for t in teams if t["role"] == "it" and "svc-wifi" in t["scope"].get("service_ids", [])), coverage_building_ids=zone, zone="zone-1"),
                dict(id="svc-lms", name="Learning Platform", kind="lms", owner_team_id=next(t["id"] for t in teams if t["role"] == "it" and "svc-lms" in t["scope"].get("service_ids", [])), coverage_building_ids=[b["id"] for b in blds]),
                dict(id="svc-av", name="Classroom AV", kind="av", owner_team_id=next(t["id"] for t in teams if t["role"] == "it" and "svc-av" in t["scope"].get("service_ids", [])), coverage_building_ids=[b["id"] for b in blds if b["kind"] == "academic"]),
                dict(id="svc-print", name="Print Services", kind="print", owner_team_id=next(t["id"] for t in teams if t["role"] == "it" and "svc-lms" in t["scope"].get("service_ids", [])), coverage_building_ids=[b["id"] for b in blds if b["kind"] in ("library", "student")]),
                dict(id="svc-hvac", name="Building Climate Systems", kind="hvac", owner_team_id=teams[0]["id"], coverage_building_ids=[b["id"] for b in blds]),
                dict(id="svc-capture", name="Lecture Capture", kind="av", owner_team_id=next(t["id"] for t in teams if t["role"] == "it" and "svc-av" in t["scope"].get("service_ids", [])), coverage_building_ids=[S["b"], S["c"]])]
    assets = []
    for b in blds:
        assets.append(dict(id=f"hvac-{b['id']}-1", kind="hvac_unit", building_id=b["id"], service_id="svc-hvac"))
        for f in range(1, min(b["floors"], 3)+1): assets.append(dict(id=f"ap-{b['id']}-{f}", kind="wifi_ap", building_id=b["id"], floor=f, service_id="svc-wifi"))
    for r in rooms:
        if "projector" in r["features"] or "projector-under-replacement" in r["features"]: assets.append(dict(id=f"proj-{r['id']}", kind="projector", building_id=r["building_id"], room_id=r["id"], service_id="svc-av"))

    # --- knowledge (tenant-specific, public-type)
    A, W = P["add_drop"].strftime("%B %d").replace(" 0", " "), P["withdraw"].strftime("%B %d").replace(" 0", " ")
    fin = f"{P['finals'][0].strftime('%B %d').replace(' 0',' ')} to {P['finals'][1].strftime('%B %d').replace(' 0',' ')}"
    unit = P["credit_unit"]
    knowledge = [
     ("kd-addrop", "Add and drop deadlines", "Registrar (demo)", f"The last day to add or drop a course without a transcript notation is {A}. The last day to withdraw from a course is {W}. Dates apply to the {P['term_name']} term. Check with Academic Operations for exceptions."),
     ("kd-finals", "Final examination period", "Registrar (demo)", f"Final examinations for {P['term_name']} run from {fin}. The examination timetable is published by {P['roles']['acadops']}. Conflicts must be reported before the add and drop deadline."),
     ("kd-credits", "Credit load policy", "Registrar (demo)", f"A full-time load is 12 {unit} or more in a {P['term_system']} term. Taking more than 18 {unit} requires advisor approval. Course {unit} are shown beside each course title."),
     ("kd-library", "Library hours and study rooms", "Library (demo)", f"The library is open 08:00 to 22:00 on weekdays. Group study rooms seat 4 to 8 people and can be reserved for up to 2 hours per day. Quiet floors are marked at the entrance."),
     ("kd-wifi", "Wi-Fi and technology help", f"{P['roles']['it']} (demo)", f"Report Wi-Fi or classroom technology problems to the {P['roles']['it']}. Include the building, the room and the time. Outages are posted on the service status page."),
     ("kd-facilities", "Reporting a building or room problem", f"{P['roles']['facilities']} (demo)", f"Report heating, cooling, lighting, or accessibility problems to {P['roles']['facilities']} with the building and room. Urgent safety issues must be reported to campus safety instead."),
     ("kd-parking", "Parking and transportation", "Transportation (demo)", f"Student parking permits are sold online for the {P['term_name']} term. Campus shuttles run every 15 minutes on weekdays. Bicycle racks are located at each residence and the library."),
     ("kd-accessibility", "Accessibility and accommodations", "Accessibility Services (demo)", f"Students who need academic accommodations should contact Accessibility Services early in the term. Instructors receive accommodation letters through the official process, not from students directly."),
    ]
    knowledge = [dict(id=i, title=t, publisher=pub, text=txt, tags=["public", "demo"], data_origin="synthetic") for i, t, pub, txt in knowledge]

    # --- term calendar
    tm = P["term"]; terms = [dict(id="term-current", name=P["term_name"], system=P["term_system"], start=tm[0].isoformat(), end=tm[1].isoformat(), finals_start=P["finals"][0].isoformat(), finals_end=P["finals"][1].isoformat(),
                                  add_drop_deadline=P["add_drop"].isoformat(), withdraw_deadline=P["withdraw"].isoformat(), break_start=P["break_"][0].isoformat(), break_end=P["break_"][1].isoformat(),
                                  weeks=10 if P["term_system"] == "quarter" else 15)]
    # --- scenario: intent-level timeline (local times); same story in every tenant, different people, places and clocks
    s1, s2, s3 = scen_secs["s1"], scen_secs["s2"], scen_secs["s3"]
    st1 = hm(s1["meetings"][0]["start"]); st2 = hm(s2["meetings"][0]["start"]); st3 = hm(s3["meetings"][0]["start"])
    # ids for every external object the story touches
    alt_room = big["c"]; room_b = big["b"]
    def at(m): return fm(max(m, 7*60+30))
    timeline = [
     dict(id="e00", at="07:30", kind="morning_sync", summary="Schedules, deadlines, saved events and service status load for all roles"),
     dict(id="e01", at=at(8*60+5), kind="faculty_course_update_drafted", actor="faculty_jordan", entity=dict(section_id=s1["id"]), payload=dict(text="Assignment 3 is due Thursday at 17:00. Late work loses 10% per day.", extracted=dict(due_day_offset=2, due_time="17:00")), autopilot=True),
     dict(id="e02", at=at(8*60+10), kind="faculty_course_update_approved", actor="faculty_jordan", entity=dict(section_id=s1["id"]), payload=dict(draft_ref="e01"), autopilot=True),
     dict(id="e03", at=fm(st1-50), kind="room_change_posted", actor="acadops_taylor", entity=dict(section_id=s1["id"]), payload=dict(from_room=s1_room, to_room=room_b, reason="Projector replacement in " + roomd[s1_room]["name"]), autopilot=True),
     dict(id="e04", at=fm(st1+5), kind="facilities_incident_reported", actor="system", entity=dict(room_id=room_b), payload=dict(incident="hvac_fault", temperature_c=27.8, trend="rising", source="building_sensor")),
     dict(id="e05", at=fm(st1+20), kind="mitigation_proposed", actor="facilities_morgan", entity=dict(section_id=s2["id"]), payload=dict(action="request_room_change", from_room=room_b, to_room=alt_room), autopilot=True),
     dict(id="e06", at=fm(st1+35), kind="mitigation_approved", actor="acadops_taylor", entity=dict(section_id=s2["id"]), payload=dict(rationale="Capacity and equipment match; no conflict at this time"), autopilot=True),
     dict(id="e07", at=fm(st2-50), kind="it_service_degraded", actor="system", entity=dict(service_id="svc-wifi"), payload=dict(zone="zone-1", building_ids=zone, severity="degraded")),
     dict(id="e08", at=fm(st2+5), kind="student_report_submitted", actor="student_alex", entity=dict(service_id="svc-wifi", building_id=S["lib"]), payload=dict(text="Wi-Fi keeps dropping on the library second floor")),
     dict(id="e09", at=fm(st2+60), kind="it_service_mitigated", actor="it_casey", entity=dict(service_id="svc-wifi"), payload=dict(note="Access point restarted (simulated)"), autopilot=True),
     dict(id="e10", at="12:15", kind="org_event_rescheduled", actor="org_riley", entity=dict(event_id="ev-fair"), payload=dict(to=dict(day_offset=0, start="14:00", end="17:00"), reason="Moved up from Thursday"), autopilot=True),
     dict(id="e11", at=fm(st3+55), kind="group_slot_available", actor="system", entity=dict(room_id=next(r["id"] for r in rooms if r["building_id"] == S["lib"] and r["kind"] == "study_room")), payload=dict(group="Software Team", meeting_minutes=60)),
     dict(id="e12", at="20:00", kind="day_end_review", actor="system", summary="Open vs resolved, who was informed, filtered signals, audit"),
    ]
    timeline.sort(key=lambda e: hm(e["at"]))
    expected = dict(
      canonical_events=["incident:hvac:" + room_b, "service:wifi:zone-1", "section_update:" + s1["id"], "room_change:" + s1["id"], "room_change:" + s2["id"], "event_change:ev-fair"],
      impact=dict(incident_room=room_b, affected_sections=[s1["id"], s2["id"]], headcount=s1["enrolled"] + s2["enrolled"], feasible_rooms=[alt_room]),
      audiences={
        "e01": dict(students=sorted(set(s1["roster"])), faculty=["faculty_jordan"], not_notified=["student_dana", "student_casey"]),
        "e04": dict(facilities=["facilities_morgan"], faculty=["faculty_jordan", "faculty_sam"], academic_ops=["acadops_taylor"], students=sorted(set(s1["roster"]) | set(s2["roster"])), not_notified=["student_dana"], note="faculty and facilities see counts, not student names"),
        "e07": dict(it=["it_casey"], faculty=["faculty_sam"], students=sorted(set(s2["roster"])), not_notified=["student_blake", "student_dana"]),
      },
      filtered_signals=2)
    scenario = dict(id="connected_campus_day", anchor="next_tuesday_in_tenant_timezone", persona_ids=list(personas), timeline=timeline, expected=expected,
                    sections=dict(s1=s1["id"], s2=s2["id"], s3=s3["id"]), rooms=dict(room_a=s1_room, room_b=room_b, room_c=alt_room, library_study=next(e for e in timeline if e["kind"]=="group_slot_available")["entity"]["room_id"]), buildings=dict(a=S["a"], b=S["b"], c=S["c"], library=S["lib"], event=S["event"]))
    tenant = dict(id=tid, name=P["name"], short_name=P["short"], timezone=P["tz"], locale=P["locale"], week_start=P["week_start"], clock=P["clock"], term_system=P["term_system"],
                  course_code_format=P["code_fmt"], room_code_format=P["room_fmt"], credit_unit=P["credit_unit"], role_vocabulary=P["roles"],
                  features=dict(faculty_workspace=True, facilities_workspace=True, it_workspace=True, org_workspace=True, security_simulation=True),
                  public_links=dict(registrar="https://registrar.example.invalid", it_help="https://it.example.invalid", facilities="https://facilities.example.invalid"),
                  brand=dict(note="Neutral demo theme. No real institutional branding."), data_origin="synthetic")
    return dict(schema_version="tenant-pack/1", data_origin="synthetic", generator=dict(name="generate_tenant_pack", version="1", seed=seed),
                tenant=tenant, campuses=[dict(id="main", name=f"{P['short']} Main Campus")], buildings=blds, walking_minutes=walk, covered_routes=covered, rooms=rooms, assets=assets, services=services,
                departments=depts, courses=courses, sections=sections, people=people, teams=teams, memberships=memberships, orgs=orgs, campus_events=events, terms=terms, knowledge=knowledge,
                personas=personas, scenario=scenario)

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--all", action="store_true"); ap.add_argument("--tenant"); ap.add_argument("--out", default="sample-data/tenants"); ap.add_argument("--seed", type=int, default=2026)
    a = ap.parse_args(); out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    for tid in (PROFILES if a.all else [a.tenant]):
        pack = build(tid, a.seed); p = out / f"{tid}.pack.json"; p.write_text(json.dumps(pack, indent=1, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
        print(f"{tid}: {p.stat().st_size//1024} KB, {len(pack['buildings'])} buildings, {len(pack['rooms'])} rooms, {len(pack['courses'])} courses, {len(pack['sections'])} sections, {len(pack['people']['students'])} demo students")
if __name__ == "__main__": main()
