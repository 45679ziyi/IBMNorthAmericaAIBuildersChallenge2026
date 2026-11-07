import { useEffect, useState, useRef, useCallback } from 'react'
import { useSearchParams } from 'react-router-dom'
import './CampusScreen.css'
import {
  getAnnouncements, getCampusPulse, getPulseSeries, getPulseInsights,
  getSecurityReport, runSecurityCheck, escalateFinding,
  markAnnouncementRead, markAllAnnouncementsRead,
  Announcement, SensorReading, PulseSeries, PulseInsight, SecurityReport,
} from '../../api/client'
import { SkeletonList } from '../../components/Skeleton'
import { StatusChip } from '../../components/StatusChip'
import { ErrorState } from '../../components/ErrorState'
import { Tabs, TabPanel } from '../../components/Tabs'
import { useToast } from '../../components/Toast'
import { useConfirm } from '../../components/ConfirmModal'
import { useBadges } from '../../state/badges'
import { formatTime, formatDay } from '../../lib/time'
import { RefreshCw, MapPin, Activity, CheckCircle, AlertCircle, XCircle, ExternalLink, ChevronDown } from 'lucide-react'

function fmtDate(iso: string | undefined) {
  if (!iso) return null
  return new Date(iso).toLocaleDateString('en-US', {
    month: 'short', day: 'numeric', year: 'numeric', timeZone: 'America/New_York',
  })
}

// ── Events tab ────────────────────────────────────────────────────────────────
const CAMPUS_EVENTS_DEMO = [
  { id: 'ce1', title: 'Fall Career Fair 2026', start: 'Nov 5, 2026 · 2:00 PM', location: 'Island Federal Credit Union Arena', source: 'SBU Career Center' },
  { id: 'ce2', title: 'CS Colloquium: AI in Healthcare', start: 'Nov 6, 2026 · 5:00 PM', location: 'CS Building Room 2311', source: 'SBU CS Department' },
  { id: 'ce3', title: 'Library Research Workshop', start: 'Nov 4, 2026 · 10:00 AM', location: 'Melville Library N2017', source: 'SBU Libraries' },
]

function EventsTab() {
  return (
    <div>
      <p className="text-muted text-sm campus-tab-note">
        Not connected to live SBU event systems.
      </p>
      <ul className="campus-list">
        {CAMPUS_EVENTS_DEMO.map(ev => (
          <li key={ev.id} className="campus-event-item card">
            <div className="campus-event-top">
              <strong>{ev.title}</strong>
              <StatusChip variant="demo" label="Demo" />
            </div>
            <div className="text-muted text-sm">{ev.start}</div>
            <div className="text-muted text-sm campus-location">
              <MapPin size={11} aria-hidden="true" /> {ev.location}
            </div>
            <div className="text-sm text-muted">Source: {ev.source}</div>
          </li>
        ))}
      </ul>
    </div>
  )
}

// ── Announcements tab ─────────────────────────────────────────────────────────
function AnnouncementsTab() {
  const [announcements, setAnnouncements] = useState<Announcement[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  const { refresh: refreshBadges } = useBadges()

  const load = useCallback(() => {
    getAnnouncements()
      .then(a => { setAnnouncements(a); setLoading(false) })
      .catch(e => { setError(String(e)); setLoading(false) })
  }, [])

  useEffect(() => { load() }, [load])

  async function handleExpand(id: string) {
    setExpanded(prev => {
      const next = new Set(prev)
      if (next.has(id)) { next.delete(id) } else { next.add(id) }
      return next
    })
    const ann = announcements.find(a => a.id === id)
    if (ann && !ann.is_read) {
      try {
        await markAnnouncementRead(id, true)
        setAnnouncements(prev => prev.map(a => a.id === id ? { ...a, is_read: true } : a))
        refreshBadges()
      } catch { /* silent */ }
    }
  }

  async function handleMarkAllRead() {
    try {
      await markAllAnnouncementsRead()
      setAnnouncements(prev => prev.map(a => ({ ...a, is_read: true })))
      refreshBadges()
    } catch (e) { setError(String(e)) }
  }

  const unreadCount = announcements.filter(a => !a.is_read).length

  if (loading) return <SkeletonList count={3} lines={3} />
  if (error) return <ErrorState message={`Couldn't load announcements. Check that the backend is running on port 8000, then try again.`} onRetry={load} />

  return (
    <div>
      <div className="ann-tab-header">
        <p className="text-muted text-sm campus-tab-note">Loaded from synthetic fixture. No connection to Brightspace.</p>
        <div className="ann-tab-actions">
          <StatusChip variant="demo" label="Demo data" />
          {unreadCount > 0 && (
            <button className="btn btn-ghost btn-sm" onClick={handleMarkAllRead}>
              Mark all read
            </button>
          )}
        </div>
      </div>
      {announcements.length === 0
        ? <div className="state-empty">No announcements.</div>
        : (
          <ul className="campus-list">
            {announcements.map(a => (
              <li key={a.id} className="card ann-tab-item">
                <button
                  className="ann-tab-summary"
                  onClick={() => handleExpand(a.id)}
                  aria-expanded={expanded.has(a.id)}
                >
                  <div className="ann-tab-title-row">
                    {!a.is_read && <span className="ann-unread-dot" aria-label="Unread" />}
                    <strong className="ann-tab-title">{a.title}</strong>
                    <span className="text-muted text-sm">{a.course_label}</span>
                  </div>
                  <ChevronDown size={14} className={`ann-chevron${expanded.has(a.id) ? ' ann-chevron-open' : ''}`} aria-hidden="true" />
                </button>
                {expanded.has(a.id) && (
                  <div className="ann-tab-body">
                    <p className="text-sm">{a.body_summary}</p>
                    {a.published_at_utc && (
                      <p className="text-muted text-sm">Published: {fmtDate(a.published_at_utc)}</p>
                    )}
                    {a.source_url && (
                      <a href={a.source_url} target="_blank" rel="noopener noreferrer" className="flex items-center gap-1 text-sm">
                        Source <ExternalLink size={11} aria-hidden="true" />
                      </a>
                    )}
                  </div>
                )}
              </li>
            ))}
          </ul>
        )
      }
    </div>
  )
}

// ── Sparkline ─────────────────────────────────────────────────────────────────
const PULSE_W = 120
const PULSE_H = 32

interface SparklineProps {
  values: number[]
  metricType: string
  latestValue: number
  unit: string
}

function Sparkline({ values, metricType, latestValue, unit }: SparklineProps) {
  if (values.length < 2) return <span className="text-muted text-sm">—</span>
  const min = Math.min(...values)
  const max = Math.max(...values)
  const range = max - min || 1
  const pts = values.map((v, i) => {
    const x = (i / (values.length - 1)) * PULSE_W
    const y = PULSE_H - ((v - min) / range) * (PULSE_H - 4) - 2
    return `${x},${y}`
  }).join(' ')

  const lastY = PULSE_H - ((values[values.length - 1] - min) / range) * (PULSE_H - 4) - 2

  return (
    <svg
      width={PULSE_W} height={PULSE_H}
      viewBox={`0 0 ${PULSE_W} ${PULSE_H}`}
      role="img"
      aria-label={`${metricType} sparkline. Latest: ${latestValue} ${unit}, min: ${min.toFixed(1)}, max: ${max.toFixed(1)}`}
      className="sparkline"
    >
      <polyline
        fill="none"
        stroke="var(--spark-color, var(--dawn))"
        strokeWidth="1.5"
        points={pts}
        strokeLinejoin="round"
        strokeLinecap="round"
      />
      <circle cx={PULSE_W} cy={lastY} r="2.5" fill="var(--spark-color, var(--dawn))" />
    </svg>
  )
}

// ── Operations tab ────────────────────────────────────────────────────────────
function OperationsTab({ visible }: { visible: boolean }) {
  const [readings, setReadings] = useState<SensorReading[]>([])
  const [series, setSeries] = useState<PulseSeries[]>([])
  const [insights, setInsights] = useState<PulseInsight[]>([])
  const [secReport, setSecReport] = useState<SecurityReport | null>(null)
  const [loadingPulse, setLoadingPulse] = useState(true)
  const [loadingSec, setLoadingSec] = useState(true)
  const [runningCheck, setRunningCheck] = useState(false)
  const [expandedFindings, setExpandedFindings] = useState<Set<string>>(new Set())
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const { showToast } = useToast()
  const { confirm } = useConfirm()

  const fetchPulse = useCallback(async () => {
    try {
      const [r, s, ins] = await Promise.all([
        getCampusPulse(),
        getPulseSeries({ points: 20 }).catch(() => [] as PulseSeries[]),
        getPulseInsights().catch(() => [] as PulseInsight[]),
      ])
      setReadings(r)
      setSeries(s)
      setInsights(ins)
    } catch { /* silent */ }
    setLoadingPulse(false)
  }, [])

  const fetchSecurity = useCallback(async () => {
    try {
      const rep = await getSecurityReport()
      setSecReport(rep)
    } catch { /* silent */ }
    setLoadingSec(false)
  }, [])

  // Poll only while this tab is visible
  useEffect(() => {
    if (!visible) {
      if (intervalRef.current) { clearInterval(intervalRef.current); intervalRef.current = null }
      return
    }
    fetchPulse()
    fetchSecurity()
    intervalRef.current = setInterval(fetchPulse, 30_000)
    return () => { if (intervalRef.current) clearInterval(intervalRef.current) }
  }, [visible, fetchPulse, fetchSecurity])

  async function handleRunCheck() {
    setRunningCheck(true)
    try {
      const rep = await runSecurityCheck()
      setSecReport(rep)
      showToast('Security check complete', 'success')
    } catch (e) { showToast(String(e), 'error') }
    setRunningCheck(false)
  }

  async function handleEscalate(findingId: string, title: string) {
    const ok = await confirm(
      `Escalate "${title}" to IT?\n\nThis is a simulation. No notification will be sent.`,
      'Escalate (simulated)',
      'primary'
    )
    if (!ok) return
    try {
      await escalateFinding(findingId)
      showToast('Recorded locally. No notification was sent.', 'info')
    } catch (e) { showToast(String(e), 'error') }
  }

  const METRIC_SPARK_VARS: Record<string, string> = {
    temperature:      'var(--dawn)',
    air_quality:      'color-mix(in srgb, var(--dawn) 70%, var(--violet))',
    occupancy_count:  'var(--amber)',
    device_health:    'var(--violet)',
  }

  return (
    <div>
      {/* Simulation banner */}
      <div className="ops-banner" role="note">
        Simulation. Not connected to any SBU system. Nothing here sends messages or controls equipment.
      </div>

      {/* Building conditions */}
      <section aria-labelledby="ops-pulse-heading" className="ops-section">
        <h2 id="ops-pulse-heading">
          Building conditions <StatusChip variant="synthetic" label="Synthetic" />
        </h2>
        {loadingPulse
          ? <SkeletonList count={3} lines={2} />
          : (
            <div className="pulse-grid">
              {readings.map(r => {
                const seriesForSensor = series.find(
                  s => s.sensor_label === r.sensor_label && s.metric_type === r.metric_type
                )
                const values = seriesForSensor?.points.map(p => p.value) ?? [r.value]
                const insightForSensor = insights.filter(
                  i => i.sensor_label === r.sensor_label && i.metric_type === r.metric_type
                )
                const sparkColor = METRIC_SPARK_VARS[r.metric_type] ?? 'var(--dawn)'

                return (
                  <div key={r.id} className="pulse-card card">
                    <div className="pulse-card-top">
                      <Activity size={13} aria-hidden="true" />
                      <span className="text-sm font-medium">{r.metric_type.replace(/_/g, ' ')}</span>
                      <span className="pulse-value">{r.value} <span className="text-muted">{r.unit}</span></span>
                    </div>
                    <div
                      className="pulse-sparkline-wrap"
                      /* computed color — geometry var */
                      style={{ '--spark-color': sparkColor } as React.CSSProperties}
                    >
                      <Sparkline values={values} metricType={r.metric_type} latestValue={r.value} unit={r.unit} />
                    </div>
                    <div className="text-muted text-sm">{r.sensor_label}</div>
                    {insightForSensor.length > 0 && (
                      <ul className="pulse-insights">
                        {insightForSensor.map(ins => (
                          <li key={ins.id} className={`pulse-insight pulse-insight-${ins.severity}`}>
                            {ins.message}
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                )
              })}
            </div>
          )
        }
      </section>

      {/* Security watchdog */}
      <section aria-labelledby="ops-sec-heading" className="ops-section">
        <div className="ops-sec-header">
          <h2 id="ops-sec-heading">
            Security posture <StatusChip variant="demo" label="Demo" />
          </h2>
          <button
            className="btn btn-ghost btn-sm"
            onClick={handleRunCheck}
            disabled={runningCheck}
          >
            <RefreshCw size={13} className={runningCheck ? 'spin' : ''} aria-hidden="true" />
            {runningCheck ? 'Checking…' : 'Run check again'}
          </button>
        </div>

        {secReport && (
          <p className="text-muted text-sm ops-schedule-note">{secReport.schedule_note}</p>
        )}

        <p className="text-muted text-sm">Checked on this app's own configuration.</p>

        {loadingSec
          ? <SkeletonList count={2} lines={2} />
          : secReport
            ? (
              <>
                <div className="sec-summary">
                  <span className="sec-count sec-count-critical">{secReport.summary.critical} critical</span>
                  <span className="sec-count sec-count-warn">{secReport.summary.warn} warn</span>
                  <span className="sec-count sec-count-info">{secReport.summary.info} info</span>
                </div>
                <ul className="sec-findings">
                  {secReport.findings.map(f => (
                    <li key={f.id} className={`card sec-finding sec-finding-${f.severity}`}>
                      <details>
                        <summary
                          className="sec-finding-summary"
                          onClick={() => setExpandedFindings(prev => {
                            const next = new Set(prev)
                            next.has(f.id) ? next.delete(f.id) : next.add(f.id)
                            return next
                          })}
                        >
                          <span className={`badge badge-${f.severity === 'critical' ? 'err' : f.severity === 'warn' ? 'warn' : 'ok'}`}>
                            {f.severity}
                          </span>
                          <span className="sec-finding-title">{f.title}</span>
                        </summary>
                        <div className="sec-finding-body">
                          {f.evidence.length > 0 && (
                            <div>
                              <strong className="text-sm">Evidence:</strong>
                              <ul className="text-sm sec-evidence">
                                {f.evidence.map((e, i) => <li key={i}>{e}</li>)}
                              </ul>
                            </div>
                          )}
                          <p className="text-sm"><strong>Recommended action:</strong> {f.recommended_human_action}</p>
                          <button
                            className="btn btn-ghost btn-sm"
                            onClick={() => handleEscalate(f.id, f.title)}
                          >
                            Escalate to IT (simulated)
                          </button>
                        </div>
                      </details>
                    </li>
                  ))}
                </ul>
              </>
            )
            : <p className="text-muted">No security report available.</p>
        }
      </section>
    </div>
  )
}

// ── Main screen ───────────────────────────────────────────────────────────────
export default function CampusScreen() {
  const [searchParams, setSearchParams] = useSearchParams()
  const activeTab = searchParams.get('tab') ?? 'events'

  function onTabChange(id: string) {
    setSearchParams({ tab: id })
  }

  const [unreadCount, setUnreadCount] = useState(0)
  useEffect(() => {
    getAnnouncements().then(anns => {
      setUnreadCount(anns.filter(a => !a.is_read).length)
    }).catch(() => {})
  }, [activeTab])

  const tabItems = [
    { id: 'events',         label: 'Events' },
    { id: 'announcements',  label: <span className="campus-tab-label">Announcements {unreadCount > 0 && <span className="campus-tab-badge">{unreadCount}</span>}</span> },
    { id: 'operations',     label: 'Operations' },
  ]

  return (
    <div>
      <div className="screen-title">
        <h1>Campus</h1>
        <p>Events, announcements, and simulated campus operations.</p>
      </div>

      <Tabs items={tabItems} activeTab={activeTab} onTabChange={onTabChange} />

      <TabPanel id="events" activeTab={activeTab}>
        <EventsTab />
      </TabPanel>

      <TabPanel id="announcements" activeTab={activeTab}>
        <AnnouncementsTab />
      </TabPanel>

      <TabPanel id="operations" activeTab={activeTab}>
        <OperationsTab visible={activeTab === 'operations'} />
      </TabPanel>
    </div>
  )
}
