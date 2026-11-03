import { useEffect, useState } from 'react'
import './TodayScreen.css'
import {
  getEvents, getTasks, getAnnouncements, getConnectors,
  CalendarEvent, Task, Announcement, ConnectorStatus,
} from '../../api/client'

function fmtTime(iso: string) {
  return new Date(iso).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', timeZone: 'America/New_York' })
}
function fmtDate(iso: string) {
  return new Date(iso).toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric', timeZone: 'America/New_York' })
}
function fmtDue(iso: string | undefined) {
  if (!iso) return 'No deadline'
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit', timeZone: 'America/New_York' })
}
function isToday(isoStart: string) {
  const d = new Date(isoStart)
  const now = new Date()
  return d.toLocaleDateString('en-US', { timeZone: 'America/New_York' }) === now.toLocaleDateString('en-US', { timeZone: 'America/New_York' })
}
function greeting() {
  const h = new Date().toLocaleString('en-US', { hour: 'numeric', hour12: false, timeZone: 'America/New_York' })
  const hour = parseInt(h)
  if (hour < 12) return 'Good morning'
  if (hour < 17) return 'Good afternoon'
  return 'Good evening'
}

export default function TodayScreen() {
  const [events, setEvents] = useState<CalendarEvent[]>([])
  const [tasks, setTasks] = useState<Task[]>([])
  const [announcements, setAnnouncements] = useState<Announcement[]>([])
  const [connectors, setConnectors] = useState<ConnectorStatus[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    Promise.all([getEvents(), getTasks(), getAnnouncements(), getConnectors()])
      .then(([ev, tk, an, cn]) => {
        setEvents(ev)
        setTasks(tk)
        setAnnouncements(an)
        setConnectors(cn)
        setLoading(false)
      })
      .catch(e => { setError(String(e)); setLoading(false) })
  }, [])

  const todayEvents = events.filter(e => isToday(e.start_at_utc)).sort((a, b) =>
    new Date(a.start_at_utc).getTime() - new Date(b.start_at_utc).getTime()
  )
  const openTasks = tasks.filter(t => t.status !== 'done').slice(0, 5)
  const upcoming = tasks.filter(t => t.status !== 'done' && t.due_at_utc).sort((a, b) =>
    new Date(a.due_at_utc!).getTime() - new Date(b.due_at_utc!).getTime()
  ).slice(0, 3)

  const now = new Date()
  const dateStr = now.toLocaleDateString('en-US', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric', timeZone: 'America/New_York' })

  if (loading) return <div className="state-loading" role="status" aria-live="polite">Loading your day…</div>
  if (error) return <div className="state-error" role="alert">Failed to load data: {error}</div>

  return (
    <div>
      <div className="screen-title">
        <h1>{greeting()}, Alex! 👋</h1>
        <p>{dateStr}</p>
      </div>

      {/* Summary strip */}
      <div className="today-strip">
        <div className="today-stat card">
          <span className="stat-n">{todayEvents.length}</span>
          <span className="stat-l">events today</span>
        </div>
        <div className="today-stat card">
          <span className="stat-n">{openTasks.length}</span>
          <span className="stat-l">open tasks</span>
        </div>
        <div className="today-stat card">
          <span className="stat-n">{upcoming.length}</span>
          <span className="stat-l">upcoming deadlines</span>
        </div>
      </div>

      <div className="today-grid">
        {/* Today's events */}
        <section aria-labelledby="today-events-heading">
          <h2 id="today-events-heading">Today's Schedule</h2>
          {todayEvents.length === 0
            ? <p className="text-muted">No events today. Import a calendar to get started.</p>
            : <ul className="event-list">
                {todayEvents.map(ev => (
                  <li key={ev.id} className="event-item card">
                    <div className="event-time">{fmtTime(ev.start_at_utc)} – {fmtTime(ev.end_at_utc)}</div>
                    <div className="event-title">{ev.title}</div>
                    {ev.location_text && <div className="text-muted text-sm">{ev.location_text}</div>}
                    <span className={`badge ${ev.source_type === 'demo' ? 'badge-demo' : 'badge-ok'}`}>
                      {ev.source_type === 'demo' ? 'DEMO' : ev.source_type}
                    </span>
                  </li>
                ))}
              </ul>
          }
        </section>

        {/* Upcoming tasks */}
        <section aria-labelledby="today-tasks-heading">
          <h2 id="today-tasks-heading">Open Tasks</h2>
          {openTasks.length === 0
            ? <p className="text-muted">No open tasks.</p>
            : <ul className="task-list">
                {openTasks.map(t => (
                  <li key={t.id} className="task-item card">
                    <div className="flex items-center justify-between">
                      <span className="task-title">{t.title}</span>
                      <span className={`badge badge-${t.priority === 'urgent' ? 'err' : t.priority === 'high' ? 'warn' : 'ok'}`}>
                        {t.priority}
                      </span>
                    </div>
                    {t.course_label && <div className="text-muted text-sm">{t.course_label}</div>}
                    <div className="text-muted text-sm">Due: {fmtDue(t.due_at_utc)} · {t.estimated_minutes} min</div>
                    {t.source_type === 'demo' && <span className="badge badge-demo">DEMO DATA</span>}
                  </li>
                ))}
              </ul>
          }
        </section>
      </div>

      {/* Announcements */}
      <section aria-labelledby="today-ann-heading" className="mt-2">
        <h2 id="today-ann-heading">Announcements <span className="badge badge-demo">DEMO DATA</span></h2>
        {announcements.length === 0
          ? <p className="text-muted">No announcements.</p>
          : <ul className="ann-list">
              {announcements.slice(0, 4).map(a => (
                <li key={a.id} className="card ann-item">
                  <div className="flex justify-between items-center">
                    <strong>{a.title}</strong>
                    <span className="text-muted text-sm">{a.course_label}</span>
                  </div>
                  <p className="text-sm mt-1">{a.body_summary}</p>
                </li>
              ))}
            </ul>
        }
      </section>

      {/* Weather sample */}
      <section aria-labelledby="weather-heading" className="mt-2">
        <div className="card flex items-center gap-2" style={{ flexWrap: 'wrap' }}>
          <span>☁️</span>
          <div>
            <strong id="weather-heading">Weather — Stony Brook, NY</strong>
            <div className="text-muted text-sm">~12.5 °C · Partly Cloudy · Humidity 62%</div>
          </div>
          <span className="badge badge-demo" style={{ marginLeft: 'auto' }}>SAMPLE FIXTURE</span>
        </div>
      </section>

      {/* Connector status strip */}
      <section aria-labelledby="conn-status-heading" className="mt-2">
        <h3 id="conn-status-heading">Data Sources</h3>
        <div className="connector-strip">
          {connectors.slice(0, 4).map(c => (
            <div key={c.name} className="connector-pill">
              <span className={`conn-dot conn-${c.status}`} aria-hidden="true" />
              <span className="text-sm">{c.name}</span>
              <span className={`badge badge-${c.status === 'connected' ? 'ok' : c.status === 'demo' ? 'demo' : 'warn'}`}>
                {c.status}
              </span>
            </div>
          ))}
        </div>
        <p className="text-muted text-sm mt-1">
          Last updated: {new Date().toLocaleTimeString('en-US', { timeZone: 'America/New_York' })}
        </p>
      </section>
    </div>
  )
}
