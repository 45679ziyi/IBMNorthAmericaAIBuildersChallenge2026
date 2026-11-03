# AURORA — Build Notes

## Workspace inspection (November 3, 2026)

### Environment

| Tool | Version |
|---|---|
| Node.js | v26.13.0 |
| npm | 11.20.0 |
| Python | 3.15.2 (system) / 3.11.15 (venv via uv) |
| pip | 26.2.2 |
| uv | 0.11.25 |

### Initial workspace state

- Two files present: `AURORA_Campus_Intelligence_Project_Spec_for_IBM_Bob.md` and `IBM_Bob_Initial_Prompt_AURORA.txt`
- No existing application code
- Full implementation created from scratch

---

## Backend setup

```bash
cd backend
uv venv --python python3   # Creates .venv with Python 3.11.15
uv pip install -e ".[dev]"
python scripts/seed_demo_data.py
```

**Packages installed:** fastapi, uvicorn, sqlalchemy, pydantic, pydantic-settings, icalendar, python-multipart, python-dateutil, pytz, httpx, pytest, pytest-asyncio, ruff

---

## Frontend setup

```bash
cd frontend
npm install
```

**Note:** Vite interactive CLI was non-interactive in this environment; frontend was scaffolded manually.

---

## Test run results

```
backend/ $ .venv/bin/pytest tests/test_api.py -v
======================== 20 passed, 3 warnings in 1.15s ========================
```

All 20 tests pass. 3 deprecation warnings (FastAPI `on_event`, starlette httpx version) — no failures.

---

## Frontend build

```
frontend/ $ npm run build
✓ 48 modules transformed.
dist/index.html                   0.58 kB │ gzip:  0.37 kB
dist/assets/index-AiSjm0_6.css    8.32 kB │ gzip:  2.30 kB
dist/assets/index-H_lpZtDZ.js   196.63 kB │ gzip: 61.77 kB
✓ built in 565ms
```

TypeScript type check: `npm run type-check` → 0 errors.

---

## Bugs found and fixed during implementation

1. **SQLite write-lock deadlock** — `_seed_knowledge()` opened a second connection via `engine.connect()` while an active session was still open. Fixed by routing FTS inserts through the existing `db` session.
2. **Timezone-naive comparison in planner** — `ev.start_at_utc` from SQLite was naive; `avail_start` was UTC-aware. Added `_ensure_utc()` helper.
3. **Test isolation** — In-memory SQLite was not shared between app startup and test session. Fixed by using a temp-file DB and monkeypatching both `engine` and `SessionLocal`.
4. **setuptools build backend** — `setuptools.backends.legacy:build` not available; fixed to `setuptools.build_meta`.

---

## Architecture decisions

- **No Docker** — kept minimal per spec §5 ("Build a small, coherent monorepo. Do not add unnecessary infrastructure").
- **No Alembic** — schema is simple; using `Base.metadata.create_all()` is sufficient for the prototype.
- **Mock LLM by default** — satisfies spec requirement that app must run without external credentials.
- **FTS5 with LIKE fallback** — robust retrieval without requiring vector embeddings; embeddings interface prepared for future.
- **Temp-file test DB** — avoids SQLite in-memory lock contention between test fixtures and app startup event.
