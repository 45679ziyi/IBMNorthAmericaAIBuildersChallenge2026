import { useState, useEffect } from 'react'
import { getWorkItems, type WorkItem } from '../../api/client'
import { useIdentity } from '../../hooks/useIdentity'
import { LoadingState } from '../../components/states/LoadingState'
import { ErrorState } from '../../components/states/ErrorState'
import { EmptyState } from '../../components/states/EmptyState'
import { PermissionDenied } from '../../components/states/PermissionDenied'
import '../../components/states/states.css'

export default function OrgScreen() {
  const { me } = useIdentity()
  const [items, setItems] = useState<WorkItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getWorkItems({ workflow_type: 'event_change' })
      .then(setItems)
      .catch(e => setError(String(e)))
      .finally(() => setLoading(false))
  }, [])

  if (me && me.role !== 'org_organizer' && me.role !== 'academic_ops') {
    return <PermissionDenied requiredRole="org_organizer" currentRole={me.role} />
  }
  if (loading) return <LoadingState message="Loading events…" />
  if (error) return <ErrorState message={error} />

  return (
    <div style={{ maxWidth: 900 }}>
      <div className="screen-title">
        <h1>Student Org Events</h1>
        <p>Event change requests and approvals.</p>
      </div>

      <section>
        <h2>Event Changes ({items.length})</h2>
        {items.length === 0 ? (
          <EmptyState title="No event changes" message="Event change requests will appear here." />
        ) : (
          <ul style={{ listStyle: 'none', padding: 0, margin: 0, display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
            {items.map(wi => (
              <li key={wi.id} className="card" style={{ padding: '0.75rem 1rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '1rem' }}>
                <span style={{ fontWeight: 500 }}>Event Change</span>
                <span style={{ fontSize: '.75rem', color: 'var(--ink-muted)', padding: '2px 8px', background: 'var(--surface)', borderRadius: 'var(--r-pill)', border: '1px solid var(--line)' }}>
                  {wi.status}
                </span>
                <span style={{ fontSize: '.8rem', color: 'var(--ink-muted)' }}>
                  {new Date(wi.created_at).toLocaleDateString()}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  )
}
