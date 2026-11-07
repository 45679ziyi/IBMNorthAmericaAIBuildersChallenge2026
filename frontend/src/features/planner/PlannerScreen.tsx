import { useEffect, useState, useRef } from 'react'
import './PlannerScreen.css'
import { getEvents, getTasks, generatePlan, acceptPlan, rejectPlan, importICS, DailyPlan, CalendarEvent, Task } from '../../api/client'
import { SkeletonList } from '../../components/Skeleton'
import { useToast } from '../../components/Toast'
import { Clock, Upload, CalendarDays } from 'lucide-react'
import { formatTime, CAMPUS_TZ } from '../../lib/time'

// Day timeline: 7am–11pm = 16 hours
const TIMELINE_START_H = 7
const TIMELINE_END_H = 23
const TIMELINE_HOURS = TIMELINE_END_H - TIMELINE_START_H

function toMinutesFromMidnight(iso: string): number {
  const d = new Date(iso)
  const str = d.toLocaleString('en-US', {
    hour: 'numeric', minute: 'numeric', hour12: false,
    timeZone: CAMPUS_TZ,
  })
  const [h, m] = str.split(':').map(Number)
  return h * 60 + (m || 0)
}

function blockTopPct(startIso: string): number {
  const mins = toMinutesFromMidnight(startIso)
  return ((mins - TIMELINE_START_H * 60) / (TIMELINE_HOURS * 60)) * 100
}

function blockHeightPct(startIso: string, endIso: string): number {
  const startMins = toMinutesFromMidnight(startIso)
  const endMins = toMinutesFromMidnight(endIso)
  const dur = Math.max(endMins - startMins, 15)
  return (dur / (TIMELINE_HOURS * 60)) * 100
}

function nowTopPct(): number {
  const now = new Date()
  const h = now.getHours() + now.getMinutes() / 60
  return Math.max(0, Math.min(100, ((h - TIMELINE_START_H) / TIMELINE_HOURS) * 100))
}

// ── Timeline component ────────────────────────────────────────────────────────
function DayTimeline({ plan }: { plan: DailyPlan }) {
  const trackRef = useRef<HTMLDivElement>(null)
  const sorted = [...plan.blocks].sort(
    (a, b) => new Date(a.start_at_utc).getTime() - new Date(b.start_at_utc).getTime()
  )
  const hourLabels = Array.from({ length: TIMELINE_HOURS + 1 }, (_, i) => TIMELINE_START_H + i)
  const pct = nowTopPct()

  // Scroll to now-marker on mount (smooth)
  useEffect(() => {
    if (!trackRef.current) return
    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    const scrollTarget = trackRef.current.scrollHeight * (pct / 100) - 80
    trackRef.current.scrollTo({ top: Math.max(0, scrollTarget), behavior: reducedMotion ? 'instant' : 'smooth' })
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const BLOCK_LABELS: Record<string, string> = {
    fixed_event: 'Fixed event',
    task: 'Task',
    break: 'Break',
    suggestion: 'Suggested',
  }

  return (
    <div className="timeline-outer" aria-label="Day timeline">
      <div className="timeline-labels" aria-hidden="true">
        {hourLabels.map(h => (
          <div key={h} className="timeline-hour-label">
            {h === 12 ? '12 PM' : h < 12 ? `${h} AM` : `${h - 12} PM`}
          </div>
        ))}
      </div>

      <div ref={trackRef} className="timeline-track" role="list">
        {/* Hour grid lines */}
        {hourLabels.map(h => (
          <div
            key={h}
            className="timeline-gridline"
            /* computed position — geometry var */
            style={{ '--pos': `${((h - TIMELINE_START_H) / TIMELINE_HOURS) * 100}%` } as React.CSSProperties}
            aria-hidden="true"
          />
        ))}

        {/* Blocks */}
        {sorted.map(block => (
          <div
            key={block.id}
            role="listitem"
            className={`timeline-block timeline-block-${block.block_type}`}
            /* computed geometry — CSS vars */
            style={{
              '--top':    `${blockTopPct(block.start_at_utc)}%`,
              '--height': `${blockHeightPct(block.start_at_utc, block.end_at_utc)}%`,
            } as React.CSSProperties}
            title={`${block.title} · ${formatTime(block.start_at_utc)}–${formatTime(block.end_at_utc)}`}
            aria-label={`${block.title}, ${formatTime(block.start_at_utc)} to ${formatTime(block.end_at_utc)}, ${block.block_type.replace('_', ' ')}`}
          >
            <span className="timeline-block-title">{block.title}</span>
            <span className="timeline-block-type">{BLOCK_LABELS[block.block_type] ?? block.block_type}</span>
            <span className="timeline-block-time">
              <Clock size={10} aria-hidden="true" /> {formatTime(block.start_at_utc)}
            </span>
          </div>
        ))}

        {/* Now marker */}
        <div
          className="timeline-now"
          /* computed position — geometry var */
          style={{ '--pos': `${pct}%` } as React.CSSProperties}
          aria-hidden="true"
        />
      </div>
    </div>
  )
}

// ── Main screen ───────────────────────────────────────────────────────────────
export default function PlannerScreen() {
  const [events, setEvents] = useState<CalendarEvent[]>([])
  const [tasks, setTasks] = useState<Task[]>([])
  const [plan, setPlan] = useState<DailyPlan | null>(null)
  const [loading, setLoading] = useState(true)
  const [generating, setGenerating] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [planDate, setPlanDate] = useState(() =>
    new Date().toLocaleDateString('fr-CA', { timeZone: CAMPUS_TZ })
  )
  const [icsResult, setIcsResult] = useState<string | null>(null)
  const [mobileView, setMobileView] = useState<'timeline' | 'list'>('timeline')
  const { showToast } = useToast()

  useEffect(() => {
    Promise.all([getEvents(), getTasks()])
      .then(([ev, tk]) => { setEvents(ev); setTasks(tk); setLoading(false) })
      .catch(e => { setError(String(e)); setLoading(false) })
  }, [])

  async function handleGenerate() {
    setGenerating(true); setError(null)
    try {
      const p = await generatePlan(planDate)
      setPlan(p)
      showToast('Plan generated', 'success')
    } catch (e) { setError(String(e)); showToast(String(e), 'error') }
    setGenerating(false)
  }

  async function handleAccept() {
    if (!plan) return
    try {
      const updated = await acceptPlan(plan.id)
      setPlan(updated)
      showToast('Plan accepted', 'success')
    } catch (e) { setError(String(e)) }
  }

  async function handleReject() {
    if (!plan) return
    try {
      const updated = await rejectPlan(plan.id)
      setPlan(updated)
      showToast('Plan rejected', 'info')
    } catch (e) { setError(String(e)) }
  }

  async function handleICSUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    try {
      const result = await importICS(file)
      const msg = `Imported ${result.imported} event${result.imported !== 1 ? 's' : ''}.`
      setIcsResult(msg)
      showToast(msg, 'success')
      const ev = await getEvents()
      setEvents(ev)
    } catch (err) {
      const msg = `Import failed: ${String(err)}`
      setIcsResult(msg)
      showToast(msg, 'error')
    }
    e.target.value = ''
  }

  if (loading) return <SkeletonList count={4} lines={3} />

  const dayEvents = events
    .filter(ev => ev.start_at_utc.startsWith(planDate))
    .sort((a, b) => new Date(a.start_at_utc).getTime() - new Date(b.start_at_utc).getTime())

  const BLOCK_LABELS: Record<string, string> = {
    fixed_event: 'Fixed event',
    task: 'Task',
    break: 'Break',
    suggestion: 'Suggested',
  }

  return (
    <div className="planner-screen">
      <div className="screen-title">
        <h1>Planner</h1>
        <p>Import your calendar and generate a conflict-free daily plan.</p>
      </div>

      {/* ICS import */}
      <div className="card mb-2 ics-row">
        <div className="ics-left">
          <label htmlFor="ics-input" className="btn btn-ghost btn-sm ics-label">
            <Upload size={14} aria-hidden="true" /> Choose .ics file
          </label>
          <input id="ics-input" type="file" accept=".ics" onChange={handleICSUpload} className="sr-only" />
          {icsResult && <span className="text-sm text-muted">{icsResult}</span>}
        </div>
        <p className="text-muted text-sm ics-note">
          Import .ics from your device. No live SBU SOLAR connection.
        </p>
      </div>

      {/* Controls */}
      <div className="card mb-2">
        <div className="planner-controls">
          <label htmlFor="plan-date" className="planner-date-label">Plan for:</label>
          <input
            id="plan-date" type="date" value={planDate}
            onChange={e => setPlanDate(e.target.value)}
            className="planner-date-input"
          />
          <div className="planner-ctrl-actions">
            <button className="btn btn-primary btn-sm" onClick={handleGenerate} disabled={generating}>
              <CalendarDays size={14} aria-hidden="true" /> {generating ? 'Generating…' : 'Generate plan'}
            </button>
            {plan && (
              <span className={`badge badge-${plan.status === 'accepted' ? 'ok' : plan.status === 'rejected' ? 'err' : 'warn'}`}>
                {plan.status}
              </span>
            )}
          </div>
        </div>
        {error && <p className="state-error mt-1" role="alert">{error}</p>}
      </div>

      {/* Plan view */}
      {plan && plan.blocks.length > 0 && (
        <>
          {/* Mobile segment control */}
          <div className="planner-segment" role="group" aria-label="Plan view">
            <button
              className={`segment-btn${mobileView === 'timeline' ? ' segment-btn-active' : ''}`}
              onClick={() => setMobileView('timeline')}
              aria-pressed={mobileView === 'timeline'}
            >
              Timeline
            </button>
            <button
              className={`segment-btn${mobileView === 'list' ? ' segment-btn-active' : ''}`}
              onClick={() => setMobileView('list')}
              aria-pressed={mobileView === 'list'}
            >
              List
            </button>
          </div>

          <div className="planner-layout">
            {/* Timeline */}
            <div className={`planner-timeline-col${mobileView === 'list' ? ' planner-col-hidden' : ''}`}>
              <h2>Timeline</h2>
              <DayTimeline plan={plan} />
            </div>

            {/* Block list + unscheduled */}
            <div className={`planner-list-col${mobileView === 'timeline' ? ' planner-col-hidden' : ''}`}>
              {plan.warnings.length > 0 && (
                <div className="card mb-2 planner-warnings">
                  <strong>Warnings</strong>
                  <ul className="text-sm">
                    {plan.warnings.map((w, i) => <li key={i}>{w}</li>)}
                  </ul>
                </div>
              )}

              <h2>Blocks</h2>
              <ul className="block-list">
                {[...plan.blocks].sort((a, b) =>
                  new Date(a.start_at_utc).getTime() - new Date(b.start_at_utc).getTime()
                ).map(block => (
                  <li key={block.id} className={`card block-item block-${block.block_type}`}>
                    <div className="flex justify-between items-center">
                      <strong className="text-sm">{block.title}</strong>
                      <span className="badge badge-synth text-sm">{BLOCK_LABELS[block.block_type] ?? block.block_type}</span>
                    </div>
                    <div className="text-muted text-sm">
                      {formatTime(block.start_at_utc)} – {formatTime(block.end_at_utc)}
                    </div>
                    <details className="text-sm mt-1">
                      <summary className="planner-why-summary">Why?</summary>
                      <p className="text-muted">{block.reason}</p>
                    </details>
                  </li>
                ))}
              </ul>

              {plan.unscheduled.length > 0 && (
                <div className="mt-2">
                  <h3>Unscheduled</h3>
                  <ul className="block-list">
                    {plan.unscheduled.map((u, i) => (
                      <li key={i} className="card planner-unscheduled">
                        <strong className="text-sm">{u.title}</strong>
                        <p className="text-muted text-sm">{u.reason}</p>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          </div>

          {/* Sticky action bar */}
          {plan.status === 'draft' && (
            <div className="planner-action-bar">
              <button className="btn btn-primary btn-sm" onClick={handleAccept}>Accept plan</button>
              <button className="btn btn-ghost btn-sm" onClick={handleReject}>Reject</button>
            </div>
          )}
        </>
      )}

      {/* Fixed events for selected day */}
      <div className="mt-2">
        <h2>Fixed Events for {planDate}</h2>
        {dayEvents.length === 0
          ? <p className="text-muted">No fixed events. Import a calendar to see your schedule.</p>
          : <ul className="block-list">
              {dayEvents.map(ev => (
                <li key={ev.id} className="card block-item block-fixed_event">
                  <div className="flex justify-between">
                    <strong>{ev.title}</strong>
                    <span className="text-muted text-sm">{formatTime(ev.start_at_utc)} – {formatTime(ev.end_at_utc)}</span>
                  </div>
                  {ev.location_text && <p className="text-muted text-sm">{ev.location_text}</p>}
                </li>
              ))}
            </ul>
        }
      </div>
    </div>
  )
}
