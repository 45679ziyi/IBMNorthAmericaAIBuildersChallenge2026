import { useEffect, useState } from 'react'
import './CampusScreen.css'
import { getAnnouncements, Announcement } from '../../api/client'

function fmtDate(iso: string | undefined) {
  if (!iso) return null
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric', timeZone: 'America/New_York' })
}

const CAMPUS_EVENTS_DEMO = [
  { id: 'ce1', title: 'Fall Career Fair 2026', start: 'Nov 5, 2026 · 2:00 PM', location: 'Island Federal Credit Union Arena', source: 'SBU Career Center (Demo)', isDemo: true },
  { id: 'ce2', title: 'CS Colloquium: AI in Healthcare', start: 'Nov 6, 2026 · 5:00 PM', location: 'CS Building Room 2311', source: 'SBU CS Department (Demo)', isDemo: true },
  { id: 'ce3', title: 'Library Research Workshop', start: 'Nov 4, 2026 · 10:00 AM', location: 'Melville Library N2017', source: 'SBU Libraries (Demo)', isDemo: true },
]

export default function CampusScreen() {
  const [announcements, setAnnouncements] = useState<Announcement[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getAnnouncements()
      .then(a => { setAnnouncements(a); setLoading(false) })
      .catch(e => { setError(String(e)); setLoading(false) })
  }, [])

  if (loading) return <div className="state-loading">Loading campus info…</div>

  return (
    <div>
      <div className="screen-title">
        <h1>Campus</h1>
        <p>Upcoming events and university resources. Demo data is labeled.</p>
      </div>

      {/* Campus Events */}
      <section aria-labelledby="campus-events-heading">
        <h2 id="campus-events-heading">
          Campus Events <span className="badge badge-demo">DEMO DATA</span>
        </h2>
        <p className="text-muted text-sm">
          Not connected to live SBU event systems. A future integration would require an authorized feed URL from SBU.
        </p>
        <ul className="campus-event-list">
          {CAMPUS_EVENTS_DEMO.map(ev => (
            <li key={ev.id} className="card campus-event-item">
              <div className="flex justify-between items-center">
                <strong>{ev.title}</strong>
                <span className="badge badge-demo">DEMO</span>
              </div>
              <div className="text-muted text-sm">{ev.start}</div>
              <div className="text-muted text-sm">📍 {ev.location}</div>
              <div className="text-sm source-link">Source: {ev.source}</div>
            </li>
          ))}
        </ul>
      </section>

      {/* Course Announcements */}
      <section aria-labelledby="campus-ann-heading" className="mt-2">
        <h2 id="campus-ann-heading">
          Course Announcements <span className="badge badge-demo">DEMO DATA</span>
        </h2>
        <p className="text-muted text-sm">
          Loaded from a local synthetic fixture. No connection to SBU Brightspace. A future integration requires written SBU authorization.
        </p>
        {error && <div className="state-error">{error}</div>}
        {announcements.length === 0
          ? <div className="state-empty">No announcements.</div>
          : <ul className="campus-event-list">
              {announcements.map(a => (
                <li key={a.id} className="card campus-event-item">
                  <div className="flex justify-between items-center">
                    <strong>{a.title}</strong>
                    <span className="text-muted text-sm">{a.course_label}</span>
                  </div>
                  <p className="text-sm mt-1">{a.body_summary}</p>
                  <div className="text-muted text-sm">
                    {a.published_at_utc && `Published: ${fmtDate(a.published_at_utc)}`}
                  </div>
                  <span className="badge badge-demo">DEMO DATA</span>
                </li>
              ))}
            </ul>
        }
      </section>

      {/* Campus Pulse link */}
      <section aria-labelledby="pulse-heading" className="mt-2">
        <div className="card">
          <h3 id="pulse-heading">Campus Pulse (Demo Preview)</h3>
          <p className="text-muted text-sm">
            Synthetic sensor telemetry — <strong>SIMULATED DATA, NOT CONNECTED TO SBU SYSTEMS.</strong>
            This demonstrates a future campus operations intelligence architecture.
          </p>
          <p className="text-muted text-sm">
            Sensor readings are generated locally with no network connections, device access, or real infrastructure.
          </p>
        </div>
      </section>
    </div>
  )
}
