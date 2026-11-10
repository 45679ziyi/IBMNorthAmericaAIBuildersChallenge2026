/**
 * Time utilities — all dates displayed in campus timezone.
 *
 * U2: The timezone is no longer a hardcoded constant.  Use getTz() to get
 * the current timezone, and setTz() to update it when the tenant config loads.
 *
 * NEVER use Date#getHours, Date#getMinutes, or hardcoded timezone literals
 * in this file or anywhere else.  Always pass the tz string explicitly.
 */

// ── Timezone state ─────────────────────────────────────────────────────────────

let _campusTz = 'America/New_York'
let _campusClock: '12h' | '24h' = '12h'

/** Return the current campus timezone string. */
export function getTz(): string { return _campusTz }

/** Update the campus timezone (called when tenant config loads). */
export function setTz(tz: string): void { _campusTz = tz }

/** Return the current campus clock mode. */
export function getClock(): '12h' | '24h' { return _campusClock }

/** Update the campus clock mode (called when tenant config loads). */
export function setClock(c: '12h' | '24h'): void { _campusClock = c }

/**
 * @deprecated Use getTz() instead.  Kept for backward compatibility only.
 * Will be removed in a future cleanup pass.
 */
export const CAMPUS_TZ = _campusTz

/** Format an ISO string as "10:00 AM" (or "10:00" for 24h) in campus timezone. */
export function formatTime(iso: string, tz = getTz(), clock = getClock()): string {
  return new Date(iso).toLocaleTimeString('en-US', {
    hour: 'numeric',
    minute: '2-digit',
    hour12: clock === '12h',
    timeZone: tz,
  })
}

/** Format an ISO string as "Mon, Nov 3" in campus timezone. */
export function formatDay(iso: string, tz = getTz()): string {
  return new Date(iso).toLocaleDateString('en-US', {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
    timeZone: tz,
  })
}

/** Returns the YYYY-MM-DD date string (campus tz) for an ISO string. */
function toLocaleDateStr(iso: string, tz = getTz()): string {
  return new Date(iso).toLocaleDateString('en-CA', { timeZone: tz })
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
export function startOfDay(isoDate: string, tz = getTz()): Date {
  const [y, m, d] = isoDate.split('-').map(Number)
  const candidate = new Date(Date.UTC(y, m - 1, d, 12, 0, 0))
  const localStr = candidate.toLocaleString('en-CA', {
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit',
    hour12: false, timeZone: tz,
  })
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
  const tz = getTz()

  if (diffMs < 0) {
    const absDays = Math.abs(diffDays)
    if (absDays === 0) return { text: 'Overdue today', isOverdue: true }
    if (absDays === 1) return { text: 'Overdue by 1 day', isOverdue: true }
    return { text: `Overdue by ${absDays} days`, isOverdue: true }
  }

  if (isSameDayAsNow(iso)) return { text: 'Due today', isOverdue: false }

  if (diffDays === 1) return { text: 'Due tomorrow', isOverdue: false }

  if (diffDays <= 6) {
    const weekday = due.toLocaleDateString('en-US', { weekday: 'short', timeZone: tz })
    return { text: `Due ${weekday}`, isOverdue: false }
  }

  const dateStr = due.toLocaleDateString('en-US', { month: 'short', day: 'numeric', timeZone: tz })
  return { text: `Due ${dateStr}`, isOverdue: false }
}

/** Minutes from now until the given ISO timestamp (negative if in the past). */
export function minutesUntil(iso: string): number {
  return Math.round((new Date(iso).getTime() - Date.now()) / 60_000)
}

/** Time-of-day greeting based on campus timezone hour. */
export function greeting(tz = getTz()): string {
  const h = parseInt(
    new Date().toLocaleString('en-US', { hour: 'numeric', hour12: false, timeZone: tz }),
    10
  )
  if (h < 12) return 'Good morning'
  if (h < 17) return 'Good afternoon'
  return 'Good evening'
}

// ── M0 additions ──────────────────────────────────────────────────────────────

const toDate = (v: string | number | Date): Date => (v instanceof Date ? v : new Date(v))

/** 'YYYY-MM-DD' in campus time. */
export const dayKey = (v: string | number | Date, tz = getTz()): string =>
  toDate(v).toLocaleDateString('en-CA', { timeZone: tz })

/** Minutes since midnight, campus time. Never use Date#getHours/getMinutes. */
export function minutesIntoDay(v: string | number | Date, tz = getTz()): number {
  const p = new Intl.DateTimeFormat('en-US', {
    hour: 'numeric', minute: 'numeric', hourCycle: 'h23', timeZone: tz,
  }).formatToParts(toDate(v))
  return (
    Number(p.find(x => x.type === 'hour')?.value ?? 0) * 60 +
    Number(p.find(x => x.type === 'minute')?.value ?? 0)
  )
}

function tzOffsetMs(ts: number, tz = getTz()): number {
  const p = new Intl.DateTimeFormat('en-US', {
    timeZone: tz, hourCycle: 'h23',
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit',
  }).formatToParts(ts)
  const g = (t: string): number => Number(p.find(x => x.type === t)!.value)
  return Date.UTC(g('year'), g('month') - 1, g('day'), g('hour'), g('minute'), g('second')) - Math.floor(ts / 1000) * 1000
}

/** 'YYYY-MM-DDTHH:mm' campus wall time → ISO UTC (for datetime-local inputs). */
export function localInputToIso(v: string, tz = getTz()): string {
  const naive = Date.parse(`${v}:00Z`)
  const first = naive - tzOffsetMs(naive, tz)
  return new Date(naive - tzOffsetMs(first, tz)).toISOString()
}

/** ISO UTC → 'YYYY-MM-DDTHH:mm' campus wall time (for datetime-local inputs). */
export function isoToLocalInput(iso: string, tz = getTz()): string {
  const ts = Date.parse(iso)
  return new Date(ts + tzOffsetMs(ts, tz)).toISOString().slice(0, 16)
}
