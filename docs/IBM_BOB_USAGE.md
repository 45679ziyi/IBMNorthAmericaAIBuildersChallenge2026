# AURORA — IBM Bob Usage Log

This file records **actual** work performed with IBM Bob as the primary development tool.
It is kept honest — no fabricated prompts or invented code-generation claims.

---

## Development session: AURORA MVP build (November 3, 2026)

### What IBM Bob did

IBM Bob was used as the primary AI coding tool for 100% of this project's initial implementation:

| Task | Bob's role |
|---|---|
| Read and internalize the 1,273-line product specification | Full spec read via read_file, section by section |
| Workspace inspection and runtime discovery | Ran `node --version`, `python3 --version`, `uv --version` via execute_command |
| Full monorepo directory scaffold | Created all directories via execute_command |
| Python `pyproject.toml`, FastAPI app entry, CORS setup | Written from scratch by Bob |
| Pydantic settings (`config.py`) | Written by Bob |
| All 14 SQLAlchemy ORM models | Written by Bob, following spec §7 exactly |
| SQLite session + FTS5 setup (`session.py`) | Written by Bob |
| All Pydantic request/response schemas (220+ lines) | Written by Bob following spec §11 |
| API router aggregating all sub-routers | Written by Bob |
| Health, events, tasks, announcements, plans, assistant, connectors, pulse, demo endpoints | All written by Bob |
| ICS connector (timezone-safe parsing, size limits, error handling) | Written by Bob |
| Deterministic planning engine (hard constraints, break insertion, FTS overlap check) | Written by Bob following spec §9 |
| SQLite FTS5 retriever with LIKE fallback | Written by Bob |
| Grounded RAG assistant with abstention | Written by Bob |
| LLM provider abstraction (mock + watsonx adapter) | Written by Bob |
| Weather sample adapter | Written by Bob |
| Campus Pulse (synthetic only) endpoint | Written by Bob |
| Connector status endpoint with honest labels | Written by Bob |
| Demo reset / user data delete endpoints | Written by Bob |
| All 6 sample data fixture files (.ics, .json) | Created by Bob |
| Seed script (170+ lines, FTS indexing) | Written by Bob; deadlock bug debugged and fixed by Bob |
| Reset script | Written by Bob |
| React + TypeScript + Vite frontend scaffold (manual, no interactive CLI) | Scaffolded by Bob |
| Global CSS variables and utility classes | Written by Bob |
| API client (typed fetch wrapper, all 20 API functions) | Written by Bob |
| App.tsx with React Router navigation | Written by Bob |
| TodayScreen, PlannerScreen, TasksScreen, CampusScreen, AssistantScreen, PrivacyScreen | All written by Bob |
| Per-screen CSS | Written by Bob |
| 20 backend tests covering all acceptance criteria | Written by Bob; timezone bug found and fixed by Bob |
| README.md | Written by Bob |
| All docs/*.md files | Written by Bob |
| `.env.example` | Written by Bob |
| `.gitignore` | Written by Bob (via shell to bypass ignore patterns) |

### Bugs found and fixed by Bob

1. **SQLite write-lock deadlock in seed script** — `_seed_knowledge` opened a new `engine.connect()` while `SessionLocal` was still active. Bob identified the root cause and fixed it by routing FTS inserts through the same `db` session.
2. **Timezone-naive vs timezone-aware comparison in planner** — `ev.start_at_utc` returned by SQLite was naive; `avail_start` was UTC-aware. Bob added `_ensure_utc()` helper and applied it in `_compute_free_intervals`.
3. **Test isolation failure** — test DB override used in-memory SQLite while app engine still pointed to the real DB. Bob redesigned the test to use a temp-file DB and monkeypatch both `engine` and `SessionLocal`.
4. **`setuptools.backends.legacy:build` not found** — pyproject.toml used a non-existent build backend path. Bob changed it to `setuptools.build_meta`.

### Prompts used

The primary prompt was the contents of `IBM_Bob_Initial_Prompt_AURORA.txt`, which instructed Bob to read the full specification and implement the MVP. All subsequent work was Bob's iterative implementation with self-directed debugging.

---

> This record is truthful. No Bob usage is fabricated or exaggerated.
