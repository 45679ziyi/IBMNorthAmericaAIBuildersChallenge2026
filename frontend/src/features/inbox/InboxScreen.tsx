import { useEffect, useState, useCallback } from 'react'
import { CheckCheck, Eye } from 'lucide-react'
import {
  fetchInbox,
  markInboxRead,
  markInboxAck,
  type InboxNotification,
} from '../../api/client'
import './InboxScreen.css'

// ── Helpers ───────────────────────────────────────────────────────────────────

function stateChipClass(state: string): string {
  if (state === 'unread') return 'chip chip-unread'
  if (state === 'acknowledged') return 'chip chip-ack'
  return 'chip chip-read'
}

function stateLabel(state: string): string {
  if (state === 'unread') return 'Unread'
  if (state === 'acknowledged') return 'Acknowledged'
  return 'Read'
}

function kindLabel(kind: string): string {
  return kind.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function InboxScreen() {
  const [notifications, setNotifications] = useState<InboxNotification[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      setError(null)
      const data = await fetchInbox()
      // sort: unread first, then by created_at desc
      data.sort((a, b) => {
        if (a.state === 'unread' && b.state !== 'unread') return -1
        if (a.state !== 'unread' && b.state === 'unread') return 1
        return b.created_at.localeCompare(a.created_at)
      })
      setNotifications(data)
    } catch (e) {
      setError(String(e))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  async function handleRead(id: string) {
    const updated = await markInboxRead(id)
    setNotifications(prev =>
      prev.map(n => (n.id === id ? updated : n)).sort((a, b) => {
        if (a.state === 'unread' && b.state !== 'unread') return -1
        if (a.state !== 'unread' && b.state === 'unread') return 1
        return b.created_at.localeCompare(a.created_at)
      })
    )
  }

  async function handleAck(id: string) {
    const updated = await markInboxAck(id)
    setNotifications(prev =>
      prev.map(n => (n.id === id ? updated : n))
    )
  }

  if (loading) return <div className="inbox-loading">Loading inbox…</div>
  if (error) return <div className="inbox-error">Error: {error}</div>
  if (notifications.length === 0)
    return <div className="inbox-empty">Your inbox is empty.</div>

  return (
    <div className="inbox-screen">
      <h2 className="inbox-title">Inbox</h2>
      <ul className="inbox-list" aria-label="Notifications">
        {notifications.map(n => (
          <li key={n.id} className={`inbox-item${n.state === 'unread' ? ' inbox-item-unread' : ''}`}>
            <div className="inbox-item-header">
              <span className="inbox-kind">{kindLabel(n.kind)}</span>
              <span className={stateChipClass(n.state)} aria-label={`State: ${stateLabel(n.state)}`}>
                {stateLabel(n.state)}
              </span>
            </div>

            <p className="inbox-item-title">{n.title}</p>
            {n.body && <p className="inbox-item-body">{n.body}</p>}

            {/* Why[] evidence path */}
            {n.why.length > 0 && (
              <ul className="inbox-why" aria-label="Why you received this">
                {n.why.map((w, i) => (
                  <li key={i} className="inbox-why-entry">
                    <span className="why-rel">{w.rel}</span>{' '}
                    <span className="why-entity">{w.entity_type}:{w.entity_id}</span>
                    {w.text && <span className="why-text"> — {w.text}</span>}
                  </li>
                ))}
              </ul>
            )}

            <div className="inbox-item-actions">
              {n.state === 'unread' && (
                <button
                  className="btn btn-ghost btn-sm"
                  onClick={() => handleRead(n.id)}
                  aria-label="Mark as read"
                >
                  <Eye size={14} aria-hidden="true" /> Read
                </button>
              )}
              {n.requires_ack && n.state !== 'acknowledged' && (
                <button
                  className="btn btn-primary btn-sm"
                  onClick={() => handleAck(n.id)}
                  aria-label="Acknowledge"
                >
                  <CheckCheck size={14} aria-hidden="true" /> Acknowledge
                </button>
              )}
            </div>

            <time className="inbox-time" dateTime={n.created_at}>
              {new Date(n.created_at).toLocaleString()}
            </time>
          </li>
        ))}
      </ul>
    </div>
  )
}
