# AURORA — Demo Script

A reproducible walkthrough for the 3-minute demo.

---

## Setup (before demo)

```bash
cd backend
source .venv/bin/activate
python scripts/reset_demo_data.py   # ensure clean state
uvicorn app.main:app --port 8000

# In another terminal:
cd frontend
npm run dev
# Open http://localhost:5173
```

---

## Step 1 — Today screen (0:00–0:30)

1. Open http://localhost:5173
2. Point out the greeting and date.
3. Show the summary strip: events today, open tasks, upcoming deadlines.
4. Show the **Announcements** section — note the `DEMO DATA` badge on every item.
5. Show the **Weather** card — note the `SAMPLE FIXTURE` badge.
6. Show the **Data Sources** strip — Brightspace is labeled `demo`; Campus Pulse is labeled `demo`.

**Key message:** All data is clearly labeled. No live SBU connection is being made.

---

## Step 2 — Import calendar + Planner (0:30–1:20)

1. Click **Planner** in the navigation.
2. Click **Choose .ics file** and select `sample-data/demo_calendar.ics`.
3. Show the import confirmation: "Imported N events".
4. The fixed events (CSE 213, MAT 203) now appear in the Fixed Events panel.
5. Click **⚡ Generate My Day** for today's date.
6. Show the Scheduled Blocks list:
   - Red `fixed event` blocks (classes) are immovable.
   - Blue `task` blocks are scheduled around them.
   - Green `break` blocks are inserted between focus sessions.
7. Click **Why?** on a task block to show the rationale.
8. Click **✓ Accept** to accept the plan.

**Key message:** Fixed events never move. Tasks are scheduled in available gaps. The algorithm is deterministic, not AI-guessed.

---

## Step 3 — Campus Knowledge Assistant (1:20–2:10)

1. Click **Assistant** in the navigation.
2. Note the "grounded in curated public SBU knowledge base" disclaimer.
3. Click the example prompt: **"What is FERPA and how does it protect student records?"**
4. Show the answer and the **Sources** section — click one source URL to show it's a real SBU page.
5. Click the example prompt: **"What is the population of Mars?"**
6. Show the `not_found` response — AURORA abstains rather than fabricating.

**Key message:** Answers are grounded in cited sources. The assistant abstains when evidence is unavailable.

---

## Step 4 — Privacy & Sources (2:10–2:40)

1. Click **Privacy** in the navigation.
2. Walk through the data policy bullet points.
3. Show the **Connected Sources** table — Brightspace is `demo`, Campus Pulse is `demo`, SOLAR is `unavailable`.
4. Show the **Campus Pulse** synthetic section — note the bold `SIMULATED DATA — NOT CONNECTED TO SBU SYSTEMS` warning.
5. Show the **Data Controls** — demonstrate the Reset Demo Data button.

**Key message:** The user can see exactly what data is used, where it came from, and how to delete it.

---

## Step 5 — Closing (2:40–3:00)

Return to Today screen. Summarize:
- One place to see your whole day
- ICS import without live SOLAR access
- Source-backed answers that abstain rather than guess
- Privacy-first design with visible data labels and deletion controls
- Extensible architecture (future approved integrations would follow the same pattern)

---

> AURORA is an independent prototype for educational purposes. Not affiliated with SBU or IBM.
