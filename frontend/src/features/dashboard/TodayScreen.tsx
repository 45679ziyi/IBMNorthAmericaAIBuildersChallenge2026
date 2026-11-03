import { useEffect, useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { Zap, Calendar, CheckSquare, Clock, MapPin, RefreshCw } from 'lucide-react'
import './TodayScreen.css'
import { SkeletonList } from '../../components/Skeleton'
import { useToast } from '../../components/Toast'
import {
  getEvents, getTasks, getAnnouncements, getConnectors, updateTask,
  CalendarEvent, Task, Announcement, ConnectorStatus,
} from '../../api/client'

// ── Helpers ──────────────────────────────────────────────────────────────────
function fmtTime(iso: string) {
  return new Date(iso).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', timeZone: 'America/New_York' })
}
function fmtDue(iso: string | undefined) {
  if (!iso) return null
  const d = new Date(iso)
  const isOverdue = d.getTime() < Date.now()
  const str = d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', timeZone: 'America/New_York' })
  return { str, isOverdue }
}
function isToday(isoStart: string) {
  const d = new Date(isoStart)
  const now = new Date()
  return d.toLocaleDateString('en-US', { timeZone: 'America/New_York' }) ===
    now.toLocaleDateString('en-US', { timeZone: 'America/New_York' })
}
function greeting() {
  const h = parseInt(new Date().toLocaleString('en-US', { hour: 'numeric', hour12: false, timeZone: 'America/New_York' }))
  if (h < 12) return 'Good morning'
  if (h < 17) return 'Good afternoon'
  return 'Good evening'
}

// ── Donut chart (pure SVG) ─────────────────────────────────────────────────
function DonutChart({ done, inProgress, todo }: { done: number; inProgress: number; todo: number }) {
  const total = done + inProgress + todo || 1
  const r = 30
  const circ = 2 * Math.PI * r

  function arc(value: number, offset: number) {
    const pct = value / total
    return { dash: circ * pct, offset: circ * (1 - offset) }
  }

  const donePct = done / total
  const ipPct = inProgress / total
  const d1 = arc(done, 0)
  const d2 = arc(inProgress, donePct)
  const d3 = arc(todo, donePct + ipPct)

  const pctDone = Math.round(donePct * 100)

  return (
    <div className="donut-wrap" aria-label={`Task progress: ${done} done, ${inProgress} in progress, ${todo} to do`}>
      <svg width="80" height="80" viewBox="0 0 80 80" aria-hidden="true">
        <circle cx="40" cy="40" r={r} fill="none" stroke="var(--surface-alt)" strokeWidth="8" />
        {todo > 0 && (
          <circle cx="40" cy="40" r={r} fill="none" stroke="var(--border)" strokeWidth="8"
            strokeDasharray={`${d3.dash} ${circ - d3.dash}`}
            strokeDashoffset={d3.offset}
            style={{ transform: 'rotate(-90deg)', transformOrigin: '40px 40px' }} />
        )}
        {inProgress > 0 && (
          <circle cx="40" cy="40" r={r} fill="none" stroke="var(--warning)" strokeWidth="8"
            strokeDasharray={`${d2.dash} ${circ - d2.dash}`}
            strokeDashoffset={d2.offset}
            style={{ transform: 'rotate(-90deg)', transformOrigin: '40px 40px' }} />
        )}
        {done > 0 && (
          <circle cx="40" cy="40" r={r} fill="none" stroke="var(--success)" strokeWidth="8"
            strokeDasharray={`${d1.dash} ${circ - d1.dash}`}
            strokeDashoffset={d1.offset}
            style={{ transform: 'rotate(-90deg)', transformOrigin: '40px 40px' }} />
        )}
        <text x="40" y="44" textAnchor="middle" fontSize="13" fontWeight="700" fill="var(--text)">{pctDone}%</text>
      </svg>
      <div className="donut-legend">
        <span className="legend-dot" style={{ background: 'var(--success)' }} />
        <span className="text-sm">{done} done</span>
        <span className="legend-dot" style={{ background: 'var(--warning)' }} />
        <span className="text-sm">{inProgress} in progress</span>
        <span className="legend-dot" style={{ background: 'var(--border)' }} />
        <span className="text-sm">{todo} to do</span>
      </div>
    </div>
  )
}

// ── AI Briefing card ───────────────────────────────────────────────────────
function BriefingCard({ events, tasks }: { events: CalendarEvent[]; tasks: Task[] }) {
  const now = Date.now()
  const open = tasks.filter(t => t.status !== 'done')
  const overdue = open.filter(t => t.due_at_utc && new Date(t.due_at_utc).getTime() < now)
  const dueToday = open.filter(t => t.due_at_utc && isToday(t.due_at_utc))
  const mostUrgent = [...overdue, ...dueToday.sort((a, b) =>
    new Date(a.due_at_utc!).getTime() - new Date(b.due_at_utc!).getTime()
  )][0]

  let briefing: string
  if (overdue.length > 0 && mostUrgent) {
    briefing = `⚠️ You have ${overdue.length} overdue task${overdue.length > 1 ? 's' : ''}. Focus on "${mostUrgent.title}" first.`
  } else if (events.length > 0 && dueToday.length > 0 && mostUrgent) {
    briefing = `You have ${events.length} event${events.length > 1 ? 's' : ''} and ${dueToday.length} task${dueToday.length > 1 ? 's' : ''} due today. Start with "${mostUrgent.title}" before your first class.`
  } else if (events.length > 0) {
    briefing = `You have ${events.length} event${events.length > 1 ? 's' : ''} scheduled today. A great day to stay on top of your coursework.`
  } else if (open.length > 0 && mostUrgent) {
    briefing = `No classes today — perfect time to focus. Your most urgent task is "${mostUrgent.title}".`
  } else {
    briefing = `Your schedule is clear. A good time to get ahead on upcoming work or review your notes.`
  }

  return (
    <div className="briefing-card card" aria-label="AI Daily Briefing">
      <div className="briefing-header">
        <Zap size={16} aria-hidden="true" className="briefing-icon" />
        <span className="briefing-label">AI Briefing</span>
        <span className="badge badge-ok text-sm">mock provider</span>
      </div>
      <p className="briefing-text">{briefing}</p>
    </div>
  )
}

// ── Main screen ─────────────────────────────────────────────────────────────
export default function TodayScreen() {
  const [events, setEvents] = useState<CalendarEvent[]>([])
  const [tasks, setTasks] = useState<Task[]>([])
  const [announcements, setAnnouncements] = useState<Announcement[]>([])
  const [connectors, setConnectors] = useState<ConnectorStatus[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [refreshedAt, setRefreshedAt] = useState(new Date())
  const navigate = useNavigate()
  const { showToast } = useToast()

  const load = useCallback(() => {
    setLoading(true)
    Promise.all([getEvents(), getTasks(), getAnnouncements(), getConnectors()])
      .then(([ev, tk, an, cn]) => {
        setEvents(ev); setTasks(tk); setAnnouncements(an); setConnectors(cn)
        setRefreshedAt(new Date())
        setLoading(false)
      })
      .catch(e => { setError(String(e)); setLoading(false) })
  }, [])

  useEffect(() => { load() }, [load])

  async function handleMarkDone(task: Task) {
    const newStatus = task.status === 'done' ? 'todo' : 'done'
    try {
      await updateTask(task.id, { status: newStatus })
      setTasks(prev => prev.map(t => t.id === task.id ? { ...t, status: newStatus } : t))
      showToast(newStatus === 'done' ? `✓ "${task.title}" marked done` : `"${task.title}" reopened`, 'success')
    } catch (e) { showToast(String(e), 'error') }
  }

  const todayEvents = events.filter(e => isToday(e.start_at_utc))
    .sort((a, b) => new Date(a.start_at_utc).getTime() - new Date(b.start_at_utc).getTime())
  const openTasks = tasks.filter(t => t.status !== 'done').slice(0, 6)

  const doneCnt = tasks.filter(t => t.status === 'done').length
  const ipCnt = tasks.filter(t => t.status === 'in_progress').length
  const todoCnt = tasks.filter(t => t.status === 'todo').length

  const dateStr = new Date().toLocaleDateString('en-US', {
    weekday: 'long', year: 'numeric', month: 'long', day: 'numeric', timeZone: 'America/New_York',
  })

  if (error) return (
    <div className="state-error" role="alert">
      Failed to load data: {error}
      <button className="btn btn-ghost btn-sm" style={{ marginLeft: '1rem' }} onClick={load}>Retry</button>
    </div>
  )

  return (
    <div>
      {/* Header */}
      <div className="today-header">
        <div>
          <h1>{greeting()}, Alex!</h1>
          <p className="text-muted">{dateStr}</p>
        </div>
        <div className="today-actions">
          <button
            className="btn btn-primary"
            onClick={() => navigate('/planner')}
            aria-label="Generate my plan for today"
          >
            <Zap size={15} aria-hidden="true" /> Generate My Day
          </button>
          <button
            className="btn btn-ghost btn-icon"
            onClick={load}
            disabled={loading}
            aria-label="Refresh data"
            title="Refresh"
          >
            <RefreshCw size={15} className={loading ? 'spin' : ''} aria-hidden="true" />
          </button>
        </div>
      </div>

      {/* AI Briefing */}
      {!loading && <BriefingCard events={todayEvents} tasks={tasks} />}

      {/* Summary strip */}
      <div className="today-strip">
        <div className="today-stat card">
          <Calendar size={18} className="stat-icon" aria-hidden="true" />
          <span className="stat-n">{todayEvents.length}</span>
          <span className="stat-l">events today</span>
        </div>
        <div className="today-stat card">
          <CheckSquare size={18} className="stat-icon" aria-hidden="true" />
          <span className="stat-n">{openTasks.length}</span>
          <span className="stat-l">open tasks</span>
        </div>
        <div className="today-stat card" style={{ gridColumn: 'span 1' }}>
          {loading
            ? <span className="stat-l">Loading…</span>
            : <DonutChart done={doneCnt} inProgress={ipCnt} todo={todoCnt} />
          }
        </div>
      </div>

      <div className="today-grid">
        {/* Today's events */}
        <section aria-labelledby="today-events-heading">
          <h2 id="today-events-heading">Today's Schedule</h2>
          {loading
            ? <SkeletonList count={2} lines={3} />
            : todayEvents.length === 0
              ? (
                <div className="state-empty">
                  <p>No events today.</p>
                  <button className="btn btn-ghost btn-sm" onClick={() => navigate('/planner')}>
                    Import calendar →
                  </button>
                </div>
              )
              : (
                <ul className="event-list">
                  {todayEvents.map(ev => (
                    <li key={ev.id} className="event-item card card-hover">
                      <div className="event-time">
                        <Clock size={12} aria-hidden="true" /> {fmtTime(ev.start_at_utc)} – {fmtTime(ev.end_at_utc)}
                      </div>
                      <div className="event-title">{ev.title}</div>
                      {ev.location_text && (
                        <div className="text-muted text-sm">
                          <MapPin size={11} aria-hidden="true" /> {ev.location_text}
                        </div>
                      )}
                      <span className={`badge ${ev.source_type === 'demo' ? 'badge-demo' : 'badge-ok'}`}>
                        {ev.source_type === 'demo' ? 'DEMO' : ev.source_type}
                      </span>
                    </li>
                  ))}
                </ul>
              )
          }
        </section>

        {/* Tasks with inline mark-done */}
        <section aria-labelledby="today-tasks-heading">
          <h2 id="today-tasks-heading">Open Tasks</h2>
          {loading
            ? <SkeletonList count={3} lines={2} />
            : openTasks.length === 0
              ? (
                <div className="state-empty">
                  <p>No open tasks.</p>
                  <button className="btn btn-ghost btn-sm" onClick={() => navigate('/tasks')}>
                    Add a task →
                  </button>
                </div>
              )
              : (
                <ul className="task-list">
                  {openTasks.map(t => {
                    const due = fmtDue(t.due_at_utc)
                    return (
                      <li key={t.id} className="task-item card card-hover">
                        <div className="flex items-center gap-1">
                          <input
                            type="checkbox"
                            checked={t.status === 'done'}
                            onChange={() => handleMarkDone(t)}
                            aria-label={`Mark "${t.title}" as done`}
                            style={{ width: 'auto', cursor: 'pointer', flexShrink: 0 }}
                          />
                          <span className="task-title" style={{ flex: 1 }}>{t.title}</span>
                          <span className={`badge badge-${t.priority === 'urgent' ? 'err' : t.priority === 'high' ? 'warn' : 'ok'}`}>
                            {t.priority}
                          </span>
                        </div>
                        {t.course_label && <div className="text-muted text-sm">{t.course_label}</div>}
                        {due && (
                          <div className={`text-sm ${due.isOverdue ? 'overdue-text' : 'text-muted'}`}>
                            {due.isOverdue ? '⚠ Overdue: ' : 'Due: '}{due.str} · {t.estimated_minutes} min
                          </div>
                        )}
                        {t.source_type === 'demo' && <span className="badge badge-demo">DEMO DATA</span>}
                      </li>
                    )
                  })}
                </ul>
              )
          }
        </section>
      </div>

      {/* Announcements */}
      <section aria-labelledby="today-ann-heading" className="mt-2">
        <h2 id="today-ann-heading">Announcements <span className="badge badge-demo">DEMO DATA</span></h2>
        {loading
          ? <SkeletonList count={2} lines={3} />
          : announcements.length === 0
            ? <p className="text-muted">No announcements.</p>
            : (
              <ul className="ann-list">
                {announcements.slice(0, 4).map(a => (
                  <li key={a.id} className="card ann-item card-hover">
                    <div className="flex justify-between items-center">
                      <strong>{a.title}</strong>
                      <span className="text-muted text-sm">{a.course_label}</span>
                    </div>
                    <p className="text-sm mt-1">{a.body_summary}</p>
                  </li>
                ))}
              </ul>
            )
        }
      </section>

      {/* Weather */}
      <section aria-labelledby="weather-heading" className="mt-2">
        <div className="card flex items-center gap-2" style={{ flexWrap: 'wrap' }}>
          <div>
            <strong id="weather-heading">Weather — Stony Brook, NY</strong>
            <div className="text-muted text-sm">~12.5 °C · Partly Cloudy · Humidity 62%</div>
          </div>
          <span className="badge badge-demo" style={{ marginLeft: 'auto' }}>SAMPLE FIXTURE</span>
        </div>
      </section>

      {/* Connector status */}
      <section aria-labelledby="conn-status-heading" className="mt-2">
        <h3 id="conn-status-heading">Data Sources</h3>
        <div className="connector-strip">
          {connectors.slice(0, 4).map(c => (
            <div key={c.name} className="connector-pill">
              <span className={`conn-dot conn-${c.status}`} aria-hidden="true" />
              <span className="text-sm">{c.name.split(' ')[0]}</span>
              <span className={`badge badge-${c.status === 'connected' ? 'ok' : c.status === 'demo' ? 'demo' : 'warn'}`}>
                {c.status}
              </span>
            </div>
          ))}
        </div>
        <p className="text-muted text-sm mt-1">
          Refreshed: {refreshedAt.toLocaleTimeString('en-US', { timeZone: 'America/New_York' })}
        </p>
      </section>
    </div>
  )
}
