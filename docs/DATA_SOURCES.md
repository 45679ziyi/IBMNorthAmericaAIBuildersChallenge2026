# AURORA — Data Sources

> AURORA is an independent educational prototype. Not affiliated with SBU or IBM.

## Principle

Every data source in AURORA is either:
1. **User-imported** (a .ics file the user manually chose to upload from their own device), or
2. **Demo fixture** (locally bundled synthetic JSON, clearly labeled), or
3. **Curated public knowledge** (manual excerpts from official public university web pages, stored locally).

No data is scraped from authenticated systems. No live institutional connections are made.

---

## Source catalog

### Calendar (ICS Import)
- **Status:** Implemented
- **Data origin:** User's device — .ics file chosen manually
- **What AURORA does:** Parses the file locally, stores events in SQLite
- **What AURORA does NOT do:** Connect to SOLAR, access Brightspace, automate portal login
- **Labeling:** `source_type = "ics_import"` on all imported events

### Brightspace (Demo Adapter)
- **Status:** Demo only — local synthetic JSON fixture
- **Data origin:** `sample-data/brightspace_demo.json` (fictional data)
- **What AURORA does:** Loads the fixture and labels all records `source_type = "demo"`
- **Future:** Requires written SBU authorization + approved OAuth app + minimum scopes
- **Labeling:** All records marked DEMO DATA in the UI

### SOLAR (Placeholder)
- **Status:** Not implemented — placeholder interface only
- **Future:** Requires a supported interface and written authorization from SBU

### Campus Knowledge Base
- **Status:** Implemented — curated local excerpts
- **Sources used:**
  - SBU Registrar FERPA page: https://www.stonybrook.edu/registrar/info/ferpa.html
  - SBU Student Access to Education Records Policy: https://www.stonybrook.edu/policy/_policies/student-access-to-education-records-policy.html
  - SBU Events Feed documentation: https://www.stonybrook.edu/websupport/components/data-feeds-people/events-feed.html
  - SBU about page, library page, academic calendar (public pages — curated excerpts)
- **What AURORA does:** Stores curated excerpts in SQLite FTS5; retrieves by keyword match
- **What AURORA does NOT do:** Scrape pages in real-time, ingest copyrighted full texts, access private pages
- **Attribution:** Every chunk carries `canonical_url`, `publisher`, and `last_verified_at_utc`

### Weather
- **Status:** Sample fixture by default
- **Data origin:** `services/connectors/weather.py` static object (not a real API call)
- **Future:** Optional live provider via `WEATHER_PROVIDER=openweathermap` + API key; uses campus-area location only, never precise student GPS

### Campus Pulse (Synthetic Only)
- **Status:** Implemented — synthetic data only
- **Data origin:** Generated locally in Python (random jitter around fixed base values)
- **Labeling:** `data_origin = "synthetic"` on every record; UI shows `SIMULATED DATA — NOT CONNECTED TO SBU SYSTEMS`
- **What AURORA does NOT do:** Network sockets, SNMP, SSH, device discovery, real building access

---

## Source quality rules

- Official university pages are the highest-trust source for campus information answers.
- Every knowledge chunk carries a `last_verified_at_utc` date shown in citations.
- If two official pages conflict, the assistant identifies the conflict and does not invent a resolution.
- If no evidence is found, the assistant abstains.

---

## Allowlist policy

Live retrieval of web content (if ever enabled) must use an explicit allowlist. Feed URLs must not be guessed — they must be obtained from an authorized SBU source per https://www.stonybrook.edu/websupport/components/data-feeds-people/events-feed.html.
