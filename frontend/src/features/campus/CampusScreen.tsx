import { useEffect, useState, useRef, useCallback } from 'react'
import './CampusScreen.css'
import { getAnnouncements, getCampusPulse, Announcement, SensorReading } from '../../api/client'
import { SkeletonList } from '../../components/Skeleton'
import { RefreshCw, MapPin, Activity } from 'lucide-react'

function fmtDate(iso: string | undefined) {
  if (!iso) return null
  return new Date(iso).toLocaleDateString('en-US', {
    month: 'short', day: 'numeric', year: 'numeric', timeZone: 'America/New_York',
  })
}

// ── Campus Pulse Sparkline (pure SVG, live polling) ─────────────────────────
const PULSE_WIDTH = 120
const PULSE_HEIGHT = 32
const MAX_HISTORY = 20

interface SparklineProps { readings: number[]; color: string; label: string }

function Sparkline({ readings, color, label }: SparklineProps) {
  if (readings.length < 2) return <span className="text-muted text-sm">—</span>
  const min = Math.min(...readings)
  const max = Math.max(...readings)
  const range = max - min || 1
  const pts = readings.map((v, i) => {
    const x = (i / (readings.length - 1)) * PULSE_WIDTH
    const y = PULSE_HEIGHT - ((v - min) / range) * (PULSE_HEIGHT - 4) - 2
    return `${x},${y}`
  }).join(' ')

  return (
    <svg
      width={PULSE_WIDTH} height={PULSE_HEIGHT}
      viewBox={`0 0 ${PULSE_WIDTH} ${PULSE_HEIGHT}`}
      aria-label={`${label} sparkline`}
      className="sparkline"
    >
      <polyline fill="none" stroke={color} strokeWidth="1.5" points={pts} strokeLinejoin="round" strokeLinecap="round" />
      {/* Current value dot */}
      {(() => {
        const last = readings[readings.length - 1]
        const x = PULSE_WIDTH
        const y = PULSE_HEIGHT - ((last - min) / range) * (PULSE_HEIGHT - 4) - 2
        return <circle cx={x} cy={y} r="2.5" fill={color} />
      })()}
    </svg>
  )
}

// ── Campus Pulse panel ──────────────────────────────────────────────────────
function CampusPulse() {
  const [readings, setReadings] = useState<SensorReading[]>([])
  const [history, setHistory] = useState<Record<string, number[]>>({})
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const fetchPulse = useCallback(async (isManual = false) => {
    if (isManual) setRefreshing(true)
    try {
      const data = await getCampusPulse()
      setReadings(data)
      setHistory(prev => {
        const next = { ...prev }
        for (const r of data) {
          const key = `${r.sensor_label}::${r.metric_type}`
          const existing = next[key] ?? []
          next[key] = [...existing, r.value].slice(-MAX_HISTORY)
        }
        return next
      })
    } catch { /* silent — data is demo anyway */ }
    setLoading(false)
    if (isManual) setRefreshing(false)
  }, [])

  useEffect(() => {
    fetchPulse()
    intervalRef.current = setInterval(() => fetchPulse(), 8_000)
    return () => { if (intervalRef.current) clearInterval(intervalRef.current) }
  }, [fetchPulse])

  const COLORS: Record<string, string> = {
    temperature: '#3b82d4',
    air_quality: '#22c55e',
    occupancy_count: '#f59e0b',
    device_health: '#8b5cf6',
  }

  return (
    <section aria-labelledby="pulse-heading" className="mt-2">
      <div className="pulse-header">
        <h2 id="pulse-heading">
          Campus Pulse <span className="badge badge-demo">SIMULATED DATA</span>
        </h2>
        <button
          className="btn btn-ghost btn-icon btn-sm"
          onClick={() => fetchPulse(true)}
          disabled={refreshing}
          aria-label="Refresh sensor readings"
          title="Refresh"
        >
          <RefreshCw size={13} className={refreshing ? 'spin' : ''} aria-hidden="true" />
        </button>
      </div>
      <p className="text-muted text-sm mb-1">
        Synthetic sensor telemetry — <strong>NOT connected to SBU systems.</strong> Updates every 8 s with simulated jitter.
      </p>

      {loading
        ? <SkeletonList count={3} lines={2} />
        : (
          <div className="pulse-grid">
            {readings.map(r => {
              const key = `${r.sensor_label}::${r.metric_type}`
              const hist = history[key] ?? [r.value]
              const color = COLORS[r.metric_type] ?? '#57606a'
              return (
                <div key={r.id} className="pulse-card card">
                  <div className="pulse-card-top">
                    <Activity size={13} style={{ color }} aria-hidden="true" />
                    <span className="text-sm font-medium">{r.metric_type.replace('_', ' ')}</span>
                    <span className="pulse-value" style={{ color }}>
                      {r.value} <span className="text-muted">{r.unit}</span>
                    </span>
                  </div>
                  <Sparkline readings={hist} color={color} label={`${r.sensor_label} ${r.metric_type}`} />
                  <div className="text-muted text-sm pulse-label">{r.sensor_label}</div>
                </div>
              )
            })}
          </div>
        )
      }
    </section>
  )
}

// ── Main screen ─────────────────────────────────────────────────────────────
export default function CampusScreen() {
  const [announcements, setAnnouncements] = useState<Announcement[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getAnnouncements()
      .then(a => { setAnnouncements(a); setLoading(false) })
      .catch(e => { setError(String(e)); setLoading(false) })
  }, [])

  return (
    <div>
      <div className="screen-title">
        <h1>Campus</h1>
        <p>Upcoming events, course announcements, and live sensor pulse. Demo data is labeled.</p>
      </div>

      {/* Campus Events — from backend */}
      <section aria-labelledby="campus-events-heading">
        <h2 id="campus-events-heading">
          Campus Events <span className="badge badge-demo">DEMO DATA</span>
        </h2>
        <p className="text-muted text-sm">
          Not connected to live SBU event systems. A future integration would require an authorized feed from SBU.
        </p>
        <ul className="campus-event-list">
          {CAMPUS_EVENTS_DEMO.map(ev => (
            <li key={ev.id} className="card campus-event-item card-hover">
              <div className="flex justify-between items-center">
                <strong>{ev.title}</strong>
                <span className="badge badge-demo">DEMO</span>
              </div>
              <div className="text-muted text-sm">{ev.start}</div>
              <div className="text-muted text-sm flex items-center gap-1">
                <MapPin size={11} aria-hidden="true" /> {ev.location}
              </div>
              <div className="text-sm source-link">Source: {ev.source}</div>
            </li>
          ))}
        </ul>
      </section>

      {/* Course Announcements */}
      <section aria-labelledby="campus-ann-heading" className="mt-2">
        <h2 id="campus-ann-heading">
          Course Announcements <span className="badge badge-demo">DEMO DATA</span>
        </h2>
        <p className="text-muted text-sm">
          Loaded from a local synthetic fixture. No connection to SBU Brightspace.
        </p>
        {error && <div className="state-error">{error}</div>}
        {loading
          ? <SkeletonList count={3} lines={3} />
          : announcements.length === 0
            ? <div className="state-empty">No announcements.</div>
            : (
              <ul className="campus-event-list">
                {announcements.map(a => (
                  <li key={a.id} className="card campus-event-item card-hover">
                    <div className="flex justify-between items-center">
                      <strong>{a.title}</strong>
                      <span className="text-muted text-sm">{a.course_label}</span>
                    </div>
                    <p className="text-sm mt-1">{a.body_summary}</p>
                    <div className="text-muted text-sm">
                      {a.published_at_utc && `Published: ${fmtDate(a.published_at_utc)}`}
                    </div>
                    <span className="badge badge-demo">DEMO DATA</span>
                  </li>
                ))}
              </ul>
            )
        }
      </section>

      {/* Campus Pulse with sparklines */}
      <CampusPulse />
    </div>
  )
}

// ── Demo data constant (below component so file is readable top-to-bottom) ──
const CAMPUS_EVENTS_DEMO = [
  {
    id: 'ce1', title: 'Fall Career Fair 2026',
    start: 'Nov 5, 2026 · 2:00 PM',
    location: 'Island Federal Credit Union Arena',
    source: 'SBU Career Center (Demo)', isDemo: true,
  },
  {
    id: 'ce2', title: 'CS Colloquium: AI in Healthcare',
    start: 'Nov 6, 2026 · 5:00 PM',
    location: 'CS Building Room 2311',
    source: 'SBU CS Department (Demo)', isDemo: true,
  },
  {
    id: 'ce3', title: 'Library Research Workshop',
    start: 'Nov 4, 2026 · 10:00 AM',
    location: 'Melville Library N2017',
    source: 'SBU Libraries (Demo)', isDemo: true,
  },
]
