import { useEffect, useState } from 'react'
import './PlannerScreen.css'
import { getEvents, getTasks, generatePlan, acceptPlan, rejectPlan, importICS, DailyPlan, CalendarEvent, Task } from '../../api/client'

function fmtTime(iso: string) {
  return new Date(iso).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', timeZone: 'America/New_York' })
}

export default function PlannerScreen() {
  const [events, setEvents] = useState<CalendarEvent[]>([])
  const [tasks, setTasks] = useState<Task[]>([])
  const [plan, setPlan] = useState<DailyPlan | null>(null)
  const [loading, setLoading] = useState(true)
  const [generating, setGenerating] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [planDate, setPlanDate] = useState(() => new Date().toLocaleDateString('fr-CA', { timeZone: 'America/New_York' }))
  const [icsMsg, setIcsMsg] = useState<string | null>(null)

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
    } catch (e) { setError(String(e)) }
    setGenerating(false)
  }

  async function handleAccept() {
    if (!plan) return
    const updated = await acceptPlan(plan.id).catch(e => { setError(String(e)); return null })
    if (updated) setPlan(updated)
  }

  async function handleReject() {
    if (!plan) return
    const updated = await rejectPlan(plan.id).catch(e => { setError(String(e)); return null })
    if (updated) setPlan(updated)
  }

  async function handleICSUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    try {
      const result = await importICS(file)
      setIcsMsg(`Imported ${result.imported} events. ${result.warnings.length > 0 ? result.warnings.join(' ') : ''}`)
      const ev = await getEvents()
      setEvents(ev)
    } catch (err) {
      setIcsMsg(`Import failed: ${String(err)}`)
    }
    e.target.value = ''
  }

  if (loading) return <div className="state-loading">Loading planner…</div>

  const dayEvents = events.filter(ev => ev.start_at_utc.startsWith(planDate))
    .sort((a, b) => new Date(a.start_at_utc).getTime() - new Date(b.start_at_utc).getTime())
  const openTasks = tasks.filter(t => t.status !== 'done')

  return (
    <div>
      <div className="screen-title">
        <h1>Planner</h1>
        <p>Import your calendar and generate a conflict-free daily plan.</p>
      </div>

      {/* ICS import */}
      <div className="card mb-2">
        <h3>Import Calendar (.ics)</h3>
        <p className="text-muted text-sm">Import a .ics file from your device. No live SBU SOLAR connection is used.</p>
        <label htmlFor="ics-input" className="btn btn-ghost btn-sm" style={{ display: 'inline-flex', cursor: 'pointer', width: 'auto' }}>
          📂 Choose .ics file
        </label>
        <input id="ics-input" type="file" accept=".ics" onChange={handleICSUpload} style={{ display: 'none' }} />
        {icsMsg && <p className={`text-sm mt-1 ${icsMsg.startsWith('Import failed') ? 'state-error' : ''}`}>{icsMsg}</p>}
      </div>

      {/* Plan generation */}
      <div className="card mb-2">
        <div className="flex items-center gap-2" style={{ flexWrap: 'wrap' }}>
          <label htmlFor="plan-date" style={{ margin: 0, whiteSpace: 'nowrap' }}>Plan for:</label>
          <input id="plan-date" type="date" value={planDate}
            onChange={e => setPlanDate(e.target.value)}
            style={{ width: '160px' }} />
          <button className="btn btn-primary btn-sm" onClick={handleGenerate} disabled={generating}>
            {generating ? 'Generating…' : '⚡ Generate My Day'}
          </button>
          {plan && plan.status === 'draft' && (
            <>
              <button className="btn btn-ghost btn-sm" style={{ color: 'var(--success)' }} onClick={handleAccept}>✓ Accept</button>
              <button className="btn btn-ghost btn-sm" style={{ color: 'var(--error)' }} onClick={handleReject}>✗ Reject</button>
            </>
          )}
          {plan && <span className={`badge badge-${plan.status === 'accepted' ? 'ok' : plan.status === 'rejected' ? 'err' : 'warn'}`}>{plan.status}</span>}
        </div>
        {error && <p className="state-error mt-1">{error}</p>}
      </div>

      {/* Plan blocks */}
      {plan && (
        <div>
          {plan.warnings.length > 0 && (
            <div className="card mb-2" style={{ borderColor: '#fcd34d', background: '#fffbeb' }}>
              <strong>⚠ Warnings</strong>
              <ul className="text-sm" style={{ marginTop: '.5rem' }}>
                {plan.warnings.map((w, i) => <li key={i}>{w}</li>)}
              </ul>
            </div>
          )}

          <h2>Scheduled Blocks</h2>
          {plan.blocks.length === 0
            ? <p className="text-muted">No blocks scheduled.</p>
            : <ul className="block-list">
                {[...plan.blocks].sort((a, b) =>
                  new Date(a.start_at_utc).getTime() - new Date(b.start_at_utc).getTime()
                ).map(block => (
                  <li key={block.id} className={`block-item card block-${block.block_type}`}>
                    <div className="flex justify-between items-center">
                      <strong>{block.title}</strong>
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
          }

          {plan.unscheduled.length > 0 && (
            <div className="mt-2">
              <h3>Unscheduled Tasks</h3>
              <ul className="block-list">
                {plan.unscheduled.map((u, i) => (
                  <li key={i} className="card" style={{ borderColor: '#fca5a5' }}>
                    <strong>{u.title}</strong>
                    <p className="text-muted text-sm" style={{ marginTop: '.25rem' }}>{u.reason}</p>
                  </li>
                ))}
              </ul>
            </div>
          )}
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
