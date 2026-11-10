import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { getWorkItems, type WorkItem } from '../../api/client'
import { useIdentity } from '../../hooks/useIdentity'
import { LoadingState } from '../../components/states/LoadingState'
import { ErrorState } from '../../components/states/ErrorState'
import { EmptyState } from '../../components/states/EmptyState'
import { PermissionDenied } from '../../components/states/PermissionDenied'
import '../../components/states/states.css'

export default function AcadopsScreen() {
  const { me } = useIdentity()
  const [approvals, setApprovals] = useState<WorkItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getWorkItems({ workflow_type: 'room_reassignment', status: 'awaiting_approval' })
      .then(setApprovals)
      .catch(e => setError(String(e)))
      .finally(() => setLoading(false))
  }, [])

  if (me && me.role !== 'academic_ops') {
    return <PermissionDenied requiredRole="academic_ops" currentRole={me.role} />
  }
  if (loading) return <LoadingState message="Loading approval queue…" />
  if (error) return <ErrorState message={error} />

  return (
    <div style={{ maxWidth: 900 }}>
      <div className="screen-title">
        <h1>Academic Operations</h1>
        <p>Room reassignment approval queue.</p>
      </div>

      <section>
        <h2>Awaiting Approval ({approvals.length})</h2>
        {approvals.length === 0 ? (
          <EmptyState title="No pending approvals" message="Room reassignment requests will appear here." />
        ) : (
          <ul style={{ listStyle: 'none', padding: 0, margin: 0, display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
            {approvals.map(wi => {
              const payload = wi.payload as Record<string, unknown>
              return (
                <li key={wi.id} className="card" style={{ padding: '1rem' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '1rem' }}>
                    <div>
                      <strong>Room Reassignment</strong>
                      {payload.proposed_room != null && (
                        <p style={{ margin: '4px 0 0', fontSize: '.88rem', color: 'var(--ink-muted)' }}>
                          Proposed room: {payload.proposed_room as string}
                        </p>
                      )}
                    </div>
                    <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                      <span style={{ fontSize: '.75rem', padding: '2px 8px', background: 'var(--surface)', border: '1px solid var(--line)', borderRadius: 'var(--r-pill)' }}>
                        {wi.status}
                      </span>
                      {wi.canonical_event_id && (
                        <Link to={`/events/${wi.canonical_event_id}`} style={{ fontSize: '.8rem', color: 'var(--dawn)' }}>
                          Event →
                        </Link>
                      )}
                    </div>
                  </div>
                </li>
              )
            })}
          </ul>
        )}
      </section>
    </div>
  )
}
