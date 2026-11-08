import { useEffect, useState, useCallback, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { CalendarDays, Clock, MapPin, RefreshCw, ChevronRight, Settings, HelpCircle } from 'lucide-react'
import './TodayScreen.css'
import { SkeletonList } from '../../components/Skeleton'
import { useToast } from '../../components/Toast'
import { StatusChip } from '../../components/StatusChip'
import { EmptyState } from '../../components/EmptyState'
import { ErrorState } from '../../components/ErrorState'
import { Sheet } from '../../components/Sheet'
import { useBadges } from '../../state/badges'
import {
  getEvents, getTasks, getAnnouncements, updateTask, getMoves, getHandledMoves,
  getSignals, getFeedsStatus, approveMoveReq, dismissMove as dismissMoveApi, undoMoveAll,
  CalendarEvent, Task, Announcement, Move, Signal, FeedStatus,
} from '../../api/client'
import {
  formatTime, relativeDue, greeting,
  minutesIntoDay, CAMPUS_TZ, dayKey,
} from '../../lib/time'
import { useNow } from '../../hooks/useNow'
import { AutonomySheet } from './AutonomySheet'

// ── Human-readable action descriptions ───────────────────────────────────────
function describeAction(action: Move['actions'][number]): string {
  const p = action.params as Record<string, unknown>
  switch (action.type) {
    case 'create_calendar_block': {
      const title = String(p.title ?? 'block')
      const start = p.start_at_utc ? formatTime(String(p.start_at_utc)) : ''
      const end   = p.end_at_utc   ? formatTime(String(p.end_at_utc))   : ''
      return start && end ? `Add "${title}" ${start}–${end}` : `Add "${title}" block`
    }
    case 'create_reminder':
      return `Set reminder at ${p.at_utc ? formatTime(String(p.at_utc)) : 'scheduled time'}`
    case 'send_message_draft':
      return `Draft message to ${p.recipient ?? 'recipient'}`
    case 'mark_task_done':
      return `Mark task as done`
    case 'update_task_priority':
      return `Update task priority to ${p.priority ?? 'normal'}`
    default:
      return action.type.replace(/_/g, ' ')
  }
}

function approveButtonLabel(move: Move): string {
  if (move.actions.length === 0) return 'Approve'
  const descriptions = move.actions.map(describeAction)
  return descriptions.join(' and ')
}

function kindExplanation(kind: string): string {
  switch (kind) {
    case 'deadline_risk':
      return 'AURORA detected an open task due within 36 hours with unscheduled time remaining.'
    case 'schedule_conflict':
      return 'AURORA detected overlapping calendar events that need resolution.'
    case 'change_impact':
      return 'AURORA detected a schedule change that may affect your plans.'
    case 'forecast_change':
      return 'AURORA detected a weather change relevant to your campus commute.'
    case 'campus_closure':
      return 'AURORA detected a campus closure or room change announcement.'
    case 'transit_delay':
      return 'AURORA detected a transit disruption on your typical route.'
    default:
      return `AURORA detected a ${kind.replace(/_/g, ' ')} situation.`
  }
}

// ── Now/Next band ─────────────────────────────────────────────────────────────
function NowNextBand({ events, tasks, now }: { events: CalendarEvent[]; tasks: Task[]; now: Date }) {
  const nowMs = now.getTime()

  const inProgress = events.find(ev => {
    const start = new Date(ev.start_at_utc).getTime()
    const end   = new Date(ev.end_at_utc).getTime()
    return start <= nowMs && nowMs < end
  })

  if (inProgress) {
    const minsLeft = Math.round((new Date(inProgress.end_at_utc).getTime() - nowMs) / 60_000)
    return (
      <div className="now-band now-band-active" aria-live="polite">
        <span className="now-tag">NOW</span>
        <span className="now-title">{inProgress.title}</span>
        <span className="now-meta">ends in {minsLeft} min</span>
      </div>
    )
  }

  const nextEvent = events
    .filter(ev => new Date(ev.start_at_utc).getTime() > nowMs)
    .sort((a, b) => new Date(a.start_at_utc).getTime() - new Date(b.start_at_utc).getTime())[0]

  if (nextEvent) {
    const mins = Math.round((new Date(nextEvent.start_at_utc).getTime() - nowMs) / 60_000)
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

  const todayKey = dayKey(now)
  const taskDueToday = tasks.find(t =>
    t.status !== 'done' && t.due_at_utc && dayKey(t.due_at_utc) === todayKey
  )
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
function TodaySummary({ events, tasks, now }: { events: CalendarEvent[]; tasks: Task[]; now: Date }) {
  const nowMs = now.getTime()
  const todayKey = dayKey(now)
  const open = tasks.filter(t => t.status !== 'done')
  const overdue = open.filter(t => t.due_at_utc && new Date(t.due_at_utc).getTime() < nowMs)
  const dueToday = open.filter(t => t.due_at_utc && dayKey(t.due_at_utc) === todayKey)
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

// ── Why drawer ────────────────────────────────────────────────────────────────
function WhyDrawer({ move, open, onClose }: { move: Move | null; open: boolean; onClose: () => void }) {
  if (!move) return null
  return (
    <Sheet open={open} onClose={onClose} title="Why AURORA proposed this">
      <div className="why-drawer">
        <h4 className="why-section-title">Evidence</h4>
        <ul className="why-evidence-list">
          {move.why.map((w, i) => (
            <li key={i} className="why-evidence-item">
              <span className="why-feed-chip">{w.feed}</span>
              <span className="why-evidence-text">{w.text}</span>
            </li>
          ))}
        </ul>

        <h4 className="why-section-title">What will happen if you approve</h4>
        <ul className="why-actions-list">
          {move.actions.map((a, i) => (
            <li key={i} className="why-action-item">
              <span className="why-action-text">{describeAction(a)}</span>
              {a.simulated && <StatusChip variant="synthetic" label="Simulated" />}
            </li>
          ))}
        </ul>

        <h4 className="why-section-title">Rule</h4>
        <p className="why-rule-text">{kindExplanation(move.kind)}</p>
      </div>
    </Sheet>
  )
}

// ── Move card ─────────────────────────────────────────────────────────────────
interface MoveCardProps {
  move: Move
  onApprove: (id: string) => void
  onDismiss: (id: string) => void
  onWhyClick: (move: Move) => void
  isNew: boolean
}

function MoveCard({ move, onApprove, onDismiss, onWhyClick, isNew }: MoveCardProps) {
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  const cardRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!isNew || reducedMotion || !cardRef.current) return
    cardRef.current.classList.add('move-card-enter')
    const id = setTimeout(() => cardRef.current?.classList.remove('move-card-enter'), 320)
    return () => clearTimeout(id)
  }, [isNew, reducedMotion])

  const approveLabel = approveButtonLabel(move)

  return (
    <div ref={cardRef} className="move-card card" aria-label={`Decision: ${move.title}`}>
      <div className="move-card-header">
        <strong className="move-card-title">{move.title}</strong>
        <span className={`badge badge-${move.urgency === 'high' ? 'err' : move.urgency === 'medium' ? 'warn' : 'ok'}`}>
          {move.urgency}
        </span>
      </div>
      <p className="move-card-summary">{move.summary}</p>
      <div className="move-card-actions">
        <button
          className="btn btn-primary btn-sm move-approve-btn"
          onClick={() => onApprove(move.id)}
          title={approveLabel}
        >
          {approveLabel.length > 60 ? 'Approve' : approveLabel}
        </button>
        <button
          className="btn btn-ghost btn-sm"
          onClick={() => onDismiss(move.id)}
        >
          Not now
        </button>
        <button
          className="btn btn-ghost btn-sm move-why-btn"
          onClick={() => onWhyClick(move)}
          aria-label="Why did AURORA suggest this?"
        >
          <HelpCircle size={13} aria-hidden="true" /> Why this?
        </button>
      </div>
    </div>
  )
}

// ── Handled section ───────────────────────────────────────────────────────────
function HandledSection({
  handledMoves,
  feedStatuses,
  onUndo,
  simMode,
}: {
  handledMoves: Move[]
  feedStatuses: FeedStatus[]
  onUndo: (id: string) => void
  simMode: boolean
}) {
  const autoApplied = handledMoves.filter(m => m.status === 'auto_applied')
  const totalFiltered = feedStatuses.reduce((s, f) => s + f.signals_filtered, 0)

  if (autoApplied.length === 0 && totalFiltered === 0) return null

  return (
    <section className="today-section" aria-labelledby="handled-heading">
      <h2 id="handled-heading">Handled for you</h2>
      {autoApplied.length > 0 && (
        <ul className="handled-list">
          {autoApplied.map(m => (
            <li key={m.id} className="handled-item card">
              <span className="handled-title">{m.title}</span>
              <button
                className="btn btn-ghost btn-sm"
                onClick={() => onUndo(m.id)}
              >
                Undo
              </button>
            </li>
          ))}
        </ul>
      )}
      {totalFiltered > 0 && (
        <p className="handled-filtered-note text-muted text-sm">
          {totalFiltered} signal{totalFiltered !== 1 ? 's' : ''} filtered as not relevant to you
          {simMode ? ' (simulated day)' : ''}
        </p>
      )}
    </section>
  )
}

// ── Sources strip ─────────────────────────────────────────────────────────────
interface FeedSignalsSheetProps {
  feed: string | null
  signals: Signal[]
  open: boolean
  onClose: () => void
}

function FeedSignalsSheet({ feed, signals, open, onClose }: FeedSignalsSheetProps) {
  const feedSignals = signals.filter(s => s.feed === feed)
  return (
    <Sheet open={open} onClose={onClose} title={`Recent signals — ${feed ?? ''}`}>
      {feedSignals.length === 0
        ? <p className="text-muted">No recent signals from this feed.</p>
        : (
          <ul className="feed-signals-list">
            {feedSignals.slice(0, 10).map(s => (
              <li key={s.id} className="feed-signal-item card">
                <div className="feed-signal-header">
                  <span className="feed-signal-time text-sm text-muted">{formatTime(s.at_utc)}</span>
                  <span className={`badge badge-${s.relevance === 'high' ? 'warn' : 'ok'}`}>{s.relevance}</span>
                </div>
                <p className="feed-signal-summary text-sm">{s.summary}</p>
              </li>
            ))}
          </ul>
        )
      }
    </Sheet>
  )
}

function SourcesStrip({ feedStatuses, onFeedClick }: { feedStatuses: FeedStatus[]; onFeedClick: (feed: string) => void }) {
  if (feedStatuses.length === 0) return null
  return (
    <section className="today-section sources-strip-section" aria-labelledby="sources-heading">
      <h2 id="sources-heading">Data sources</h2>
      <div className="sources-strip" role="list">
        {feedStatuses.map(f => (
          <button
            key={f.feed}
            role="listitem"
            className="source-chip btn btn-ghost"
            onClick={() => onFeedClick(f.feed)}
            title={`Click to see recent signals from ${f.feed}`}
          >
            <span className="source-name">{f.feed.replace(/_/g, ' ')}</span>
            {f.last_signal_at && (
              <span className="source-time text-sm text-muted">
                Updated {formatTime(f.last_signal_at)}
              </span>
            )}
            <StatusChip variant="synthetic" label="Synthetic" />
          </button>
        ))}
      </div>
    </section>
  )
}

// ── Day summary counters ──────────────────────────────────────────────────────
function DaySummaryCounters({
  feedStatuses,
  handledMoves,
  proposedMoves,
  simMode,
}: {
  feedStatuses: FeedStatus[]
  handledMoves: Move[]
  proposedMoves: Move[]
  simMode: boolean
}) {
  const feedsChecked    = feedStatuses.length
  const signalsProcessed = feedStatuses.reduce((s, f) => s + f.signals_seen, 0)
  const signalsFiltered  = feedStatuses.reduce((s, f) => s + f.signals_filtered, 0)
  const handledAuto      = handledMoves.filter(m => m.status === 'auto_applied').length
  const decisionsAsked   = proposedMoves.length

  const counters = [
    { label: 'Feeds checked',       value: feedsChecked       },
    { label: 'Signals processed',   value: signalsProcessed   },
    { label: 'Signals filtered',    value: signalsFiltered    },
    { label: 'Handled automatically', value: handledAuto      },
    { label: 'Decisions asked',     value: decisionsAsked     },
  ]

  return (
    <section className="today-section day-counters-section" aria-labelledby="day-counters-heading">
      <h2 id="day-counters-heading">
        Day at a glance
        <span className="day-counters-mode text-muted text-sm">
          {simMode ? ' — simulated day' : ' — real-time'}
        </span>
      </h2>
      <div className="day-counters">
        {counters.map(c => (
          <div key={c.label} className="day-counter-item">
            <span className="day-counter-value">{c.value}</span>
            <span className="day-counter-label text-muted text-sm">{c.label}</span>
          </div>
        ))}
      </div>
    </section>
  )
}

// ── Now-marker ────────────────────────────────────────────────────────────────
function nowPct(now: Date, TIMELINE_START_H: number, TIMELINE_HOURS: number): number {
  const mins = minutesIntoDay(now)
  return Math.max(0, Math.min(100, ((mins - TIMELINE_START_H * 60) / (TIMELINE_HOURS * 60)) * 100))
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
  kind: 'event' | 'task' | 'aurora'
  location?: string
}

interface SignalFlag {
  signal: Signal
  pct: number
}

interface RainBand {
  startPct: number
  heightPct: number
}

interface LeaveByMarker {
  pct: number
  label: string
}

function TodayTimeline({
  items,
  signalFlags,
  rainBand,
  leaveBy,
  now,
}: {
  items: TimelineItem[]
  signalFlags: SignalFlag[]
  rainBand: RainBand | null
  leaveBy: LeaveByMarker | null
  now: Date
}) {
  const markerRef = useRef<HTMLDivElement>(null)
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  const [tooltipSignal, setTooltipSignal] = useState<Signal | null>(null)

  useEffect(() => {
    if (!markerRef.current || reducedMotion) return
    markerRef.current.classList.add('now-marker-entering')
    const id = setTimeout(() => markerRef.current?.classList.remove('now-marker-entering'), 400)
    return () => clearTimeout(id)
  }, [reducedMotion])

  const pct = nowPct(now, TIMELINE_START_H, TIMELINE_HOURS)
  const hourLabels = Array.from({ length: TIMELINE_HOURS + 1 }, (_, i) => TIMELINE_START_H + i)
  const timeLabel = now.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', timeZone: CAMPUS_TZ })

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
            style={{ '--pos': `${((h - TIMELINE_START_H) / TIMELINE_HOURS) * 100}%` } as React.CSSProperties}
            aria-hidden="true"
          />
        ))}

        {/* Rain band */}
        {rainBand && (
          <div
            className="tl-rain-band"
            style={{
              '--top':    `${rainBand.startPct}%`,
              '--height': `${rainBand.heightPct}%`,
            } as React.CSSProperties}
            aria-label="Forecasted rain"
          />
        )}

        {/* Blocks */}
        {items.map(item => {
          const startMins = minutesIntoDay(item.start_at_utc)
          const endMins   = minutesIntoDay(item.end_at_utc)
          const topPct    = ((startMins - TIMELINE_START_H * 60) / (TIMELINE_HOURS * 60)) * 100
          const heightPct = (Math.max(endMins - startMins, 15) / (TIMELINE_HOURS * 60)) * 100
          const kindClass = item.kind === 'aurora' ? 'tl-block-aurora' : `tl-block-${item.kind}`
          return (
            <div
              key={item.id}
              role="listitem"
              className={`tl-block ${kindClass}`}
              style={{ '--top': `${topPct}%`, '--height': `${heightPct}%` } as React.CSSProperties}
              aria-label={`${item.title}, ${formatTime(item.start_at_utc)} to ${formatTime(item.end_at_utc)}, ${item.kind}`}
            >
              <span className="tl-block-title">{item.title}</span>
              <span className="tl-block-time">
                <Clock size={10} aria-hidden="true" /> {formatTime(item.start_at_utc)}
              </span>
            </div>
          )
        })}

        {/* Signal flags */}
        {signalFlags.map((sf, i) => (
          <div
            key={sf.signal.id ?? i}
            className={`tl-signal-flag tl-signal-flag-${sf.signal.feed.replace(/_/g, '-')}`}
            style={{ '--pos': `${sf.pct}%` } as React.CSSProperties}
            title={sf.signal.summary}
            onClick={() => setTooltipSignal(tt => tt?.id === sf.signal.id ? null : sf.signal)}
            role="button"
            aria-label={`Signal: ${sf.signal.summary}`}
          >
            <span className="tl-signal-dot" aria-hidden="true" />
          </div>
        ))}

        {/* Signal tooltip */}
        {tooltipSignal && (
          <div
            className="tl-signal-tooltip"
            style={{ '--pos': `${signalFlags.find(f => f.signal.id === tooltipSignal.id)?.pct ?? 0}%` } as React.CSSProperties}
            role="tooltip"
          >
            <button className="tl-tooltip-close" onClick={() => setTooltipSignal(null)} aria-label="Close">×</button>
            <p className="text-sm">{tooltipSignal.summary}</p>
            <span className="text-sm text-muted">{tooltipSignal.feed} · {formatTime(tooltipSignal.at_utc)}</span>
          </div>
        )}

        {/* Leave-by marker */}
        {leaveBy && (
          <div
            className="tl-leave-by"
            style={{ '--pos': `${leaveBy.pct}%` } as React.CSSProperties}
            aria-label={leaveBy.label}
          >
            <span className="tl-leave-by-line" aria-hidden="true" />
            <span className="tl-leave-by-label">{leaveBy.label}</span>
          </div>
        )}

        {/* Now marker */}
        <div
          ref={markerRef}
          className="tl-now-marker"
          style={{ '--pos': `${pct}%` } as React.CSSProperties}
          role="presentation"
        >
          <span className="sr-only">{`Current time: ${timeLabel}`}</span>
          <span className="tl-now-dot" aria-hidden="true" />
          <span className="tl-now-line" aria-hidden="true" />
          <span className="tl-now-label" aria-hidden="true">{timeLabel}</span>
        </div>
      </div>
    </div>
  )
}

// ── Main screen ───────────────────────────────────────────────────────────────
export default function TodayScreen() {
  const [events,       setEvents]       = useState<CalendarEvent[]>([])
  const [tasks,        setTasks]        = useState<Task[]>([])
  const [announcements, setAnnouncements] = useState<Announcement[]>([])
  const [moves,        setMoves]        = useState<Move[]>([])
  const [handledMoves, setHandledMoves] = useState<Move[]>([])
  const [signals,      setSignals]      = useState<Signal[]>([])
  const [feedStatuses, setFeedStatuses] = useState<FeedStatus[]>([])
  const [loading,      setLoading]      = useState(true)
  const [error,        setError]        = useState<string | null>(null)
  const [whyMove,      setWhyMove]      = useState<Move | null>(null)
  const [whyOpen,      setWhyOpen]      = useState(false)
  const [feedOpen,     setFeedOpen]     = useState(false)
  const [activeFeed,   setActiveFeed]   = useState<string | null>(null)
  const [autonomyOpen, setAutonomyOpen] = useState(false)
  const prevMoveIds    = useRef<Set<string>>(new Set())

  const navigate = useNavigate()
  const { showToast } = useToast()
  const { refresh: refreshBadges } = useBadges()
  const { now, simState } = useNow()

  const simMode = simState?.mode === 'scenario'

  const load = useCallback(() => {
    setLoading(true)
    Promise.all([
      getEvents(), getTasks(), getAnnouncements(),
      getMoves(), getHandledMoves(),
      getSignals(), getFeedsStatus(),
    ])
      .then(([ev, tk, an, mv, hm, sg, fs]) => {
        setEvents(ev); setTasks(tk); setAnnouncements(an)
        setMoves(mv); setHandledMoves(hm)
        setSignals(sg); setFeedStatuses(fs)
        setLoading(false)
      })
      .catch(e => { setError(String(e)); setLoading(false) })
  }, [])

  useEffect(() => { load() }, [load])

  async function handleMarkDone(task: Task) {
    const newStatus = task.status === 'done' ? 'todo' : 'done'
    setTasks(prev => prev.map(t => t.id === task.id ? { ...t, status: newStatus } : t))
    try {
      await updateTask(task.id, { status: newStatus })
      refreshBadges()
      if (newStatus === 'done') showToast(`"${task.title}" marked done`, 'success')
    } catch (e) {
      setTasks(prev => prev.map(t => t.id === task.id ? { ...t, status: task.status } : t))
      showToast(String(e), 'error')
    }
  }

  async function handleApprove(id: string) {
    try {
      await approveMoveReq(id)
      showToast('Move approved', 'success')
      load()
    } catch (e) { showToast(String(e), 'error') }
  }

  async function handleDismiss(id: string) {
    try {
      await dismissMoveApi(id)
      showToast('Dismissed', 'info')
      setMoves(prev => prev.filter(m => m.id !== id))
    } catch (e) { showToast(String(e), 'error') }
  }

  async function handleUndo(id: string) {
    try {
      await undoMoveAll(id)
      showToast('Action undone', 'success')
      load()
    } catch (e) { showToast(String(e), 'error') }
  }

  function handleWhyClick(move: Move) {
    setWhyMove(move)
    setWhyOpen(true)
  }

  function handleFeedClick(feed: string) {
    setActiveFeed(feed)
    setFeedOpen(true)
  }

  if (error) return (
    <ErrorState
      message="Couldn't load today's data. Check that the backend is running on port 8000, then try again."
      onRetry={load}
    />
  )

  const todayKey = dayKey(now)
  const nowMs = now.getTime()

  const todayEvents = events
    .filter(e => dayKey(e.start_at_utc) === todayKey)
    .sort((a, b) => new Date(a.start_at_utc).getTime() - new Date(b.start_at_utc).getTime())

  const openTasks   = tasks.filter(t => t.status !== 'done')
  const overdueTasks = openTasks.filter(t => t.due_at_utc && new Date(t.due_at_utc).getTime() < nowMs)
  const otherOpen   = openTasks.filter(t => !overdueTasks.includes(t))
  const dueSoon = [
    ...overdueTasks.sort((a, b) => new Date(a.due_at_utc!).getTime() - new Date(b.due_at_utc!).getTime()),
    ...otherOpen.sort((a, b) => {
      if (!a.due_at_utc && !b.due_at_utc) return 0
      if (!a.due_at_utc) return 1
      if (!b.due_at_utc) return -1
      return new Date(a.due_at_utc).getTime() - new Date(b.due_at_utc).getTime()
    }),
  ].slice(0, 5)

  const doneCnt      = tasks.filter(t => t.status === 'done').length
  const totalCnt     = tasks.length
  const progressPct  = totalCnt > 0 ? Math.round((doneCnt / totalCnt) * 100) : 0

  const dateStr = now.toLocaleDateString('en-US', {
    weekday: 'long', year: 'numeric', month: 'long', day: 'numeric', timeZone: CAMPUS_TZ,
  })

  // Build timeline items
  const timelineItems: TimelineItem[] = [
    ...todayEvents.map(ev => ({
      id:          ev.id,
      title:       ev.title,
      start_at_utc: ev.start_at_utc,
      end_at_utc:  ev.end_at_utc,
      kind:        (ev.source_type === 'aurora_block' ? 'aurora' : 'event') as TimelineItem['kind'],
      location:    ev.location_text,
    })),
    ...tasks
      .filter(t => t.status !== 'done' && t.due_at_utc && dayKey(t.due_at_utc) === todayKey)
      .map(t => ({
        id:          t.id,
        title:       t.title,
        start_at_utc: t.due_at_utc!,
        end_at_utc:  new Date(new Date(t.due_at_utc!).getTime() + t.estimated_minutes * 60_000).toISOString(),
        kind:        'task' as const,
      })),
  ].sort((a, b) => new Date(a.start_at_utc).getTime() - new Date(b.start_at_utc).getTime())

  // Signal flags: today's relevant signals
  const signalFlags: SignalFlag[] = signals
    .filter(s => dayKey(s.at_utc) === todayKey && s.relevance !== 'none')
    .map(s => {
      const mins = minutesIntoDay(s.at_utc)
      const pct  = ((mins - TIMELINE_START_H * 60) / (TIMELINE_HOURS * 60)) * 100
      return { signal: s, pct: Math.max(0, Math.min(100, pct)) }
    })

  // Rain band: look for a forecast_change signal with rain
  const rainSignal = signals.find(s =>
    s.kind === 'forecast_change' &&
    (s.payload?.condition === 'rain' || JSON.stringify(s.payload).toLowerCase().includes('rain'))
  )
  const rainBand: RainBand | null = rainSignal
    ? (() => {
        const startMins = minutesIntoDay(rainSignal.at_utc)
        const endMins   = Math.min(startMins + 180, TIMELINE_END_H * 60) // 3h window
        const startPct  = ((startMins - TIMELINE_START_H * 60) / (TIMELINE_HOURS * 60)) * 100
        const heightPct = ((endMins - startMins) / (TIMELINE_HOURS * 60)) * 100
        return { startPct, heightPct }
      })()
    : null

  // Leave-by marker: from auto_applied change_impact move
  const leaveByMove = handledMoves.find(m =>
    m.kind === 'change_impact' && m.status === 'auto_applied'
  )
  const leaveBy: LeaveByMarker | null = (() => {
    if (!leaveByMove) return null
    const whyTexts = leaveByMove.why.map(w => w.text).join(' ')
    const match = whyTexts.match(/leave.by.(\d{1,2}:\d{2}\s*[AP]M)/i)
    if (!match) return null
    // Parse the time string in today's context
    const parts = match[1].match(/(\d+):(\d+)\s*(AM|PM)/i)
    if (!parts) return null
    let h = parseInt(parts[1])
    const m2 = parseInt(parts[2])
    const ampm = parts[3].toUpperCase()
    if (ampm === 'PM' && h !== 12) h += 12
    if (ampm === 'AM' && h === 12) h = 0
    const mins = h * 60 + m2
    const pct  = ((mins - TIMELINE_START_H * 60) / (TIMELINE_HOURS * 60)) * 100
    return { pct: Math.max(0, Math.min(100, pct)), label: `Leave by ${match[1]}` }
  })()

  // Track new move IDs for entrance animation
  const currentMoveIds = new Set(moves.map(m => m.id))
  const newMoveIds = new Set([...currentMoveIds].filter(id => !prevMoveIds.current.has(id)))
  prevMoveIds.current = currentMoveIds

  // Proposed moves (top 3 by urgency)
  const urgencyOrder: Record<string, number> = { high: 0, medium: 1, low: 2 }
  const proposedMoves = [...moves]
    .filter(m => m.status === 'proposed')
    .sort((a, b) => (urgencyOrder[a.urgency] ?? 3) - (urgencyOrder[b.urgency] ?? 3))
    .slice(0, 3)

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
            className="btn btn-ghost btn-sm autonomy-btn"
            onClick={() => setAutonomyOpen(true)}
            aria-label="Autonomy settings"
            title="Autonomy settings"
          >
            <Settings size={14} aria-hidden="true" />
            <span className="autonomy-btn-label">Autonomy</span>
          </button>
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
      {!loading && <NowNextBand events={todayEvents} tasks={tasks} now={now} />}

      {/* Needs your decision */}
      {!loading && proposedMoves.length > 0 && (
        <section className="today-section" aria-labelledby="decisions-heading">
          <h2 id="decisions-heading">Needs your decision</h2>
          <div className="move-cards-list">
            {proposedMoves.map(m => (
              <MoveCard
                key={m.id}
                move={m}
                onApprove={handleApprove}
                onDismiss={handleDismiss}
                onWhyClick={handleWhyClick}
                isNew={newMoveIds.has(m.id)}
              />
            ))}
          </div>
        </section>
      )}

      {/* Handled for you */}
      {!loading && (
        <HandledSection
          handledMoves={handledMoves}
          feedStatuses={feedStatuses}
          onUndo={handleUndo}
          simMode={simMode}
        />
      )}

      {/* Today's timeline */}
      <section aria-labelledby="today-timeline-heading" className="today-section">
        <h2 id="today-timeline-heading">Today's Timeline</h2>
        {loading
          ? <SkeletonList count={2} lines={3} />
          : timelineItems.length === 0
            ? <EmptyState message="No events or tasks today." action={{ label: 'Import calendar →', onClick: () => navigate('/planner') }} />
            : <TodayTimeline
                items={timelineItems}
                signalFlags={signalFlags}
                rainBand={rainBand}
                leaveBy={leaveBy}
                now={now}
              />
        }
      </section>

      {/* Sources strip */}
      {!loading && (
        <SourcesStrip feedStatuses={feedStatuses} onFeedClick={handleFeedClick} />
      )}

      {/* Day summary counters */}
      {!loading && feedStatuses.length > 0 && (
        <DaySummaryCounters
          feedStatuses={feedStatuses}
          handledMoves={handledMoves}
          proposedMoves={proposedMoves}
          simMode={simMode}
        />
      )}

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
                      {!a.is_read && <><span className="ann-unread-dot" aria-hidden="true" /><span className="sr-only">Unread</span></>}
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

      {/* Today's summary */}
      {!loading && <TodaySummary events={todayEvents} tasks={tasks} now={now} />}

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
            <div className="progress-bar-fill" style={{ '--pct': `${progressPct}%` } as React.CSSProperties} />
          </div>
        </div>
      )}

      {/* Footer chip */}
      {!loading && (
        <div className="today-footer">
          <StatusChip variant="demo" label="Demo data" />
        </div>
      )}

      {/* Why drawer */}
      <WhyDrawer move={whyMove} open={whyOpen} onClose={() => setWhyOpen(false)} />

      {/* Feed signals sheet */}
      <FeedSignalsSheet
        feed={activeFeed}
        signals={signals}
        open={feedOpen}
        onClose={() => setFeedOpen(false)}
      />

      {/* Autonomy sheet */}
      <AutonomySheet open={autonomyOpen} onClose={() => setAutonomyOpen(false)} />
    </div>
  )
}
