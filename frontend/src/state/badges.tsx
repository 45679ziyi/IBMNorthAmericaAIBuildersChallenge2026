/**
 * BadgesProvider — global badge counts context.
 * Counts overdue tasks and unread announcements.
 * Refreshes on mount, every 60s, and on window focus.
 */
import { createContext, useContext, useState, useEffect, useCallback } from 'react'
import type { ReactNode } from 'react'
import { getTasks, getUnreadCount } from '../api/client'

interface BadgeState {
  overdueTasks: number
  unreadAnnouncements: number
}

interface BadgesCtxValue {
  badges: BadgeState
  refresh: () => void
}

export const BadgesCtx = createContext<BadgesCtxValue>({
  badges: { overdueTasks: 0, unreadAnnouncements: 0 },
  refresh: () => {},
})

export function BadgesProvider({ children }: { children: ReactNode }): JSX.Element {
  const [badges, setBadges] = useState<BadgeState>({ overdueTasks: 0, unreadAnnouncements: 0 })

  const refresh = useCallback(async () => {
    try {
      const [tasks, unread] = await Promise.all([
        getTasks(),
        getUnreadCount(),
      ])
      const now = Date.now()
      const overdue = tasks.filter(
        t => t.status !== 'done' && t.due_at_utc && new Date(t.due_at_utc).getTime() < now
      ).length
      setBadges({ overdueTasks: overdue, unreadAnnouncements: unread.unread })
    } catch {
      /* silent — badge data is best-effort */
    }
  }, [])

  // On mount and every 60s
  useEffect(() => {
    refresh()
    const id = setInterval(refresh, 60_000)
    return () => clearInterval(id)
  }, [refresh])

  // On window focus
  useEffect(() => {
    window.addEventListener('focus', refresh)
    return () => window.removeEventListener('focus', refresh)
  }, [refresh])

  return (
    <BadgesCtx.Provider value={{ badges, refresh }}>
      {children}
    </BadgesCtx.Provider>
  )
}

export function useBadges(): BadgesCtxValue {
  return useContext(BadgesCtx)
}
