# AURORA — Campus Intelligence

> **⚠️ Prototype notice:** AURORA is an independent educational prototype. It is not affiliated with, endorsed by, or operated by Stony Brook University or IBM.

AURORA is a privacy-first campus intelligence assistant that turns a student's fragmented academic and campus information into a reliable, source-backed daily plan — with honest labels on everything simulated or demo.

---

## Features

| Feature | Status |
|---|---|
| Student home dashboard (Today view with Now/Next band) | ✅ |
| Calendar import (`.ics`) with timezone normalization | ✅ |
| Task manager (create / edit / complete / delete) | ✅ |
| Announcements inbox with read state | ✅ |
| Deterministic daily planning engine with visual timeline | ✅ |
| Campus knowledge assistant (term-coverage RAG) | ✅ |
| Privacy & Sources center | ✅ |
| Campus Pulse simulation (deterministic synthetic sensors) | ✅ |
| Pulse trend analysis and insights | ✅ |
| Operations simulation (sensor insights + security watchdog) | ✅ |
| Security watchdog (synthetic asset + advisory matching) | ✅ |
| System / Light / Dark theme with no flash | ✅ |
| Responsive layout (desktop rail, mobile bottom tab bar) | ✅ |

---

## Quick start

> **All commands below run from the project root** — the folder that contains `backend/` and `frontend/`. Never `cd` into a subdirectory unless the command tells you to.

### Prerequisites

| Tool | Minimum version |
|---|---|
| Python | 3.11+ |
| Node.js | 18+ |
| npm | 9+ |
| uv (recommended) | any recent |

---

### Option A — One-line scripts (easiest)

Open **Terminal 1** (backend):

```bash
bash start.sh
```

Open **Terminal 2** (frontend):

```bash
bash start_frontend.sh
```

Then open **http://localhost:5173** in your browser.

The scripts are self-locating — run them from any directory, for example:

```bash
bash /path/to/aurora-campus-intelligence/start.sh
```

---

### Option B — Step by step

All commands are relative to the project root (the folder that contains `backend/` and `frontend/`).

#### 1. Install backend dependencies

```bash
cd backend
uv venv --python python3       # or: python3 -m venv .venv
source .venv/bin/activate
uv pip install -e ".[dev]"     # or: pip install -e ".[dev]"
cd ..
```

#### 2. Install frontend dependencies

```bash
cd frontend
npm install
cd ..
```

#### 3. Configure environment (optional)

```bash
cp .env.example .env
# Edit .env only if you want a live AI or weather provider
```

#### 4. Seed demo data

```bash
cd backend && source .venv/bin/activate
python -m scripts.seed_demo_data
cd ..
```

#### 5. Run backend (Terminal 1)

```bash
cd backend && source .venv/bin/activate
uvicorn app.main:app --reload --port 8000
```

#### 6. Run frontend (Terminal 2)

```bash
cd frontend
npm run dev
```

Open **http://localhost:5173**

---

### Reset demo data

From the project root:

```bash
cd backend && source .venv/bin/activate
python -m scripts.reset_demo_data
```

---

## Tests and validation

All commands run from the project root.

```bash
# Backend — pytest
cd backend && source .venv/bin/activate
pytest -v

# Frontend — TypeScript type-check
cd frontend && npm run type-check

# Frontend — production build
cd frontend && npm run build

# Run the security check simulation manually
cd backend && source .venv/bin/activate
python -m scripts.run_security_check
```

---

## Architecture

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for a full overview.

Stack:

- **Frontend:** React + TypeScript + Vite, responsive (desktop rail / mobile bottom tabs)
- **Backend:** Python 3.11+, FastAPI, SQLAlchemy 2.x, SQLite
- **AI:** Provider-abstracted; defaults to deterministic mock (no external calls required)
- **Retrieval:** SQLite FTS5 full-text search with term-coverage ranking over curated public knowledge chunks
- **Ops simulation:** Deterministic time-bucketed sensor simulation with trend analysis
- **Security watchdog:** Synthetic fixture-based advisory and certificate matching; AURORA posture self-checks

---

## Safety and honesty

- All demo academic records are synthetic fiction. No real student data.
- No connection to SBU SOLAR, Brightspace, campus networks, or real sensors.
- No NetID password, Stony Brook ID, SSN, grades, or private messages are collected.
- Campus Pulse readings are labeled `SIMULATED DATA — NOT CONNECTED TO SBU SYSTEMS`.
- Security findings are based on fictional demo fixtures; they are advisory simulations only.
- External LLM calls are opt-in; the app works fully offline with the mock provider.

See [`docs/SECURITY_AND_PRIVACY.md`](docs/SECURITY_AND_PRIVACY.md).

---

## License

MIT — see `LICENSE`.

---

## IBM Bob usage

See [`docs/IBM_BOB_USAGE.md`](docs/IBM_BOB_USAGE.md).
