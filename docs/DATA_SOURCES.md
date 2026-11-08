# AURORA — Data Sources

> AURORA is an independent educational prototype. Not affiliated with SBU or IBM.

## Principle

Every data source in AURORA is either:
1. **User-imported** (a .ics file the user manually chose to upload from their own device), or
2. **Scenario fixture** (locally bundled synthetic JSON from `sample-data/scenarios/demo_day.json`, clearly labeled), or
3. **Curated public knowledge** (manual excerpts from official public university web pages, stored locally).

No data is scraped from authenticated systems. No live institutional connections are made.

> Every signal in this prototype comes from `sample-data/scenarios/demo_day.json`. A real adapter would require written institutional authorization.

---

## V2 simulated feeds

The following 7 feeds are delivered by `FixtureFeed`, which reads from the scenario JSON file. None of them make network requests. Each entry below describes what the feed represents in reality, why it is simulated here, and what a real integration would require.

### `solar` — Schedule and enrollment feed

**Represents:** SOLAR (Student On-Line Academic Registration), the SBU registrar system. Provides class schedules, room assignments, and enrollment counts.

**Why simulated:** SOLAR has no public API. Accessing it requires student credentials and a browser session or a custom institutional adapter with written authorization from the registrar.

**What a real integration would need:** An authorized institutional API or data export, written authorization from SBU's registrar, approved OAuth scope or service account, and a rate-limit-aware adapter.

**Signals in prototype:** `schedule_snapshot`, `room_change`, `deadlines_snapshot`.

---

### `brightspace` — Learning Management System feed

**Represents:** D2L Brightspace, the SBU LMS. Provides announcements, assignment due dates, and course materials.

**Why simulated:** Brightspace has an OAuth 2.0 API, but accessing it requires an approved OAuth application registered by the institution, minimum scopes approved by IT, and compliance review.

**What a real integration would need:** SBU IT approval, an authorized OAuth app, minimum scopes (announcements, assignments read), and a sandbox test environment before production access.

**Signals in prototype:** `announcement`, `deadlines_snapshot`.

---

### `campus_events` — Campus events feed

**Represents:** SBU campus events calendar. Provides upcoming events, venue details, and rescheduling notices.

**Why simulated:** The SBU events feed is public but the adapter requires an explicit allowlist URL (see `docs/DATA_SOURCES.md` source quality rules). Live scraping or polling is not implemented.

**What a real integration would need:** URL from https://www.stonybrook.edu/websupport/components/data-feeds-people/events-feed.html, confirmed with an authorized SBU source, rate-limited polling.

**Signals in prototype:** `saved_events_snapshot`, `event_rescheduled`, `event_announced`.

---

### `shuttle` — Campus shuttle feed

**Represents:** SBU campus shuttle system real-time location and delay data.

**Why simulated:** No public shuttle API is available. Real data would require direct integration with the shuttle dispatch system.

**What a real integration would need:** A data-sharing agreement with Parking and Transportation Services, an authenticated API endpoint, and a persona-matching step (only relevant to students who use the shuttle).

**Signals in prototype:** `delay`.

---

### `weather` — Weather forecast feed

**Represents:** Short-range weather forecast for the Stony Brook campus area (outdoor walk conditions, rain windows).

**Why simulated:** The default configuration uses a static fixture. An optional live provider is supported via `WEATHER_PROVIDER=openweathermap`.

**What a real integration would need:** An OpenWeatherMap (or equivalent) API key, campus-area coordinates only (never precise student GPS), and the opt-in setting `WEATHER_PROVIDER` in `.env`.

**Signals in prototype:** `forecast_change`.

---

### `building_ops` — Building operations / facilities feed

**Represents:** Facilities management system readings — HVAC, temperature, occupancy sensors, and incident reports for classrooms and buildings.

**Why simulated:** Building systems use proprietary protocols (BACnet, SNMP, Modbus) and are isolated on secure institutional networks. No public API exists.

**What a real integration would need:** A data-sharing agreement with Facilities Management, access to the building automation system's data bus or dashboard API, and approval from the Campus Operations team.

**Signals in prototype:** `incident`.

---

### `library_rooms` — Library room availability feed

**Represents:** Melville Library study room booking system — available rooms, capacities, and booking slots.

**Why simulated:** The library booking system (LibCal or equivalent) has an API, but accessing it requires authorization and API key provisioning from the library.

**What a real integration would need:** A LibCal (or equivalent) API key issued by SBU Libraries, read-only scopes for room availability, and a group-size matching step.

**Signals in prototype:** `availability`.

---

## Real data source: Calendar (ICS import)

- **Status:** Implemented
- **Data origin:** User's device — .ics file chosen manually
- **What AURORA does:** Parses the file locally, stores events in SQLite
- **What AURORA does NOT do:** Connect to SOLAR, access Brightspace, automate portal login
- **Labeling:** `source_type = "ics_import"` on all imported events

---

## Campus Knowledge Base

- **Status:** Implemented — curated local excerpts
- **Sources used:**
  - SBU Registrar FERPA page: https://www.stonybrook.edu/registrar/info/ferpa.html
  - SBU Student Access to Education Records Policy: https://www.stonybrook.edu/policy/_policies/student-access-to-education-records-policy.html
  - SBU Events Feed documentation: https://www.stonybrook.edu/websupport/components/data-feeds-people/events-feed.html
  - SBU about page, library page, academic calendar (public pages — curated excerpts)
- **What AURORA does:** Stores curated excerpts in SQLite FTS5; retrieves by keyword match
- **What AURORA does NOT do:** Scrape pages in real-time, ingest copyrighted full texts, access private pages
- **Attribution:** Every chunk carries `canonical_url`, `publisher`, and `last_verified_at_utc`

---

## Source quality rules

- Official university pages are the highest-trust source for campus information answers.
- Every knowledge chunk carries a `last_verified_at_utc` date shown in citations.
- If two official pages conflict, the assistant identifies the conflict and does not invent a resolution.
- If no evidence is found, the assistant abstains.

---

## Allowlist policy

Live retrieval of web content (if ever enabled) must use an explicit allowlist. Feed URLs must not be guessed — they must be obtained from an authorized SBU source per https://www.stonybrook.edu/websupport/components/data-feeds-people/events-feed.html.
