/**
 * Time utilities — all dates displayed in campus timezone (Eastern).
 */

export const CAMPUS_TZ = 'America/New_York'

/** Format an ISO string as "10:00 AM" in campus timezone. */
export function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString('en-US', {
    hour: 'numeric',
    minute: '2-digit',
    timeZone: CAMPUS_TZ,
  })
}

/** Format an ISO string as "Mon, Nov 3" in campus timezone. */
export function formatDay(iso: string): string {
  return new Date(iso).toLocaleDateString('en-US', {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
    timeZone: CAMPUS_TZ,
  })
}

/** Returns the YYYY-MM-DD date string (campus tz) for an ISO string. */
function toLocaleDateStr(iso: string): string {
  return new Date(iso).toLocaleDateString('en-CA', { timeZone: CAMPUS_TZ })
}

/** Returns true if two ISO strings fall on the same calendar day (campus tz). */
export function isSameDay(isoA: string, isoB: string): boolean {
  return toLocaleDateStr(isoA) === toLocaleDateStr(isoB)
}

/** Returns true if the ISO string is on today's date (campus tz). */
export function isSameDayAsNow(iso: string): boolean {
  return toLocaleDateStr(iso) === toLocaleDateStr(new Date().toISOString())
}

/** Returns a Date set to midnight on the given YYYY-MM-DD date string (campus tz). */
export function startOfDay(isoDate: string): Date {
  // Parse as campus-tz midnight via explicit locale formatting trick
  const [y, m, d] = isoDate.split('-').map(Number)
  // Use Intl to figure out UTC offset at that date in campus tz
  const candidate = new Date(Date.UTC(y, m - 1, d, 12, 0, 0))
  const localStr = candidate.toLocaleString('en-CA', {
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit',
    hour12: false, timeZone: CAMPUS_TZ,
  })
  // localStr looks like "2026-11-07, 07:00:00"
  const parts = localStr.replace(', ', 'T')
  const localMidnight = new Date(parts.replace(/^(.{10})T(.{8})$/, `$1T00:00:00`))
  return localMidnight
}

/** Relative due text for a task's due_at_utc. Returns null if no due date. */
export function relativeDue(
  iso: string | undefined
): { text: string; isOverdue: boolean } | null {
  if (!iso) return null
  const due = new Date(iso)
  const now = new Date()
  const diffMs = due.getTime() - now.getTime()
  const diffDays = Math.round(diffMs / (1000 * 60 * 60 * 24))

  if (diffMs < 0) {
    const absDays = Math.abs(diffDays)
    if (absDays === 0) return { text: 'Overdue today', isOverdue: true }
    if (absDays === 1) return { text: 'Overdue by 1 day', isOverdue: true }
    return { text: `Overdue by ${absDays} days`, isOverdue: true }
  }

  if (isSameDayAsNow(iso)) return { text: 'Due today', isOverdue: false }

  if (diffDays === 1) return { text: 'Due tomorrow', isOverdue: false }

  if (diffDays <= 6) {
    const weekday = due.toLocaleDateString('en-US', { weekday: 'short', timeZone: CAMPUS_TZ })
    return { text: `Due ${weekday}`, isOverdue: false }
  }

  const dateStr = due.toLocaleDateString('en-US', { month: 'short', day: 'numeric', timeZone: CAMPUS_TZ })
  return { text: `Due ${dateStr}`, isOverdue: false }
}

/** Minutes from now until the given ISO timestamp (negative if in the past). */
export function minutesUntil(iso: string): number {
  return Math.round((new Date(iso).getTime() - Date.now()) / 60_000)
}

/** Time-of-day greeting based on campus timezone hour. */
export function greeting(): string {
  const h = parseInt(
    new Date().toLocaleString('en-US', { hour: 'numeric', hour12: false, timeZone: CAMPUS_TZ }),
    10
  )
  if (h < 12) return 'Good morning'
  if (h < 17) return 'Good afternoon'
  return 'Good evening'
}
