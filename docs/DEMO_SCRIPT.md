# AURORA 90-Second Demo Script

> This script walks through the "disrupted Tuesday" scenario. All events are virtual; no real SBU system is touched.

---

## Setup

1. Start the backend: `cd backend && source .venv/bin/activate && uvicorn app.main:app --reload --port 8000`
2. Seed data: `python -m scripts.seed_demo_data` (if not already seeded)
3. Start the frontend: `cd frontend && npm run dev`
4. Open **http://localhost:5173** and navigate to **Today**.
5. In the Demo Bar, select scenario **"disrupted_tuesday"** and press **Reset** to initialize.

The scenario anchor date is the next Tuesday on or after today in campus time.

---

## Step 1: 07:30 — Morning planning (already done)

Virtual time: **07:30 AM**

> "AURORA already planned two hours for tonight's assignment. I didn't type anything."

**What to show:**
- Two AURORA aurora blocks in the timeline: 08:00–09:30 and 11:25–11:55.
- One auto-applied move in "Handled for you": "Planned 2 h for CSE 213 Assignment 3." with an **Undo** button.

**Note for presenter:** The assignment is due at 23:59. The blocks were placed automatically before the day started, without any user input.

---

## Step 2: 08:05 — Announcement ingestion (press Play at 60×)

Press **Play** at **60×** speed. The clock will advance to approximately 08:10.

> "It read the Brightspace announcement and created the task, with the source."

**What to show:**
- Task "Prepare for Quiz 4 (MAT 203)" appears in "Handled for you."
- Provenance chip: "From Brightspace announcement (8:05 AM)"
- Due: Thursday 12:30 PM, 90 min estimated.

**What happened:** The Brightspace announcement "Quiz 4 on Thursday — about 90 minutes of preparation" was ingested. The `ingestion` detector parsed the deadline and created the task automatically.

---

## Step 3: 09:10 — Room change

Continue playing or press **Next signal**. Virtual time advances to ~09:15.

> "A room change in SOLAR. It updated my calendar and told me when to leave."

**What to show:**
- "Handled for you": "Updated CSE 214 room — now in Javits 101 (was LE 201)"
- Leave-by marker on the timeline at **9:51 AM**.

**What happened:** SOLAR moved CSE 214 from LE 201 to Javits 101. The `change_impact` detector updated the calendar and computed the leave-by time (6 min walk from Melville Library + 3 min buffer = leave by 9:51). The 09:30 aurora block is unchanged because it still fits before 9:51.

---

## Step 4: 09:40 — Filtered signal

Continue. Virtual time ~09:45.

> "The shuttle delay doesn't affect me, so it stayed quiet."

**What to show:**
- Day counters area: **filtered: 1**
- No decision card or handled entry for the shuttle delay.

**What happened:** Route 3 was delayed 12 minutes. The relevance engine determined Alex does not use the shuttle (not in the persona's routes). The signal was counted but suppressed.

---

## Step 5: 10:05 — Operations view

Continue to ~10:10, then switch to the **Operations** tab and toggle to **Staff view**.

> "Same event from the facilities side: 2 classes, 168 students, one feasible room. One approval."

**What to show:**
- Incident card: Cooling fault in Javits 101, 27.8 °C and rising.
- Impact graph: 2 affected classes (CSE 214, MAT 203), 168 students total.
- Feasible mitigation: Move MAT 203 to Javits 102.
- A staff **Approve** button.

**What happened:** The `ops_impact` detector generated a staff-audience move. The student side shows an informational move ("Javits 101 has a cooling fault") with no action required.

---

## Step 6: 10:35 — Scripted resolution

Switch back to **Today**.

> "My class moved. I did nothing."

**What to show:**
- "Handled for you": "Updated MAT 203 room — now in Javits 102"
- Timeline: MAT 203 block shows Javits 102.

**What happened:** The scenario fixture includes a scripted approval at 10:35 if staff haven't approved yet. The `request_room_change` (simulated) fired, emitting a new room-change signal for MAT 203, which the `change_impact` detector then auto-applied.

---

## Step 7: 12:15 — Career Fair conflict

Continue to ~12:20. A decision card appears.

> "Overlap caught across two systems, resolved in one tap, and it already checked the rain."

1. Press **"Why this?"** to open the evidence drawer.
   - Evidence: Career Fair moved to today 2:00–5:00 PM (campus_events), CSE 316 at 3:00 PM (SOLAR), rain forecast 2:00–5:00 PM (weather), walk SAC→CS 8 min outdoors.
2. Press **Approve**.

**What to show after approval:**
- 2:00–2:45 PM block appears in the timeline.
- Leave-by reminder at **2:49 PM** on the timeline.

**What happened:** The `conflict` detector found that the Career Fair (saved event) overlaps CSE 316. It computed an attendance window (2:00–2:45) that lets Alex attend and still reach CSE 316 by 3:00 PM. The rain note was added because the 2:49 walk is in the rain window.

---

## Step 8: 16:15 — Group meeting

Continue to ~16:20. A new decision card appears.

> "Room booking is simulated and the invite is a draft. Nothing is sent."

Press **Approve**.

**What to show:**
- Move "Book Melville Study Room 3 for group session" executes.
- Result chips: "Book room — **Simulated**", "Draft message — **Draft only, not sent**"
- 5:15–6:15 PM block appears in the timeline.

**What happened:** The `group_opportunity` detector found all four teammates free 5:15–6:15 PM and Melville Study Room 3 available. The `book_room` action is simulated (no real booking made). The `draft_message` action created a draft invite — never sent.

---

## Step 9: Close — Counters and autonomy

Open the **Autonomy** sheet (button in the Today header).

> "Nothing here touched a real system, and every automatic step has Undo."

**What to show:**
- Day summary counters: feeds checked (7), signals processed (~12), signals filtered (2: shuttle + chess club), handled automatically (4–5), decisions asked (2).
- Autonomy sheet: policy table with locked categories highlighted.
- "Handled for you" section: every auto-applied move has an Undo button.

---

## Notes for presenters

- All times shown are **virtual** — the real clock on your machine does not matter.
- The demo bar shows the current virtual time and the scenario name.
- Pressing **Reset** restores the scenario to 07:30 and removes all moves, tasks, and calendar blocks created during the scenario.
- At 600× speed the entire day plays in approximately 75 seconds; at 60× it takes about 12 minutes.
- "Simulated" chips on actions are not a warning — they are the intended label. Room bookings and staff requests are always simulated in this prototype.
