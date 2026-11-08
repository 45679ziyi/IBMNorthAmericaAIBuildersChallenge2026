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

// ── M0 additions ──────────────────────────────────────────────────────────────

const toDate = (v: string | number | Date): Date => (v instanceof Date ? v : new Date(v))

/** 'YYYY-MM-DD' in campus time. */
export const dayKey = (v: string | number | Date): string =>
  toDate(v).toLocaleDateString('en-CA', { timeZone: CAMPUS_TZ })

/** Minutes since midnight, campus time. Never use Date#getHours/getMinutes. */
export function minutesIntoDay(v: string | number | Date): number {
  const p = new Intl.DateTimeFormat('en-US', {
    hour: 'numeric', minute: 'numeric', hourCycle: 'h23', timeZone: CAMPUS_TZ,
  }).formatToParts(toDate(v))
  return (
    Number(p.find(x => x.type === 'hour')?.value ?? 0) * 60 +
    Number(p.find(x => x.type === 'minute')?.value ?? 0)
  )
}

function tzOffsetMs(ts: number): number {
  const p = new Intl.DateTimeFormat('en-US', {
    timeZone: CAMPUS_TZ, hourCycle: 'h23',
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit',
  }).formatToParts(ts)
  const g = (t: string): number => Number(p.find(x => x.type === t)!.value)
  return Date.UTC(g('year'), g('month') - 1, g('day'), g('hour'), g('minute'), g('second')) - Math.floor(ts / 1000) * 1000
}

/** 'YYYY-MM-DDTHH:mm' campus wall time → ISO UTC (for datetime-local inputs). */
export function localInputToIso(v: string): string {
  const naive = Date.parse(`${v}:00Z`)
  const first = naive - tzOffsetMs(naive)
  return new Date(naive - tzOffsetMs(first)).toISOString()
}

/** ISO UTC → 'YYYY-MM-DDTHH:mm' campus wall time (for datetime-local inputs). */
export function isoToLocalInput(iso: string): string {
  const ts = Date.parse(iso)
  return new Date(ts + tzOffsetMs(ts)).toISOString().slice(0, 16)
}
