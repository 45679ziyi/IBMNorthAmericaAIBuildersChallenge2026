import { useEffect, useState } from 'react'
import './PlannerScreen.css'
import { getEvents, getTasks, generatePlan, acceptPlan, rejectPlan, importICS, DailyPlan, CalendarEvent, Task } from '../../api/client'
import { SkeletonList } from '../../components/Skeleton'
import { useToast } from '../../components/Toast'
import { Clock, Upload, Zap } from 'lucide-react'

// Day timeline: 7am–11pm = 16 hours
const TIMELINE_START_H = 7
const TIMELINE_END_H = 23
const TIMELINE_HOURS = TIMELINE_END_H - TIMELINE_START_H

function fmtTime(iso: string) {
  return new Date(iso).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', timeZone: 'America/New_York' })
}

function toMinutesFromMidnight(iso: string): number {
  const d = new Date(iso)
  // Convert to NY time components
  const str = d.toLocaleString('en-US', {
    hour: 'numeric', minute: 'numeric', hour12: false,
    timeZone: 'America/New_York',
  })
  const [h, m] = str.split(':').map(Number)
  return h * 60 + (m || 0)
}

function blockTopPct(startIso: string): string {
  const mins = toMinutesFromMidnight(startIso)
  const fromStart = mins - TIMELINE_START_H * 60
  return `${(fromStart / (TIMELINE_HOURS * 60)) * 100}%`
}

function blockHeightPct(startIso: string, endIso: string): string {
  const startMins = toMinutesFromMidnight(startIso)
  const endMins = toMinutesFromMidnight(endIso)
  const dur = Math.max(endMins - startMins, 15) // min 15min visible
  return `${(dur / (TIMELINE_HOURS * 60)) * 100}%`
}

// ── Timeline component ──────────────────────────────────────────────────────
function DayTimeline({ plan }: { plan: DailyPlan }) {
  const sorted = [...plan.blocks].sort(
    (a, b) => new Date(a.start_at_utc).getTime() - new Date(b.start_at_utc).getTime()
  )
  const hourLabels = Array.from({ length: TIMELINE_HOURS + 1 }, (_, i) => TIMELINE_START_H + i)

  return (
    <div className="timeline-outer" aria-label="Day timeline">
      {/* Hour grid */}
      <div className="timeline-labels" aria-hidden="true">
        {hourLabels.map(h => (
          <div key={h} className="timeline-hour-label">
            {h === 12 ? '12 PM' : h < 12 ? `${h} AM` : `${h - 12} PM`}
          </div>
        ))}
      </div>

      {/* Track */}
      <div className="timeline-track" role="list">
        {/* Hour grid lines */}
        {hourLabels.map(h => (
          <div
            key={h}
            className="timeline-gridline"
            style={{ top: `${((h - TIMELINE_START_H) / TIMELINE_HOURS) * 100}%` }}
            aria-hidden="true"
          />
        ))}

        {/* Blocks */}
        {sorted.map(block => (
          <div
            key={block.id}
            role="listitem"
            className={`timeline-block timeline-block-${block.block_type}`}
            style={{
              top: blockTopPct(block.start_at_utc),
              height: blockHeightPct(block.start_at_utc, block.end_at_utc),
            }}
            title={`${block.title} · ${fmtTime(block.start_at_utc)}–${fmtTime(block.end_at_utc)}`}
            aria-label={`${block.title}, ${fmtTime(block.start_at_utc)} to ${fmtTime(block.end_at_utc)}, ${block.block_type.replace('_', ' ')}`}
          >
            <span className="timeline-block-title">{block.title}</span>
            <span className="timeline-block-time">
              <Clock size={10} aria-hidden="true" /> {fmtTime(block.start_at_utc)}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Main screen ─────────────────────────────────────────────────────────────
export default function PlannerScreen() {
  const [events, setEvents] = useState<CalendarEvent[]>([])
  const [tasks, setTasks] = useState<Task[]>([])
  const [plan, setPlan] = useState<DailyPlan | null>(null)
  const [loading, setLoading] = useState(true)
  const [generating, setGenerating] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [planDate, setPlanDate] = useState(() =>
    new Date().toLocaleDateString('fr-CA', { timeZone: 'America/New_York' })
  )
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
      showToast('Plan generated!', 'success')
    } catch (e) { setError(String(e)); showToast(String(e), 'error') }
    setGenerating(false)
  }

  async function handleAccept() {
    if (!plan) return
    try {
      const updated = await acceptPlan(plan.id)
      setPlan(updated)
      showToast('Plan accepted ✓', 'success')
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
      showToast(`Imported ${result.imported} events.`, 'success')
      const ev = await getEvents()
      setEvents(ev)
    } catch (err) {
      showToast(`Import failed: ${String(err)}`, 'error')
    }
    e.target.value = ''
  }

  if (loading) return <SkeletonList count={4} lines={3} />

  const dayEvents = events
    .filter(ev => ev.start_at_utc.startsWith(planDate))
    .sort((a, b) => new Date(a.start_at_utc).getTime() - new Date(b.start_at_utc).getTime())

  return (
    <div>
      <div className="screen-title">
        <h1>Planner</h1>
        <p>Import your calendar and generate a conflict-free daily plan.</p>
      </div>

      {/* ICS import */}
      <div className="card mb-2">
        <h3>Import Calendar (.ics)</h3>
        <p className="text-muted text-sm">
          Import a .ics file from your device. No live SBU SOLAR connection is used.
        </p>
        <label htmlFor="ics-input" className="btn btn-ghost btn-sm" style={{ display: 'inline-flex', cursor: 'pointer', width: 'auto', gap: '.4rem' }}>
          <Upload size={14} aria-hidden="true" /> Choose .ics file
        </label>
        <input id="ics-input" type="file" accept=".ics" onChange={handleICSUpload} style={{ display: 'none' }} />
      </div>

      {/* Plan generation controls */}
      <div className="card mb-2">
        <div className="flex items-center gap-2" style={{ flexWrap: 'wrap' }}>
          <label htmlFor="plan-date" style={{ margin: 0, whiteSpace: 'nowrap' }}>Plan for:</label>
          <input
            id="plan-date" type="date" value={planDate}
            onChange={e => setPlanDate(e.target.value)}
            style={{ width: '160px' }}
          />
          <button className="btn btn-primary btn-sm" onClick={handleGenerate} disabled={generating}>
            <Zap size={14} aria-hidden="true" /> {generating ? 'Generating…' : 'Generate My Day'}
          </button>
          {plan && plan.status === 'draft' && (
            <>
              <button className="btn btn-ghost btn-sm" style={{ color: 'var(--success)' }} onClick={handleAccept}>✓ Accept</button>
              <button className="btn btn-ghost btn-sm" style={{ color: 'var(--error)' }} onClick={handleReject}>✗ Reject</button>
            </>
          )}
          {plan && (
            <span className={`badge badge-${plan.status === 'accepted' ? 'ok' : plan.status === 'rejected' ? 'err' : 'warn'}`}>
              {plan.status}
            </span>
          )}
        </div>
        {error && <p className="state-error mt-1">{error}</p>}
      </div>

      {/* Visual timeline + sidebar */}
      {plan && plan.blocks.length > 0 && (
        <div className="planner-layout">
          <div>
            <h2>Visual Timeline</h2>
            <DayTimeline plan={plan} />
          </div>

          <div>
            {plan.warnings.length > 0 && (
              <div className="card mb-2" style={{ borderColor: 'var(--warning)', background: 'var(--surface-alt)' }}>
                <strong>⚠ Warnings</strong>
                <ul className="text-sm" style={{ marginTop: '.5rem', paddingLeft: '1.2rem' }}>
                  {plan.warnings.map((w, i) => <li key={i}>{w}</li>)}
                </ul>
              </div>
            )}

            <h2>Blocks</h2>
            <ul className="block-list">
              {[...plan.blocks].sort((a, b) =>
                new Date(a.start_at_utc).getTime() - new Date(b.start_at_utc).getTime()
              ).map(block => (
                <li key={block.id} className={`block-item card block-${block.block_type}`}>
                  <div className="flex justify-between items-center">
                    <strong className="text-sm">{block.title}</strong>
                    <span className={`badge badge-${block.block_type === 'fixed_event' ? 'err' : block.block_type === 'break' ? 'ok' : 'warn'}`}>
                      {block.block_type.replace('_', ' ')}
                    </span>
                  </div>
                  <div className="text-muted text-sm">
                    {fmtTime(block.start_at_utc)} – {fmtTime(block.end_at_utc)}
                  </div>
                  <details className="text-sm mt-1">
                    <summary style={{ cursor: 'pointer', color: 'var(--accent)' }}>Why?</summary>
                    <p style={{ marginTop: '.3rem', color: 'var(--text-muted)' }}>{block.reason}</p>
                  </details>
                </li>
              ))}
            </ul>

            {plan.unscheduled.length > 0 && (
              <div className="mt-2">
                <h3>Unscheduled</h3>
                <ul className="block-list">
                  {plan.unscheduled.map((u, i) => (
                    <li key={i} className="card" style={{ borderColor: 'var(--error)' }}>
                      <strong className="text-sm">{u.title}</strong>
                      <p className="text-muted text-sm" style={{ marginTop: '.25rem' }}>{u.reason}</p>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </div>
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
                    <span className="text-muted text-sm">{fmtTime(ev.start_at_utc)} – {fmtTime(ev.end_at_utc)}</span>
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
