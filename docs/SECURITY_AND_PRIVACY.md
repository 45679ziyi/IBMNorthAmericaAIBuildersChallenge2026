# AURORA — Security and Privacy

> AURORA is an independent educational prototype. Not affiliated with SBU or IBM.

## Prototype data policy

1. **Synthetic data only.** All demo academic records are fictional. No real student data, grades, transcripts, or private messages are used or stored.
2. **No institutional credentials.** The prototype does not ask for, store, or transmit SBU NetID passwords, Stony Brook IDs, Social Security numbers, or other institutional identifiers.
3. **No live institutional connections.** AURORA does not connect to SBU SOLAR, Brightspace, campus networks, building controls, cameras, or real sensor infrastructure.
4. **No administrative actions.** AURORA is advisory and read-only. It does not submit assignments, register students for courses, send messages, or control campus systems.
5. **Local storage.** All data is stored in a local SQLite database. In the default configuration, no data leaves the machine except for optional external AI/weather provider calls (clearly labeled in the Privacy screen).

## Data minimization

Fields explicitly excluded from all models:
- NetID / username for institutional systems
- Stony Brook University ID number
- Social Security number
- Home address
- Date of birth
- Real grades or transcript data
- Private course messages
- Precise GPS location history
- Biometric identifiers

## Privacy claims — what AURORA does NOT claim

- FERPA compliance (this is a prototype, not an institution-operated system)
- End-to-end encryption (the server-side backend can read plaintext to perform inference)
- SBU approval, sponsorship, or affiliation
- Production-grade security certifications

## Why AURORA does not claim end-to-end encryption

The backend server must read plaintext task descriptions, calendar events, and knowledge chunks in order to plan, retrieve relevant documents, and generate answers. A true end-to-end encrypted system would require client-side encryption and server-side computation on ciphertext (e.g., homomorphic encryption or secure enclaves). That is not implemented here. Every privacy-sensitive request passes through the FastAPI process in plaintext. This is appropriate for a local development prototype where the user runs the server on their own machine, but it must be disclosed honestly.

## Target privacy architecture (future, not implemented)

A future institution-hosted deployment would address this as follows:

1. **Personal data processed on the user's device.** Where possible (e.g., local plan generation, task management), inference runs entirely in the browser or a local model, so no personal data reaches a shared server.
2. **School-hosted deployment with transport and at-rest encryption.** All traffic over HTTPS/TLS. Database at rest with AES-256. Key management through the institution's existing KMS.
3. **Separate services per data domain.** Personal data (tasks, calendar), public knowledge, and operations telemetry are handled by separate services with separate databases and separate access controls.
4. **Least-privilege read-only access.** No service account has write access to institutional systems. Advisory outputs are recommendations; all actions require human approval.
5. **Human approval for any action.** Nothing that originated in AURORA (a plan, an advisory, a recommendation) can be executed without an explicit human confirmation step that creates an audit record.

**None of the above is implemented in this prototype.** It is documented here so that the design intent is clear and the gap between current state and a production-safe deployment is honest and visible.

## Local development security

- Secrets must never be committed. Use `.env` (excluded from Git).
- The `.env.example` file contains placeholders only.
- SQLite databases containing user data are excluded from Git.

## External data flows

| Data | Destination | When |
|---|---|---|
| Assistant questions | Optional: IBM watsonx.ai or other LLM | Only if `AI_PROVIDER` is set to a live provider |
| Weather location (campus area only) | Optional: OpenWeatherMap or similar | Only if `WEATHER_PROVIDER` is set |
| Imported .ics file contents | Backend only | Never sent to external AI in the default configuration |

## Responsible AI requirements (spec §13.5)

- AI outputs are recommendations, not official academic advising.
- For uncertain or conflicting data, AURORA abstains and directs the user to the official source.
- No autonomous actions against institutional systems are performed.
- The LLM is never allowed to create or change timestamps without deterministic validation.

## Future institution deployment

A future school-hosted deployment would require institution-managed infrastructure, identity, key management, logging, and model hosting. That is a future design possibility, not a feature of this prototype.
