import { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import {
  getCanonicalEvent, getCanonicalEventReach, getCanonicalEventThread,
  postThreadMessage, getWorkItems,
  createScenario, listScenarios, promoteScenario,
  type CanonicalEvent, type ReachResponse, type Thread, type WorkItem,
  type ScenarioRun, type CandidateOption,
} from '../../api/client'
import { useIdentity } from '../../hooks/useIdentity'
import { LoadingState } from '../../components/states/LoadingState'
import { ErrorState } from '../../components/states/ErrorState'
import '../../components/states/states.css'
import './EventSpinePage.css'

const MIN_CELL = 5

function severityColor(s: string) {
  if (s === 'critical') return 'badge-red'
  if (s === 'high') return 'badge-orange'
  if (s === 'medium') return 'badge-yellow'
  return 'badge-blue'
}

function suppressCount(n: number) {
  return n < MIN_CELL ? `fewer than ${MIN_CELL}` : String(n)
}

// ── Section: Header ──────────────────────────────────────────────────────────

function EventHeader({ event }: { event: CanonicalEvent }) {
  const shortId = event.id.slice(0, 12)
  const typeLabel = event.type.replace(/\./g, ' › ')
  return (
    <div className="es-header">
      <div className="es-header-row">
        <span className={`badge ${severityColor(event.severity)}`}>{event.severity}</span>
        <span className="badge badge-outline">{typeLabel}</span>
        <span className={`badge ${event.status === 'open' ? 'badge-red' : 'badge-green'}`}>{event.status}</span>
        {event.classification !== 'institutional' && (
          <span className="badge badge-purple">{event.classification}</span>
        )}
        <span className="badge badge-sim">SIMULATION</span>
      </div>
      <h1 className="es-title">{typeLabel}</h1>
      <div className="es-meta-row">
        <code className="es-id">{shortId}</code>
        <span className="es-tenant">{event.tenant_id}</span>
        {event.corroborations > 0 && (
          <span className="badge badge-outline">{event.corroborations} corroboration{event.corroborations !== 1 ? 's' : ''}</span>
        )}
      </div>
    </div>
  )
}

// ── Section: Facts timeline ───────────────────────────────────────────────────

function FactsTimeline({ event }: { event: CanonicalEvent }) {
  return (
    <section className="es-section">
      <h2>Facts</h2>
      <ol className="es-timeline">
        <li className="es-tl-item">
          <span className="es-tl-time">{new Date(event.received_at).toLocaleTimeString()}</span>
          <span className="es-tl-actor">{event.source_feed ?? 'system'}</span>
          <span className="es-tl-badge es-tl-badge-auto">ingested</span>
          <span className="es-tl-body">
            Signal from <strong>{event.source_feed ?? 'system'}</strong> — record <code>{event.source_record_id ?? '—'}</code>
          </span>
        </li>
        {event.occurred_at && (
          <li className="es-tl-item">
            <span className="es-tl-time">{new Date(event.occurred_at).toLocaleTimeString()}</span>
            <span className="es-tl-actor">{event.last_actor ?? 'system'}</span>
            <span className={`es-tl-badge ${event.last_actor_mode === 'autopilot' ? 'es-tl-badge-auto' : 'es-tl-badge-human'}`}>
              {event.last_actor_mode}
            </span>
            <span className="es-tl-body">Occurred at {new Date(event.occurred_at).toLocaleString()}</span>
          </li>
        )}
      </ol>
    </section>
  )
}

// ── Section: Impact ───────────────────────────────────────────────────────────

function ImpactSection({ event }: { event: CanonicalEvent }) {
  const buildings = event.entity_refs.filter(r => r.type === 'building').map(r => r.id)
  const sections  = event.entity_refs.filter(r => r.type === 'section').map(r => r.id)
  const services  = event.entity_refs.filter(r => r.type === 'service').map(r => r.id)

  return (
    <section className="es-section">
      <h2>Impact</h2>
      <dl className="es-dl">
        {buildings.length > 0 && (
          <>
            <dt>Buildings</dt>
            <dd>{buildings.join(', ')}</dd>
          </>
        )}
        {sections.length > 0 && (
          <>
            <dt>Sections</dt>
            <dd>{suppressCount(sections.length)} section{sections.length !== 1 ? 's' : ''}</dd>
          </>
        )}
        {services.length > 0 && (
          <>
            <dt>Services</dt>
            <dd>{services.join(', ')}</dd>
          </>
        )}
        {buildings.length === 0 && sections.length === 0 && services.length === 0 && (
          <dd className="es-empty">No entity refs recorded</dd>
        )}
      </dl>
    </section>
  )
}

// ── Section: Work items ───────────────────────────────────────────────────────

function WorkItemsSection({ items }: { items: WorkItem[] }) {
  if (items.length === 0) return null
  return (
    <section className="es-section">
      <h2>Work Items</h2>
      <ul className="es-wi-list">
        {items.map(wi => (
          <li key={wi.id} className="es-wi-item">
            <span className="es-wi-type">{wi.workflow_type}</span>
            <span className={`badge ${wi.status === 'resolved' ? 'badge-green' : 'badge-yellow'}`}>{wi.status}</span>
            {wi.owner_person_id && <span className="es-wi-owner">→ {wi.owner_person_id}</span>}
            {wi.required_next_fields.length > 0 && (
              <span className="es-wi-next">needs: {wi.required_next_fields.join(', ')}</span>
            )}
          </li>
        ))}
      </ul>
    </section>
  )
}

// ── Section: Reach map ────────────────────────────────────────────────────────

function ReachMapSection({ reach }: { reach: ReachResponse | null }) {
  if (!reach) return null
  const entries = Object.entries(reach.audience_counts)
  if (entries.length === 0) return null
  const total = entries.reduce((s, [, n]) => s + n, 0)
  return (
    <section className="es-section">
      <h2>Reach</h2>
      <ul className="es-reach-list">
        {entries.map(([role, count]) => (
          <li key={role} className="es-reach-item">
            <span className="es-reach-role">{role}</span>
            <span className="es-reach-count">{suppressCount(count)}</span>
            <div className="es-reach-bar">
              <div
                className="es-reach-fill"
                style={{ width: total > 0 ? `${Math.round((count / total) * 100)}%` : '0%' }}
              />
            </div>
          </li>
        ))}
      </ul>
    </section>
  )
}

// ── Section: Thread ───────────────────────────────────────────────────────────

function ThreadSection({ eventId, thread, onRefresh }: {
  eventId: string
  thread: Thread | null
  onRefresh: () => void
}) {
  const [body, setBody] = useState('')
  const [posting, setPosting] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  async function submit() {
    if (!body.trim()) return
    setPosting(true); setErr(null)
    try {
      await postThreadMessage(eventId, body.trim())
      setBody('')
      onRefresh()
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : 'Failed to post message')
    } finally {
      setPosting(false)
    }
  }

  return (
    <section className="es-section">
      <h2>Discussion</h2>
      {thread && thread.messages.length > 0 ? (
        <ul className="es-thread-list">
          {thread.messages.map(m => (
            <li key={m.id} className="es-thread-msg">
              <span className="es-thread-author">{m.author_person_id}</span>
              <span className="es-thread-time">{new Date(m.created_at).toLocaleTimeString()}</span>
              <p className="es-thread-body">{m.body}</p>
            </li>
          ))}
        </ul>
      ) : (
        <p className="es-empty">No messages yet.</p>
      )}
      <div className="es-thread-form">
        <textarea
          className="form-control"
          rows={2}
          maxLength={2000}
          placeholder="Add a message… (max 2000 chars)"
          value={body}
          onChange={e => setBody(e.target.value)}
        />
        {err && <p className="form-error">{err}</p>}
        <button className="btn btn-primary" disabled={!body.trim() || posting} onClick={submit}>
          {posting ? 'Posting…' : 'Post'}
        </button>
      </div>
    </section>
  )
}

// ── Section: Audit ────────────────────────────────────────────────────────────

function AuditSection({ event, role }: { event: CanonicalEvent; role: string }) {
  const auditable = ['facilities', 'it', 'academic_ops']
  if (!auditable.includes(role)) return null
  return (
    <section className="es-section">
      <h2>Audit</h2>
      <dl className="es-dl">
        <dt>Idempotency key</dt><dd><code>{event.idempotency_key}</code></dd>
        <dt>Schema version</dt><dd>{event.schema_version}</dd>
        <dt>Last actor</dt><dd>{event.last_actor ?? '—'} ({event.last_actor_mode})</dd>
        <dt>Received at</dt><dd>{new Date(event.received_at).toISOString()}</dd>
        <dt>Data origin</dt><dd>synthetic</dd>
      </dl>
    </section>
  )
}

// ── Section: Scenario Panel (V4-05/06) ───────────────────────────────────────

function ScenarioPanel({ event, role }: { event: CanonicalEvent; role: string }) {
  const canCreate = ['facilities', 'it', 'academic_ops', 'faculty'].includes(role)
  const canApprove = role === 'academic_ops'

  const [runs, setRuns] = useState<ScenarioRun[]>([])
  const [loading, setLoading] = useState(false)
  const [creating, setCreating] = useState(false)
  const [form, setForm] = useState({ affected_room_id: '', repair_delay_minutes: 60 })
  const [promoting, setPromoting] = useState<string | null>(null)  // option_id being promoted
  const [promoteRationale, setPromoteRationale] = useState('')
  const [activeRun, setActiveRun] = useState<ScenarioRun | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function loadRuns() {
    try {
      const list = await listScenarios(event.id)
      setRuns(list)
      if (list.length > 0 && !activeRun) setActiveRun(list[0])
    } catch { /* optional panel */ }
  }

  useEffect(() => { loadRuns() }, [event.id])

  async function handleCreate() {
    if (!form.affected_room_id.trim()) return
    setCreating(true); setError(null)
    try {
      const run = await createScenario({
        canonical_event_id: event.id,
        affected_room_id: form.affected_room_id.trim(),
        repair_delay_minutes: form.repair_delay_minutes,
      })
      setRuns(prev => [run, ...prev])
      setActiveRun(run)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to run scenario')
    } finally {
      setCreating(false)
    }
  }

  async function handlePromote(run: ScenarioRun, optionId: string) {
    if (!promoteRationale.trim() || promoteRationale.length < 10) {
      setError('Rationale must be at least 10 characters.')
      return
    }
    setLoading(true); setError(null)
    try {
      await promoteScenario(run.id, optionId, promoteRationale)
      await loadRuns()
      setPromoting(null)
      setPromoteRationale('')
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Promotion failed')
    } finally {
      setLoading(false)
    }
  }

  if (!canCreate) return null

  const result = activeRun?.result
  const bestCandidate: CandidateOption | undefined = result?.candidates?.[0]

  return (
    <section className="es-section" aria-labelledby="scenario-heading">
      <h2 id="scenario-heading">What-if Scenario</h2>
      <p className="es-muted">
        Run a deterministic alternate-room analysis. Results are simulated and do not change any live data.
        <span className="badge badge-sim" style={{ marginLeft: 8 }}>SYNTHETIC SIMULATION</span>
      </p>

      {/* Create form */}
      <div className="es-scenario-form" role="form" aria-label="Create scenario">
        <label className="es-label" htmlFor="affected-room">
          Affected room ID
        </label>
        <input
          id="affected-room"
          className="es-input"
          type="text"
          value={form.affected_room_id}
          onChange={e => setForm(f => ({ ...f, affected_room_id: e.target.value }))}
          placeholder="e.g. LE-101"
          aria-required="true"
        />
        <label className="es-label" htmlFor="repair-delay">
          Repair delay (minutes)
        </label>
        <input
          id="repair-delay"
          className="es-input"
          type="number"
          min={0}
          max={10080}
          value={form.repair_delay_minutes}
          onChange={e => setForm(f => ({ ...f, repair_delay_minutes: parseInt(e.target.value) || 0 }))}
        />
        <button
          className="btn btn-primary btn-sm"
          onClick={handleCreate}
          disabled={creating || !form.affected_room_id.trim()}
          aria-busy={creating}
        >
          {creating ? 'Running…' : 'Run scenario'}
        </button>
      </div>

      {error && <p className="es-error" role="alert">{error}</p>}

      {/* Active run results */}
      {activeRun && result && (
        <div className="es-scenario-result">
          <div className="es-scenario-meta">
            <span className="badge badge-outline">engine: {activeRun.engine_version}</span>
            <span className={`badge ${activeRun.status === 'promoted' ? 'badge-green' : 'badge-blue'}`}>
              {activeRun.status}
            </span>
            <span className="es-muted" style={{ fontSize: '0.75rem' }}>
              hash: <code>{activeRun.result_hash?.slice(0, 12)}</code>
            </span>
          </div>

          {/* Summary */}
          <dl className="es-dl es-scenario-summary">
            <dt>Affected sections</dt>
            <dd>{result.summary.affected_sections_count}</dd>
            <dt>Affected students</dt>
            <dd>{result.summary.affected_students_display}</dd>
            <dt>Feasible alternatives</dt>
            <dd>{result.summary.feasible_alternatives}</dd>
            <dt>Data completeness</dt>
            <dd>{result.summary.data_completeness}</dd>
          </dl>

          {/* Missing data / assumptions */}
          {result.missing_data.length > 0 && (
            <details className="es-scenario-disclosure">
              <summary>Missing data ({result.missing_data.length})</summary>
              <ul>
                {result.missing_data.map((m, i) => <li key={i}>{m}</li>)}
              </ul>
            </details>
          )}
          {result.assumptions.length > 0 && (
            <details className="es-scenario-disclosure">
              <summary>Assumptions ({result.assumptions.length})</summary>
              <ul>
                {result.assumptions.map((a, i) => <li key={i}>{a}</li>)}
              </ul>
            </details>
          )}

          {/* Candidates */}
          {result.candidates.length > 0 ? (
            <div className="es-scenario-candidates">
              <h3>Feasible alternatives</h3>
              {result.candidates.slice(0, 3).map(c => (
                <div key={c.room_id} className={`es-candidate ${c.rank === 1 ? 'es-candidate-best' : ''}`}>
                  <div className="es-candidate-header">
                    <strong>#{c.rank} {c.room_name}</strong>
                    <span className="badge badge-outline">score {c.score.toFixed(2)}</span>
                    <span className="es-muted">cap {c.capacity}</span>
                    {c.features.length > 0 && (
                      <span className="es-muted">{c.features.join(', ')}</span>
                    )}
                  </div>
                  <dl className="es-dl es-candidate-factors">
                    <dt title="How well the capacity fits enrolled headcount">Capacity fit</dt>
                    <dd>{(c.score_factors.capacity_fit * 100).toFixed(0)}% <em className="es-muted">({c.score_factors.capacity_fit_basis})</em></dd>
                    <dt title="Building proximity score">Proximity</dt>
                    <dd>{(c.score_factors.building_proximity * 100).toFixed(0)}% <em className="es-muted">({c.score_factors.proximity_basis})</em></dd>
                    {c.score_factors.feature_match < 1 && (
                      <>
                        <dt>Feature match</dt>
                        <dd>{(c.score_factors.feature_match * 100).toFixed(0)}% <em className="es-muted">({c.score_factors.feature_match_basis})</em></dd>
                      </>
                    )}
                  </dl>
                  {canApprove && activeRun.status === 'computed' && (
                    <>
                      {promoting === c.option_id ? (
                        <div className="es-promote-form">
                          <label htmlFor={`rationale-${c.option_id}`} className="es-label">
                            Approval rationale (required)
                          </label>
                          <textarea
                            id={`rationale-${c.option_id}`}
                            className="es-input"
                            rows={2}
                            value={promoteRationale}
                            onChange={e => setPromoteRationale(e.target.value)}
                            placeholder="Explain why this option was selected…"
                            aria-required="true"
                          />
                          <div style={{ display: 'flex', gap: 8 }}>
                            <button
                              className="btn btn-primary btn-sm"
                              onClick={() => handlePromote(activeRun, c.option_id)}
                              disabled={loading || promoteRationale.length < 10}
                              aria-busy={loading}
                            >
                              {loading ? 'Approving…' : 'Approve this option'}
                            </button>
                            <button className="btn btn-ghost btn-sm" onClick={() => setPromoting(null)}>
                              Cancel
                            </button>
                          </div>
                        </div>
                      ) : (
                        <button
                          className="btn btn-outline btn-sm"
                          onClick={() => { setPromoting(c.option_id); setPromoteRationale('') }}
                        >
                          Select and approve
                        </button>
                      )}
                    </>
                  )}
                  {activeRun.status === 'promoted' && activeRun.promoted_option_id === c.option_id && (
                    <p className="es-approved-note">
                      ✓ Approved by {activeRun.promoted_by} — "{activeRun.promotion_rationale}"
                    </p>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <p className="es-muted">No feasible alternatives found for the given constraints.</p>
          )}

          {/* Infeasible rooms */}
          {result.infeasible.length > 0 && (
            <details className="es-scenario-disclosure">
              <summary>Infeasible rooms ({result.infeasible.length})</summary>
              <ul>
                {result.infeasible.map(inf => (
                  <li key={inf.room_id}>
                    <strong>{inf.room_name}</strong> — {inf.failed_constraints.join('; ')}
                  </li>
                ))}
              </ul>
            </details>
          )}
        </div>
      )}

      {/* Previous runs */}
      {runs.length > 1 && (
        <div className="es-scenario-history">
          <h3>Previous runs</h3>
          <ul>
            {runs.slice(1, 5).map(r => (
              <li key={r.id}>
                <button
                  className="btn btn-ghost btn-sm"
                  onClick={() => setActiveRun(r)}
                  aria-pressed={activeRun?.id === r.id}
                >
                  {new Date(r.created_at).toLocaleTimeString()} — {r.status} — {(r.result?.candidates?.length ?? 0)} candidates
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  )
}


// ── Main Page ─────────────────────────────────────────────────────────────────

export default function EventSpinePage() {
  const { id } = useParams<{ id: string }>()
  const { me } = useIdentity()
  const role = me?.role ?? 'student'

  const [event, setEvent]   = useState<CanonicalEvent | null>(null)
  const [reach, setReach]   = useState<ReachResponse | null>(null)
  const [thread, setThread] = useState<Thread | null>(null)
  const [items, setItems]   = useState<WorkItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError]     = useState<string | null>(null)

  async function load() {
    if (!id) return
    setLoading(true); setError(null)
    try {
      const [ev, wi] = await Promise.all([
        getCanonicalEvent(id),
        getWorkItems({ canonical_event_id: id }),
      ])
      setEvent(ev)
      setItems(wi)
      // Reach and thread can fail silently (403 for students on restricted)
      try { setReach(await getCanonicalEventReach(id)) } catch { /* ok */ }
      try { setThread(await getCanonicalEventThread(id)) } catch { /* ok */ }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to load event')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [id])

  if (loading) return <LoadingState message="Loading event…" />
  if (error || !event) return <ErrorState message={error ?? 'Event not found'} onRetry={load} />

  return (
    <div className="es-page">
      <div className="es-back">
        <Link to="/" className="btn btn-ghost btn-sm">← Back</Link>
      </div>
      <EventHeader event={event} />
      <FactsTimeline event={event} />
      <ImpactSection event={event} />
      <WorkItemsSection items={items} />
      <ReachMapSection reach={reach} />
      <ThreadSection eventId={event.id} thread={thread} onRefresh={load} />
      <ScenarioPanel event={event} role={role} />
      <AuditSection event={event} role={role} />
    </div>
  )
}
