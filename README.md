# AURORA — Campus Intelligence

> **⚠️ Prototype notice:** AURORA is an independent educational prototype. It is not affiliated with, endorsed by, or operated by Stony Brook University or IBM.

AURORA is a privacy-first campus intelligence assistant that turns a student's fragmented academic and campus information into a reliable, source-backed daily plan.

---

## Features

| Feature | Status |
|---|---|
| Student home dashboard (today view) | ✅ |
| Calendar import (`.ics`) with timezone normalization | ✅ |
| Task manager (create / edit / complete / delete) | ✅ |
| Announcements inbox (demo adapter) | ✅ |
| Deterministic daily planning engine | ✅ |
| Campus knowledge assistant (grounded RAG) | ✅ |
| Privacy & Sources center | ✅ |
| Campus Pulse demo (synthetic sensor data) | ✅ |

---

## Quick Start

### Prerequisites

| Tool | Minimum version |
|---|---|
| Python | 3.11+ |
| Node.js | 18+ |
| npm | 9+ |
| uv (recommended) | any recent |

> **Important:** Every command below must be run **after `cd`-ing into the project folder**.
> The project is located at:
> ```
> /Users/zl/Desktop/Stonybrook/Program/IBM 2026 NAC/aurora-campus-intelligence
> ```
> All `cd backend` / `cd frontend` paths are **relative to that folder**.

---

### Option A — One-line scripts (easiest)

Open **Terminal 1** and run the backend:

```bash
cd "/Users/zl/Desktop/Stonybrook/Program/IBM 2026 NAC/aurora-campus-intelligence"
bash start.sh
```

Open **Terminal 2** and run the frontend:

```bash
cd "/Users/zl/Desktop/Stonybrook/Program/IBM 2026 NAC/aurora-campus-intelligence"
bash start_frontend.sh
```

Open **http://localhost:5173** in your browser.

---

### Option B — Step by step

#### Step 1 — Navigate to the project root first

```bash
cd "/Users/zl/Desktop/Stonybrook/Program/IBM 2026 NAC/aurora-campus-intelligence"
```

> Every subsequent command assumes you are inside this folder.

#### Step 2 — Install backend dependencies

```bash
cd backend
uv venv --python python3        # or: python3 -m venv .venv
source .venv/bin/activate
uv pip install -e ".[dev]"      # or: pip install -e ".[dev]"
cd ..
```

#### Step 3 — Install frontend dependencies

```bash
cd frontend
npm install
cd ..
```

#### Step 4 — Configure environment (optional)

```bash
cp .env.example .env
# Edit .env only if you want a live AI or weather provider
```

#### Step 5 — Seed demo data

```bash
cd backend
source .venv/bin/activate
python -m scripts.seed_demo_data
cd ..
```

#### Step 6 — Run backend (Terminal 1)

```bash
cd "/Users/zl/Desktop/Stonybrook/Program/IBM 2026 NAC/aurora-campus-intelligence/backend"
source .venv/bin/activate
uvicorn app.main:app --reload --port 8000
```

#### Step 7 — Run frontend (Terminal 2)

```bash
cd "/Users/zl/Desktop/Stonybrook/Program/IBM 2026 NAC/aurora-campus-intelligence/frontend"
npm run dev
```

Open **http://localhost:5173**

---

### Reset demo data

```bash
cd "/Users/zl/Desktop/Stonybrook/Program/IBM 2026 NAC/aurora-campus-intelligence/backend"
source .venv/bin/activate
python -m scripts.reset_demo_data
```

---

## Run tests

```bash
# Backend — from the backend/ folder
cd "/Users/zl/Desktop/Stonybrook/Program/IBM 2026 NAC/aurora-campus-intelligence/backend"
source .venv/bin/activate
pytest -v

# Frontend — type check and production build
cd "/Users/zl/Desktop/Stonybrook/Program/IBM 2026 NAC/aurora-campus-intelligence/frontend"
npm run type-check
npm run build
```

---

## Architecture

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for a full overview.

The stack is:

- **Frontend:** React + TypeScript + Vite
- **Backend:** Python 3.11+, FastAPI, SQLAlchemy 2.x, SQLite
- **AI:** Provider-abstracted; defaults to deterministic mock (no external calls required)
- **Retrieval:** SQLite FTS5 full-text search over curated public knowledge chunks

---

## Safety and compliance

- All demo academic records are synthetic fiction. No real student data.
- No connection to SBU SOLAR, Brightspace, campus networks, or real sensors.
- No NetID password, Stony Brook ID, SSN, grades, or private messages are collected.
- Campus Pulse readings are labeled `SIMULATED DATA — NOT CONNECTED TO SBU SYSTEMS`.
- External LLM calls are opt-in; the app works fully offline with the mock provider.

See [`docs/SECURITY_AND_PRIVACY.md`](docs/SECURITY_AND_PRIVACY.md).

---

## License

MIT — see `LICENSE`.

---

## IBM Bob usage

See [`docs/IBM_BOB_USAGE.md`](docs/IBM_BOB_USAGE.md).
