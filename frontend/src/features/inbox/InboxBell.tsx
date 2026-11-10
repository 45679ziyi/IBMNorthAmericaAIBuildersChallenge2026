import { useEffect, useState } from 'react'
import { Bell } from 'lucide-react'
import { fetchInboxUnread } from '../../api/client'
import './InboxBell.css'

interface Props {
  onClick?: () => void
  pollIntervalMs?: number
}

export function InboxBell({ onClick, pollIntervalMs = 30_000 }: Props) {
  const [unread, setUnread] = useState(0)

  useEffect(() => {
    let cancelled = false

    async function poll() {
      try {
        const data = await fetchInboxUnread()
        if (!cancelled) setUnread(data.unread)
      } catch {
        // silently ignore — bell just shows 0
      }
    }

    poll()
    const id = setInterval(poll, pollIntervalMs)
    return () => {
      cancelled = true
      clearInterval(id)
    }
  }, [pollIntervalMs])

  return (
    <button
      className="inbox-bell btn btn-ghost btn-icon"
      onClick={onClick}
      aria-label={unread > 0 ? `Inbox, ${unread} unread` : 'Inbox'}
      title="Inbox"
    >
      <Bell size={17} aria-hidden="true" />
      {unread > 0 && (
        <span className="inbox-bell-badge" aria-hidden="true">
          {unread > 99 ? '99+' : unread}
        </span>
      )}
    </button>
  )
}
