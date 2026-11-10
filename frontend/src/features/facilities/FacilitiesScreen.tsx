import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { getWorkItems, transitionWorkItem, type WorkItem } from '../../api/client'
import { useIdentity } from '../../hooks/useIdentity'
import { CampusMap } from '../campus/CampusMap'
import { LoadingState } from '../../components/states/LoadingState'
import { ErrorState } from '../../components/states/ErrorState'
import { EmptyState } from '../../components/states/EmptyState'
import { PermissionDenied } from '../../components/states/PermissionDenied'
import '../../components/states/states.css'
import './FacilitiesScreen.css'

const MIN_CELL = 5

function suppressCount(n: number | undefined) {
  if (n === undefined) return '—'
  return n < MIN_CELL ? `fewer than ${MIN_CELL}` : String(n)
}

function statusColor(s: string) {
  if (s.includes('resolv') || s.includes('closed')) return 'status-green'
  if (s.includes('triage') || s.includes('assess')) return 'status-yellow'
  return 'status-blue'
}

export default function FacilitiesScreen() {
  const { me } = useIdentity()
  const [items, setItems] = useState<WorkItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selected, setSelected] = useState<WorkItem | null>(null)
  const [transitioning, setTransitioning] = useState(false)
  const [transErr, setTransErr] = useState<string | null>(null)
  const [proposedRoom, setProposedRoom] = useState('')

  async function load() {
    setLoading(true); setError(null)
    try {
      const data = await getWorkItems({ team: 'facilities' })
      setItems(data)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to load work items')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  async function handleProposeMitigation() {
    if (!selected || !proposedRoom.trim()) return
    setTransitioning(true); setTransErr(null)
    try {
      await transitionWorkItem(selected.id, 'propose_mitigation', { proposed_room: proposedRoom.trim() })
      setSelected(null); setProposedRoom('')
      load()
    } catch (e: unknown) {
      setTransErr(e instanceof Error ? e.message : 'Transition failed')
    } finally {
      setTransitioning(false)
    }
  }

  if (me && !['facilities', 'academic_ops'].includes(me.role)) {
    return <PermissionDenied requiredRole="facilities" currentRole={me.role} />
  }
  if (loading) return <LoadingState message="Loading work queue…" />
  if (error) return <ErrorState message={error} onRetry={load} />

  // Incident-type work items
  const incidents = items.filter(wi =>
    wi.workflow_type === 'incident_response' || wi.workflow_type === 'room_reassignment'
  )
  const incidentBuildingIds = incidents.flatMap(wi => {
    const payload = wi.payload as Record<string, unknown>
    return payload.building_id ? [String(payload.building_id)] : []
  })

  return (
    <div className="facilities-screen">
      <div className="screen-title">
        <h1>Facilities Workspace</h1>
        <p>Work order queue, incident triage, and campus map.</p>
      </div>

      <div className="facilities-layout">
        {/* Left: work queue */}
        <div className="facilities-queue">
          <section>
            <h2>Work Queue ({incidents.length})</h2>
            {incidents.length === 0 ? (
              <EmptyState title="Queue is clear" message="No active incidents or room reassignments." />
            ) : (
              <ul className="fac-item-list">
                {incidents.map(wi => {
                  const payload = wi.payload as Record<string, unknown>
                  return (
                    <li
                      key={wi.id}
                      className={`fac-item card${selected?.id === wi.id ? ' fac-item-selected' : ''}`}
                      onClick={() => setSelected(prev => prev?.id === wi.id ? null : wi)}
                      role="button"
                      tabIndex={0}
                      onKeyDown={e => e.key === 'Enter' && setSelected(prev => prev?.id === wi.id ? null : wi)}
                      aria-expanded={selected?.id === wi.id}
                    >
                      <div className="fac-item-row">
                        <div className="fac-item-meta">
                          <span className="fac-item-type">{wi.workflow_type.replace(/_/g, ' ')}</span>
                          {payload.building_id != null && <span className="fac-item-building">📍 {payload.building_id as string}</span>}
                        </div>
                        <span className={`fac-status ${statusColor(wi.status)}`}>{wi.status}</span>
                      </div>
                      {payload.affected_sections !== undefined && (
                        <p className="fac-item-detail text-sm text-muted">
                          Affected sections: {suppressCount(Number(payload.affected_sections))}
                        </p>
                      )}
                      {wi.canonical_event_id && (
                        <Link
                          to={`/events/${wi.canonical_event_id}`}
                          className="fac-event-link text-sm"
                          onClick={e => e.stopPropagation()}
                        >
                          View event →
                        </Link>
                      )}

                      {/* Triage panel */}
                      {selected?.id === wi.id && (
                        <div className="fac-triage-panel" onClick={e => e.stopPropagation()}>
                          <h4>Propose room change</h4>
                          <input
                            type="text"
                            className="form-control"
                            placeholder="Proposed room (e.g. JAV-102)"
                            value={proposedRoom}
                            onChange={e => setProposedRoom(e.target.value)}
                          />
                          {transErr && <p className="form-error">{transErr}</p>}
                          <div className="fac-triage-actions">
                            <button
                              className="btn btn-primary btn-sm"
                              disabled={!proposedRoom.trim() || transitioning}
                              onClick={handleProposeMitigation}
                            >
                              {transitioning ? 'Proposing…' : 'Propose mitigation'}
                            </button>
                          </div>
                        </div>
                      )}
                    </li>
                  )
                })}
              </ul>
            )}
          </section>
        </div>

        {/* Right: campus map */}
        <div className="facilities-map-col">
          <section>
            <h2>Campus Map</h2>
            <CampusMap highlightBuildings={incidentBuildingIds} compact={false} />
          </section>
        </div>
      </div>
    </div>
  )
}
