# AURORA — 3-Minute Demo Script

This is the narrated script for the three-minute Connected Campus Day demo, following Appendix F of the V3 brief.

---

## Before you start

1. Start backend: `cd backend && source .venv/bin/activate && uvicorn app.main:app --reload --port 8000`
2. Start frontend: `cd frontend && npm run dev`
3. Open **http://localhost:5173**
4. Make sure the tenant is set to **SBU Demo** (top bar)
5. Make sure the persona is **Alex (Student)**

---

## 0:00 — 0:20 | The problem

**Say:** "A university is five systems and six offices. When anything changes, the student is the integrator."

**Show:** The student command center. Point to the empty decision area. "Right now, nothing has happened. But in a moment, three things will go wrong at once."

---

## 0:20 — 0:55 | One event, many roles

**Action:** In the Demo Bar, click **Start** → select `disrupted_tuesday`. Click **Play** at 300×. Let it run until the cooling fault fires (around `10:05` on the clock). Pause.

**Say:** "A cooling fault just reported 27.8°C and rising in the lecture hall. Three things happened simultaneously: Facilities got a work order, the two faculty teaching there got a teaching-impact notice, and the 19 affected students got a status notification. But not Dana — Dana isn't enrolled in those sections."

**Action:** Click on the cooling fault event chip in campus status. This opens the **Event Spine** at `/events/ce_xxxx`.

**Say:** "One event. One ID. Here's what each role sees — Facilities sees the full incident and the work order. Faculty see section counts. Students see status. AcadOps sees the approval queue. Nobody sees more than they need to."

**Point to:** The impact section — "2 sections, 168 students. One feasible alternative room."

---

## 0:55 — 1:25 | A real decision

**Action:** Switch persona to **Morgan (Facilities)** using the persona switcher.

**Say:** "I'm now acting as Morgan. This is not authentication — this is a demo persona. The server enforces what Morgan can and can't do."

**Show:** The Facilities workspace. There's a room reassignment work item. Click **Propose room change**, enter room CS-LH2, submit.

**Action:** Try to approve it as Morgan (click "Approve" if available).

**Say:** "Morgan cannot approve this. The server returns 403 — Academic Operations must approve room changes, not Facilities."

**Action:** Switch to **Taylor (Academic Ops)**. The approval queue shows the pending reassignment. Click **Approve**, enter a rationale. Submit.

**Say:** "Taylor approves with a rationale. Watch the student and faculty views."

**Action:** Switch back to Alex. The timeline and campus status now show the updated room.

---

## 1:25 — 1:50 | Quiet by design

**Action:** Resume play. Let it advance to `11:40` (Wi-Fi degradation).

**Say:** "Wi-Fi degraded in one building zone. Ten students were notified — the students enrolled in the affected section. Blake and Dana were not notified. Two signals were filtered with a reason."

**Point to:** The Wi-Fi event. "Alex submits a report from the library. Instead of creating a second event, it joins the existing Wi-Fi event. One event, one thread."

---

## 1:50 — 2:25 | Portable

**Action:** Switch the **tenant** to **Pacific Demo** (top bar, Demo Universities). Click **Replay from reset** (or stop and restart).

**Say:** "Pacific Demo: quarter system, Los Angeles time. Same build, different pack."

**Point to:** The clock showing LA time, "Fall Quarter 2026" in the term display, class times shifted.

**Action:** Switch to **Rhine Demo**. 

**Say:** "Rhine: 24-hour clock, ECTS credits, Berlin time zone. Same binary, same code, a university is a pack that passes a validator."

**Show:** `tools/validate_tenant_pack.py --help` (or just say it exists).

---

## 2:25 — 2:50 | Trusted

**Action:** Switch back to **SBU Demo**. Navigate to **Trust & Quality** (in the nav for the tenant admin persona, or show it directly).

**Say:** "Authorization: 300 cases, 100% pass rate. Injection tests: 0 successful out of 20. No SMTP, no SMS, no push. Tenant leakage probes: 0 of 50. The eval harness runs offline — no API key required."

**Show:** The eval numbers on screen.

---

## 2:50 — 3:00 | Close

**Say:** "Read-only. Advisory. Synthetic data. A coordination layer for any university — built end-to-end with IBM Bob."

---

## Contingency notes

- If the scenario gets stuck: click **Reset** in the Demo Bar
- If the tenant switch doesn't load: refresh and re-enter the tenant header manually
- If work items don't appear: advance time slightly past the expected event time
