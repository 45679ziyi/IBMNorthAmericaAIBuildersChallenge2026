# AURORA — Architecture

> AURORA is an independent educational prototype. Not affiliated with SBU or IBM.

## System overview

```
Student Web App (React + TypeScript + Vite)
        ↕  HTTP/JSON  (proxied in dev; direct in prod)
FastAPI Application  (Python 3.11+)
├── API v1 (REST endpoints)
├── Auth boundary  (single demo user; future role model documented)
├── Connector Layer
│   ├── ICS Connector (user-uploaded .ics files)
│   ├── Brightspace Demo Adapter (local JSON fixture)
│   ├── Weather Adapter (sample fixture / opt-in live)
│   ├── Campus Knowledge Connector (curated local JSON)
│   └── Campus Sensor Connector (synthetic only)
├── Normalization → SQLite (SQLAlchemy 2.x)
├── Deterministic Planning Engine (pure Python, no LLM for time math)
├── Campus Knowledge Retriever (SQLite FTS5 / LIKE fallback)
├── LLM Provider Adapter (mock default; watsonx opt-in)
└── Audit Events (local SQLite only)
```

## Data boundaries (spec §6.1)

Three logically separate domains even within the single-user prototype:

| Domain | Contents | Storage |
|---|---|---|
| Personal | Imported calendar, tasks, preferences, demo academic data | SQLite (local) |
| Public knowledge | Curated public SBU policy excerpts | SQLite (local) |
| Operations simulation | Synthetic sensor readings | SQLite + in-memory |

These domains must remain separate. A future institution deployment would add separate services and authorization boundaries.

## Key design decisions

### Deterministic planning
The scheduling engine (`services/planner/engine.py`) is pure Python with no LLM involvement in time arithmetic. Inputs → sorted task list → free-interval computation → greedy earliest-fit. The LLM is only allowed to explain results, summarize text, or convert natural language — never to invent or modify timestamps.

### Grounded RAG
The assistant (`services/rag/assistant.py`) retrieves from the SQLite FTS5 index of curated public knowledge chunks. All retrieved content is treated as untrusted data (not instructions). If no evidence is found, the assistant abstains. The LLM provider is swappable; the mock provider gives deterministic rule-based responses for tests and offline demos.

### Safety constraints honored
- No live connections to SBU SOLAR, Brightspace, campus networks, or real sensors.
- No real student records, grades, NetIDs, or passwords.
- Every synthetic record is labeled with `source_type = "demo"` or `data_origin = "synthetic"`.
- Campus Pulse readings always carry `data_origin = "synthetic"`.

## Tech stack

| Layer | Technology |
|---|---|
| Frontend | React 18, TypeScript, Vite 5 |
| Backend | Python 3.11, FastAPI, SQLAlchemy 2.x |
| Database | SQLite (FTS5 for knowledge search) |
| AI (default) | Deterministic mock provider (no external calls) |
| AI (optional) | IBM watsonx.ai via `AI_PROVIDER=watsonx` |
| Scheduling | Pure Python deterministic algorithm |
| Calendar parsing | `icalendar`, `pytz`, `python-dateutil` |

## Future architecture (documentation only)

See the mermaid diagram in the product specification (§6.2) for the aspirational institution deployment. That future design includes:
- Institution Identity Provider (IDP) gating all data access
- Separate services per domain with a Policy and Permission Gateway
- Human review required before any operational action
- No standing unrestricted access for AI service accounts
