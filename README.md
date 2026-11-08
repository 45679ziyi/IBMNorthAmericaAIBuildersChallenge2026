# AURORA — Campus Intelligence

> **⚠️ Prototype notice:** AURORA is an independent educational prototype. It is not affiliated with, endorsed by, or operated by Stony Brook University or IBM.

AURORA is a read-only intelligence layer above the systems a student already uses. It watches simulated feeds, connects the signals, and turns them into a few decisions the student can approve with one tap.

---

## What is simulated vs what is real

| Real | Simulated |
|---|---|
| ICS calendar file import | Every other feed (SOLAR, Brightspace, weather, shuttle, sensors) |
| Local tasks, events, plans | Room bookings, staff requests, sensor readings |
| Rule-based planning engine | Every counter in the UI (scenario outputs, not measured benefits) |
| Knowledge retriever (SQLite FTS5) | LLM answer generation (extractive mock) |

---

## What AURORA claims — and does not claim

**Claims:**
- A read-only intelligence layer that sits above existing systems
- Advisory only; no action is taken without human approval (or is automatically reversible)
- All feeds are simulated fixtures; the adapter interface is designed for real connectors
- Automatic actions are reversible (Undo available for every auto-applied move)

**Does NOT claim:**
- Connection to any real SBU system (SOLAR, Brightspace, campus networks, sensors)
- FERPA compliance
- End-to-end encryption
- SBU or IBM endorsement or affiliation
- Measured time savings (every counter is a count of simulated scenario events)
- Production readiness

---

## Safety

- No send action exists anywhere in this codebase. There is no `send_email`, `sendmail`, or equivalent.
- Automatic actions touch only AURORA's own plan and are reversible via the Undo button.
- Every external action (`book_room`, `request_room_change`) is simulated and labeled so in the UI, the API response, and the audit log.
- Message drafts are created as drafts only and are never sent.
- Escalation writes a local audit record and nothing else.

---

## Quick start

All commands run from the project root (the folder containing `backend/` and `frontend/`).

### Prerequisites

| Tool | Minimum version |
|---|---|
| Python | 3.11+ |
| Node.js | 18+ |
| npm | 9+ |
| uv (recommended) | any recent |

### Step 1 — Backend dependencies

```bash
cd backend
uv venv --python python3        # or: python3 -m venv .venv
source .venv/bin/activate
uv pip install -e ".[dev]"      # or: pip install -e ".[dev]"
cd ..
```

### Step 2 — Frontend dependencies

```bash
cd frontend
npm install
cd ..
```

### Step 3 — Seed demo data

```bash
cd backend && source .venv/bin/activate
python -m scripts.seed_demo_data
cd ..
```

### Step 4 — Run the backend (Terminal 1)

```bash
cd backend && source .venv/bin/activate
uvicorn app.main:app --reload --port 8000
```

### Step 5 — Run the frontend (Terminal 2)

```bash
cd frontend
npm run dev
```

Open **http://localhost:5173**

### One-line scripts (alternative)

```bash
bash start.sh           # Terminal 1 — backend
bash start_frontend.sh  # Terminal 2 — frontend
```

---

## How to run the demo

The demo uses a scripted "disrupted Tuesday" scenario — a day where a room changes, a cooling fault occurs, a career fair moves, and a group meeting needs booking. AURORA watches the feeds, proposes moves, and applies reversible automatic actions.

1. Start the backend and frontend (see Quick start above).
2. Open **http://localhost:5173** and navigate to **Today**.
3. In the **Demo Bar** at the top, press **"disrupted_tuesday"** to start the scenario, then press **Play** (60×, 300×, or 600× speed).
4. Watch the command center: decision cards appear, the timeline updates, and "Handled for you" fills with auto-applied moves.
5. Press **Next signal** to step through each event one at a time.
6. Switch to the **Operations** tab and toggle to **Staff view** to see the facilities side of the same incident.
7. See [`docs/DEMO_SCRIPT.md`](docs/DEMO_SCRIPT.md) for the full 90-second walkthrough with exact virtual times.

---

## Commands

| Command | What it does | Caveat |
|---|---|---|
| `cd backend && source .venv/bin/activate && pytest -v` | Run all backend tests | — |
| `cd frontend && npm run type-check` | TypeScript type-check (0 errors expected) | — |
| `cd frontend && npm run build` | Production build | — |
| `cd frontend && npm run ui-check` | Playwright accessibility and overflow check | Playwright must be installed separately (`pip install playwright && playwright install`) |
| `cd frontend && npm run demo-shots` | Take demo screenshots | Playwright must be installed |

---

## Architecture

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for a full overview.

Stack:

- **Frontend:** React 18 + TypeScript + Vite, responsive (desktop rail / mobile bottom tabs)
- **Backend:** Python 3.11+, FastAPI, SQLAlchemy 2.x, SQLite
- **Intelligence:** 7 pure-function detectors, moves engine with fingerprint reconciliation, demo clock, scenario runner
- **Retrieval:** SQLite FTS5 full-text search with term-coverage ranking over curated public knowledge chunks
- **Feeds:** All simulated via `FixtureFeed`; ICS calendar file import is the only real data path
- **Action layer:** 7 allowlisted action types; no others can execute; simulated actions are labeled

---

## Docs

| File | Contents |
|---|---|
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Intelligence loop, clock, detectors, action layer |
| [`docs/SECURITY_AND_PRIVACY.md`](docs/SECURITY_AND_PRIVACY.md) | No-send guarantee, allowlist, undo, audit trail |
| [`docs/DATA_SOURCES.md`](docs/DATA_SOURCES.md) | Every feed and why it is simulated |
| [`docs/DATA_DICTIONARY.md`](docs/DATA_DICTIONARY.md) | All tables and columns |
| [`docs/DEMO_SCRIPT.md`](docs/DEMO_SCRIPT.md) | 90-second demo walkthrough |
| [`docs/BUILD_NOTES.md`](docs/BUILD_NOTES.md) | Final test counts and what was not verified |
| [`docs/IBM_BOB_USAGE.md`](docs/IBM_BOB_USAGE.md) | Truthful M0–M6 build log |

---

## License

MIT — see `LICENSE`.
