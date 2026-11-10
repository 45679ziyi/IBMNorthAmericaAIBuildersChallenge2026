import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { getWorkItems, getCampusIncidents, type WorkItem, type CanonicalEvent } from '../../api/client'
import { useIdentity } from '../../hooks/useIdentity'
import { LoadingState } from '../../components/states/LoadingState'
import { ErrorState } from '../../components/states/ErrorState'
import { EmptyState } from '../../components/states/EmptyState'
import { PermissionDenied } from '../../components/states/PermissionDenied'
import '../../components/states/states.css'

export default function ITScreen() {
  const { me } = useIdentity()
  const [items, setItems] = useState<WorkItem[]>([])
  const [incidents, setIncidents] = useState<CanonicalEvent[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    Promise.all([
      getWorkItems({ team: 'it' }),
      getCampusIncidents().catch(() => [] as CanonicalEvent[]),
    ])
      .then(([wi, ci]) => { setItems(wi); setIncidents(ci as CanonicalEvent[]) })
      .catch(e => setError(String(e)))
      .finally(() => setLoading(false))
  }, [])

  if (me && !['it', 'academic_ops'].includes(me.role)) {
    return <PermissionDenied requiredRole="it" currentRole={me.role} />
  }
  if (loading) return <LoadingState message="Loading IT Ops…" />
  if (error) return <ErrorState message={error} />

  const disruptions = incidents.filter(i => i.type.includes('service_disruption') || i.type.includes('service'))

  return (
    <div style={{ maxWidth: 900 }}>
      <div className="screen-title">
        <h1>IT Operations</h1>
        <p>Service status and active incidents.</p>
      </div>

      <section style={{ marginBottom: '2rem' }}>
        <h2>Service Disruptions</h2>
        {disruptions.length === 0 ? (
          <p className="state-message" style={{ color: 'var(--ink-muted)' }}>✓ All services operational</p>
        ) : (
          <ul style={{ listStyle: 'none', padding: 0, margin: 0, display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
            {disruptions.slice(0, 10).map(inc => (
              <li key={inc.id} className="card" style={{ padding: '0.75rem 1rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span>{inc.type.replace(/\./g, ' › ')}</span>
                <span style={{ fontSize: '.75rem', color: 'var(--ink-muted)' }}>{inc.severity}</span>
                <Link to={`/events/${inc.id}`} style={{ fontSize: '.8rem', color: 'var(--dawn)' }}>Details →</Link>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section>
        <h2>Work Queue ({items.length})</h2>
        {items.length === 0 ? (
          <EmptyState title="No active items" />
        ) : (
          <ul style={{ listStyle: 'none', padding: 0, margin: 0, display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
            {items.slice(0, 15).map(wi => (
              <li key={wi.id} className="card" style={{ padding: '0.75rem 1rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '1rem' }}>
                <span style={{ fontWeight: 500 }}>{wi.workflow_type.replace(/_/g, ' ')}</span>
                <span style={{ fontSize: '.75rem', color: 'var(--ink-muted)', padding: '2px 8px', background: 'var(--surface)', borderRadius: 'var(--r-pill)', border: '1px solid var(--line)' }}>{wi.status}</span>
                {wi.canonical_event_id && (
                  <Link to={`/events/${wi.canonical_event_id}`} style={{ fontSize: '.8rem', color: 'var(--dawn)', whiteSpace: 'nowrap' }}>Event →</Link>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  )
}
