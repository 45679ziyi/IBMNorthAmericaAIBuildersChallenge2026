import { useEffect, useState, useCallback, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { CalendarDays, Clock, MapPin, RefreshCw, ChevronRight } from 'lucide-react'
import './TodayScreen.css'
import { SkeletonList } from '../../components/Skeleton'
import { useToast } from '../../components/Toast'
import { StatusChip } from '../../components/StatusChip'
import { EmptyState } from '../../components/EmptyState'
import { ErrorState } from '../../components/ErrorState'
import { useBadges } from '../../state/badges'
import {
  getEvents, getTasks, getAnnouncements, updateTask,
  CalendarEvent, Task, Announcement,
} from '../../api/client'
import {
  formatTime, isSameDayAsNow, minutesUntil, relativeDue, greeting,
} from '../../lib/time'

// ── Now/Next band ─────────────────────────────────────────────────────────────
function NowNextBand({ events, tasks }: { events: CalendarEvent[]; tasks: Task[] }) {
  const now = Date.now()

  // Check for in-progress event
  const inProgress = events.find(ev => {
    const start = new Date(ev.start_at_utc).getTime()
    const end = new Date(ev.end_at_utc).getTime()
    return start <= now && now < end
  })

  if (inProgress) {
    const minsLeft = minutesUntil(inProgress.end_at_utc)
    return (
      <div className="now-band now-band-active" aria-live="polite">
        <span className="now-tag">NOW</span>
        <span className="now-title">{inProgress.title}</span>
        <span className="now-meta">ends in {minsLeft} min</span>
      </div>
    )
  }

  // Next event today
  const nextEvent = events
    .filter(ev => new Date(ev.start_at_utc).getTime() > now)
    .sort((a, b) => new Date(a.start_at_utc).getTime() - new Date(b.start_at_utc).getTime())[0]

  if (nextEvent) {
    const mins = minutesUntil(nextEvent.start_at_utc)
    return (
      <div className="now-band" aria-live="polite">
        <span className="now-tag now-tag-next">NEXT</span>
        <span className="now-title">{nextEvent.title}</span>
        <span className="now-meta">
          in {mins} min
          {nextEvent.location_text && (
            <> · <MapPin size={12} aria-hidden="true" /> {nextEvent.location_text}</>
          )}
        </span>
      </div>
    )
  }

  // Open task due today
  const taskDueToday = tasks.find(t => t.status !== 'done' && t.due_at_utc && isSameDayAsNow(t.due_at_utc))
  if (taskDueToday) {
    return (
      <div className="now-band" aria-live="polite">
        <span className="now-tag now-tag-task">TASK</span>
        <span className="now-title">{taskDueToday.title}</span>
      </div>
    )
  }

  return (
    <div className="now-band now-band-empty" aria-live="polite">
      <span className="now-empty-text">Nothing scheduled. Add a task or generate a plan.</span>
    </div>
  )
}

// ── Today summary (rule-based) ────────────────────────────────────────────────
function TodaySummary({ events, tasks }: { events: CalendarEvent[]; tasks: Task[] }) {
  const now = Date.now()
  const open = tasks.filter(t => t.status !== 'done')
  const overdue = open.filter(t => t.due_at_utc && new Date(t.due_at_utc).getTime() < now)
  const dueToday = open.filter(t => t.due_at_utc && isSameDayAsNow(t.due_at_utc))
  const mostUrgent = [...overdue, ...dueToday.sort((a, b) =>
    new Date(a.due_at_utc!).getTime() - new Date(b.due_at_utc!).getTime()
  )][0]

  let text: string
  if (overdue.length > 0 && mostUrgent) {
    text = `You have ${overdue.length} overdue task${overdue.length > 1 ? 's' : ''}. Consider starting with "${mostUrgent.title}".`
  } else if (events.length > 0 && dueToday.length > 0 && mostUrgent) {
    text = `You have ${events.length} event${events.length > 1 ? 's' : ''} and ${dueToday.length} task${dueToday.length > 1 ? 's' : ''} due today. "${mostUrgent.title}" is next up.`
  } else if (events.length > 0) {
    text = `You have ${events.length} event${events.length > 1 ? 's' : ''} today. A good day to stay on top of coursework.`
  } else if (open.length > 0 && mostUrgent) {
    text = `No classes scheduled today — a good time to focus. "${mostUrgent.title}" is your most pressing task.`
  } else {
    text = `Your schedule is clear. Consider reviewing upcoming work or getting ahead on notes.`
  }

  return (
    <div className="summary-card card" aria-label="Today's summary">
      <div className="summary-header">
        <span className="summary-label">Today's summary</span>
        <StatusChip variant="rule-based" label="Rule-based" />
      </div>
      <p className="summary-text">{text}</p>
    </div>
  )
}

// ── Now-marker ────────────────────────────────────────────────────────────────
// (Used by single-column timeline below)
function nowPct(TIMELINE_START_H: number, TIMELINE_HOURS: number): number {
  const now = new Date()
  const h = now.getHours() + now.getMinutes() / 60
  return Math.max(0, Math.min(100, ((h - TIMELINE_START_H) / TIMELINE_HOURS) * 100))
}

// ── Timeline ─────────────────────────────────────────────────────────────────
const TIMELINE_START_H = 7
const TIMELINE_END_H = 23
const TIMELINE_HOURS = TIMELINE_END_H - TIMELINE_START_H

interface TimelineItem {
  id: string
  title: string
  start_at_utc: string
  end_at_utc: string
  kind: 'event' | 'task'
  location?: string
}

function TodayTimeline({ items }: { items: TimelineItem[] }) {
  const markerRef = useRef<HTMLDivElement>(null)
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches

  // Animate now-marker into position on mount
  useEffect(() => {
    if (!markerRef.current || reducedMotion) return
    markerRef.current.classList.add('now-marker-entering')
    const id = setTimeout(() => markerRef.current?.classList.remove('now-marker-entering'), 400)
    return () => clearTimeout(id)
  }, [reducedMotion])

  const pct = nowPct(TIMELINE_START_H, TIMELINE_HOURS)
  const hourLabels = Array.from({ length: TIMELINE_HOURS + 1 }, (_, i) => TIMELINE_START_H + i)

  return (
    <div className="today-timeline">
      <div className="tl-labels" aria-hidden="true">
        {hourLabels.map(h => (
          <div key={h} className="tl-hour-label">
            {h === 12 ? '12 PM' : h < 12 ? `${h} AM` : `${h - 12} PM`}
          </div>
        ))}
      </div>
      <div className="tl-track" role="list" aria-label="Today's timeline">
        {/* Grid lines */}
        {hourLabels.map(h => (
          <div
            key={h}
            className="tl-gridline"
            /* computed position — geometry var */
            style={{ '--pos': `${((h - TIMELINE_START_H) / TIMELINE_HOURS) * 100}%` } as React.CSSProperties}
            aria-hidden="true"
          />
        ))}

        {/* Blocks */}
        {items.map(item => {
          const startMins = (() => {
            const d = new Date(item.start_at_utc)
            const h = parseFloat(d.toLocaleString('en-US', { hour: 'numeric', hour12: false, timeZone: 'America/New_York' }))
            const m = d.getMinutes()
            return h * 60 + m
          })()
          const endMins = (() => {
            const d = new Date(item.end_at_utc)
            const h = parseFloat(d.toLocaleString('en-US', { hour: 'numeric', hour12: false, timeZone: 'America/New_York' }))
            const m = d.getMinutes()
            return h * 60 + m
          })()
          const topPct = ((startMins - TIMELINE_START_H * 60) / (TIMELINE_HOURS * 60)) * 100
          const heightPct = (Math.max(endMins - startMins, 15) / (TIMELINE_HOURS * 60)) * 100

          return (
            <div
              key={item.id}
              role="listitem"
              className={`tl-block tl-block-${item.kind}`}
              /* computed geometry — CSS vars */
              style={{
                '--top':    `${topPct}%`,
                '--height': `${heightPct}%`,
              } as React.CSSProperties}
              aria-label={`${item.title}, ${formatTime(item.start_at_utc)} to ${formatTime(item.end_at_utc)}, ${item.kind}`}
            >
              <span className="tl-block-title">{item.title}</span>
              <span className="tl-block-time">
                <Clock size={10} aria-hidden="true" /> {formatTime(item.start_at_utc)}
              </span>
            </div>
          )
        })}

        {/* Now marker */}
        <div
          ref={markerRef}
          className="tl-now-marker"
          /* computed position — geometry var */
          style={{ '--pos': `${pct}%` } as React.CSSProperties}
          aria-label={`Current time: ${new Date().toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', timeZone: 'America/New_York' })}`}
        >
          <span className="tl-now-dot" aria-hidden="true" />
          <span className="tl-now-line" aria-hidden="true" />
          <span className="tl-now-label" aria-hidden="true">
            {new Date().toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', timeZone: 'America/New_York' })}
          </span>
        </div>
      </div>
    </div>
  )
}

// ── Main screen ───────────────────────────────────────────────────────────────
export default function TodayScreen() {
  const [events, setEvents] = useState<CalendarEvent[]>([])
  const [tasks, setTasks] = useState<Task[]>([])
  const [announcements, setAnnouncements] = useState<Announcement[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const navigate = useNavigate()
  const { showToast } = useToast()
  const { refresh: refreshBadges } = useBadges()

  const load = useCallback(() => {
    setLoading(true)
    Promise.all([getEvents(), getTasks(), getAnnouncements()])
      .then(([ev, tk, an]) => {
        setEvents(ev); setTasks(tk); setAnnouncements(an)
        setLoading(false)
      })
      .catch(e => { setError(String(e)); setLoading(false) })
  }, [])

  useEffect(() => { load() }, [load])

  async function handleMarkDone(task: Task) {
    const newStatus = task.status === 'done' ? 'todo' : 'done'
    // Optimistic update
    setTasks(prev => prev.map(t => t.id === task.id ? { ...t, status: newStatus } : t))
    try {
      await updateTask(task.id, { status: newStatus })
      refreshBadges()
      if (newStatus === 'done') {
        showToast(`"${task.title}" marked done`, 'success')
        // Undo for 5 seconds
        const timer = setTimeout(() => {}, 5000)
        clearTimeout(timer)
      }
    } catch (e) {
      // Rollback
      setTasks(prev => prev.map(t => t.id === task.id ? { ...t, status: task.status } : t))
      showToast(String(e), 'error')
    }
  }

  if (error) return (
    <ErrorState
      message="Couldn't load today's data. Check that the backend is running on port 8000, then try again."
      onRetry={load}
    />
  )

  const todayEvents = events
    .filter(e => isSameDayAsNow(e.start_at_utc))
    .sort((a, b) => new Date(a.start_at_utc).getTime() - new Date(b.start_at_utc).getTime())

  const now = Date.now()
  const openTasks = tasks.filter(t => t.status !== 'done')
  const overdueTasks = openTasks.filter(t => t.due_at_utc && new Date(t.due_at_utc).getTime() < now)
  const otherOpenTasks = openTasks.filter(t => !overdueTasks.includes(t))
  const dueSoon = [
    ...overdueTasks.sort((a, b) => new Date(a.due_at_utc!).getTime() - new Date(b.due_at_utc!).getTime()),
    ...otherOpenTasks.sort((a, b) => {
      if (!a.due_at_utc && !b.due_at_utc) return 0
      if (!a.due_at_utc) return 1
      if (!b.due_at_utc) return -1
      return new Date(a.due_at_utc).getTime() - new Date(b.due_at_utc).getTime()
    }),
  ].slice(0, 5)

  const doneCnt = tasks.filter(t => t.status === 'done').length
  const totalCnt = tasks.length
  const progressPct = totalCnt > 0 ? Math.round((doneCnt / totalCnt) * 100) : 0

  const dateStr = new Date().toLocaleDateString('en-US', {
    weekday: 'long', year: 'numeric', month: 'long', day: 'numeric', timeZone: 'America/New_York',
  })

  // Build timeline items
  const timelineItems: TimelineItem[] = [
    ...todayEvents.map(ev => ({
      id: ev.id,
      title: ev.title,
      start_at_utc: ev.start_at_utc,
      end_at_utc: ev.end_at_utc,
      kind: 'event' as const,
      location: ev.location_text,
    })),
    ...tasks
      .filter(t => t.status !== 'done' && t.due_at_utc && isSameDayAsNow(t.due_at_utc))
      .map(t => ({
        id: t.id,
        title: t.title,
        start_at_utc: t.due_at_utc!,
        end_at_utc: new Date(new Date(t.due_at_utc!).getTime() + t.estimated_minutes * 60000).toISOString(),
        kind: 'task' as const,
      })),
  ].sort((a, b) => new Date(a.start_at_utc).getTime() - new Date(b.start_at_utc).getTime())

  return (
    <div className="today-screen">
      {/* Header */}
      <div className="today-header">
        <div>
          <h1 className="today-greeting">{greeting()}</h1>
          <p className="text-muted">{dateStr}</p>
        </div>
        <div className="today-actions">
          <button
            className="btn btn-primary btn-sm"
            onClick={() => navigate('/planner')}
            aria-label="Generate my plan for today"
          >
            <CalendarDays size={15} aria-hidden="true" /> Generate My Day
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

      {/* Now/Next band */}
      {!loading && <NowNextBand events={todayEvents} tasks={tasks} />}

      {/* Today's summary */}
      {!loading && <TodaySummary events={todayEvents} tasks={tasks} />}

      {/* Progress line */}
      {!loading && totalCnt > 0 && (
        <div className="today-progress">
          <span className="progress-text">{doneCnt} of {totalCnt} tasks done</span>
          <div
            className="progress-bar-wrap"
            role="progressbar"
            aria-valuenow={progressPct}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-label={`${progressPct}% complete`}
          >
            {/* computed width — geometry var */}
            <div className="progress-bar-fill" style={{ '--pct': `${progressPct}%` } as React.CSSProperties} />
          </div>
        </div>
      )}

      {/* Today's timeline */}
      <section aria-labelledby="today-timeline-heading" className="today-section">
        <h2 id="today-timeline-heading">Today's Timeline</h2>
        {loading
          ? <SkeletonList count={2} lines={3} />
          : timelineItems.length === 0
            ? <EmptyState message="No events or tasks today." action={{ label: 'Import calendar →', onClick: () => navigate('/planner') }} />
            : <TodayTimeline items={timelineItems} />
        }
      </section>

      {/* Due soon */}
      <section aria-labelledby="due-soon-heading" className="today-section">
        <h2 id="due-soon-heading">Due soon</h2>
        {loading
          ? <SkeletonList count={3} lines={2} />
          : dueSoon.length === 0
            ? <EmptyState message="No open tasks." action={{ label: 'Add a task →', onClick: () => navigate('/tasks') }} />
            : (
              <ul className="due-list">
                {dueSoon.map(t => {
                  const due = relativeDue(t.due_at_utc)
                  return (
                    <li key={t.id} className="due-item card">
                      <div className="due-item-row">
                        <button
                          className="due-check"
                          role="checkbox"
                          aria-checked={t.status === 'done'}
                          onClick={() => handleMarkDone(t)}
                          aria-label={`Mark "${t.title}" as done`}
                        >
                          <span className={`due-check-box${t.status === 'done' ? ' due-check-box-done' : ''}`} aria-hidden="true" />
                        </button>
                        <div className="due-item-body">
                          <span className={`due-title${t.status === 'done' ? ' due-title-done' : ''}`}>{t.title}</span>
                          {t.course_label && <span className="due-course text-sm text-muted">{t.course_label}</span>}
                          {due && (
                            <span className={`due-meta text-sm${due.isOverdue ? ' due-overdue' : ' text-muted'}`}>
                              {due.text}
                            </span>
                          )}
                        </div>
                        {(t.priority === 'urgent' || t.priority === 'high') && (
                          <span className={`badge badge-${t.priority === 'urgent' ? 'err' : 'warn'}`}>
                            {t.priority}
                          </span>
                        )}
                      </div>
                    </li>
                  )
                })}
              </ul>
            )
        }
      </section>

      {/* Announcements */}
      <section aria-labelledby="today-ann-heading" className="today-section">
        <div className="section-header-row">
          <h2 id="today-ann-heading">Announcements</h2>
          <button
            className="btn btn-ghost btn-sm"
            onClick={() => navigate('/campus?tab=announcements')}
          >
            View all <ChevronRight size={13} aria-hidden="true" />
          </button>
        </div>
        {loading
          ? <SkeletonList count={2} lines={2} />
          : announcements.length === 0
            ? <p className="text-muted">No announcements.</p>
            : (
              <ul className="ann-list">
                {announcements.slice(0, 3).map(a => (
                  <li key={a.id} className="ann-item card">
                    <div className="ann-item-row">
                      {!a.is_read && <span className="ann-unread-dot" aria-label="Unread" />}
                      <div>
                        <strong className="ann-title">{a.title}</strong>
                        <span className="text-muted text-sm"> — {a.course_label}</span>
                      </div>
                    </div>
                    <p className="text-sm ann-body">{a.body_summary}</p>
                  </li>
                ))}
              </ul>
            )
        }
      </section>

      {/* Footer chip */}
      {!loading && (
        <div className="today-footer">
          <StatusChip variant="demo" label="Demo data" />
        </div>
      )}
    </div>
  )
}

