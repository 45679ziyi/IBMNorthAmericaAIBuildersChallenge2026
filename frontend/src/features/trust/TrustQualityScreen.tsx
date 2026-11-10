import { useState, useEffect } from 'react'
import { getTrustQuality, type TrustQuality } from '../../api/client'
import { LoadingState } from '../../components/states/LoadingState'
import { ErrorState } from '../../components/states/ErrorState'
import '../../components/states/states.css'
import './TrustQualityScreen.css'

type SuiteStatus = 'pass' | 'warn' | 'fail' | 'not_run'

interface SuiteRow {
  name: string
  status: SuiteStatus
  metric: string
  value: string
}

function statusBadge(s: SuiteStatus) {
  const map: Record<SuiteStatus, string> = {
    pass: 'tq-badge-pass',
    warn: 'tq-badge-warn',
    fail: 'tq-badge-fail',
    not_run: 'tq-badge-notrun',
  }
  const labels: Record<SuiteStatus, string> = {
    pass: 'Pass', warn: 'Warn', fail: 'Fail', not_run: 'Not run',
  }
  return <span className={`tq-badge ${map[s]}`}>{labels[s]}</span>
}

function parseSuites(data: TrustQuality): SuiteRow[] {
  const rows: SuiteRow[] = []

  // Authorization
  const auth = data.authorization as Record<string, unknown>
  if ('pass_rate' in auth && auth.pass_rate !== null) {
    const rate = Number(auth.pass_rate)
    rows.push({
      name: 'Authorization',
      status: rate >= 1.0 ? 'pass' : rate >= 0.95 ? 'warn' : 'fail',
      metric: 'Pass rate',
      value: `${(rate * 100).toFixed(1)}% (${auth.cases} cases)`,
    })
  } else {
    rows.push({ name: 'Authorization', status: 'not_run', metric: '—', value: 'Not run' })
  }

  // Deadline extraction
  const dl = data.deadline_extraction as Record<string, unknown>
  if ('exact_match' in dl && dl.exact_match !== null) {
    const em = Number(dl.exact_match)
    rows.push({
      name: 'Deadline Extraction',
      status: em >= 0.90 ? 'pass' : em >= 0.80 ? 'warn' : 'fail',
      metric: 'Exact match',
      value: `${(em * 100).toFixed(1)}% (${dl.cases} cases)`,
    })
  } else {
    rows.push({ name: 'Deadline Extraction', status: 'not_run', metric: '—', value: 'Not run' })
  }

  // Retrieval
  const ret = data.retrieval as Record<string, unknown>
  if ('coverage_accuracy' in ret && ret.coverage_accuracy !== null) {
    const ca = Number(ret.coverage_accuracy)
    rows.push({
      name: 'Retrieval',
      status: ca >= 0.90 ? 'pass' : ca >= 0.80 ? 'warn' : 'fail',
      metric: 'Coverage accuracy',
      value: `${(ca * 100).toFixed(1)}% (${ret.cases} cases)`,
    })
  } else {
    rows.push({ name: 'Retrieval', status: 'not_run', metric: '—', value: 'Not run' })
  }

  // Injection
  const inj = data.injection as Record<string, unknown>
  if ('successful_injections' in inj && inj.successful_injections !== null) {
    const si = Number(inj.successful_injections)
    rows.push({
      name: 'Injection',
      status: si === 0 ? 'pass' : si <= 2 ? 'warn' : 'fail',
      metric: 'Successful injections',
      value: `${si} / ${inj.cases} cases`,
    })
  } else {
    rows.push({ name: 'Injection', status: 'not_run', metric: '—', value: 'Not run' })
  }

  // Tenant leakage
  const tl = data.tenant_leakage as Record<string, unknown>
  if ('leaks' in tl && tl.leaks !== null) {
    const leaks = Number(tl.leaks)
    rows.push({
      name: 'Tenant Leakage',
      status: leaks === 0 ? 'pass' : 'fail',
      metric: 'Leaks',
      value: `${leaks} / ${tl.probes} probes`,
    })
  } else {
    rows.push({ name: 'Tenant Leakage', status: 'not_run', metric: '—', value: 'Not run' })
  }

  // Determinism
  const det = data.determinism as Record<string, unknown>
  if ('identical_hashes' in det && det.identical_hashes !== null) {
    rows.push({
      name: 'Determinism',
      status: det.identical_hashes ? 'pass' : 'fail',
      metric: 'Identical hashes',
      value: det.identical_hashes ? `Yes (${det.tenants} tenants)` : 'No',
    })
  } else {
    rows.push({ name: 'Determinism', status: 'not_run', metric: '—', value: 'Not run' })
  }

  return rows
}

export default function TrustQualityScreen() {
  const [data, setData] = useState<TrustQuality | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getTrustQuality()
      .then(setData)
      .catch(e => setError(String(e)))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <LoadingState message="Loading quality metrics…" />
  if (error || !data) return <ErrorState message={error ?? 'Failed to load metrics'} />

  const rows = parseSuites(data)
  const allPass = rows.every(r => r.status === 'pass' || r.status === 'not_run')

  return (
    <div className="tq-screen">
      <div className="screen-title">
        <h1>Trust &amp; Quality</h1>
        <p>Automated evaluation results for AI and authorization correctness.</p>
      </div>

      <div className="tq-provider-row">
        <span className="tq-provider-label">AI provider:</span>
        <span className="tq-provider-value">{data.ai_provider}</span>
        {data.watsonx_configured ? (
          <span className="tq-badge tq-badge-pass">watsonx configured</span>
        ) : (
          <span className="tq-badge tq-badge-notrun">mock only</span>
        )}
      </div>

      <div className="tq-overall">
        <span className={`tq-overall-badge ${allPass ? 'tq-badge-pass' : 'tq-badge-warn'}`}>
          {allPass ? '✓ All suites pass' : 'Some suites need attention'}
        </span>
        <span className="tq-run-hint">Run: <code>python -m evals.run --all</code> to refresh</span>
      </div>

      <table className="tq-table">
        <thead>
          <tr>
            <th>Suite</th>
            <th>Status</th>
            <th>Metric</th>
            <th>Result</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(row => (
            <tr key={row.name} className={`tq-row tq-row-${row.status}`}>
              <td className="tq-name">{row.name}</td>
              <td>{statusBadge(row.status)}</td>
              <td className="tq-metric">{row.metric}</td>
              <td className="tq-value">{row.value}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <div className="tq-note">
        <p>
          <strong>IBM Bob</strong> was used as the primary development assistant for this project.
          All AI outputs pass through the verifier (<code>services/ai/verifier.py</code>) before
          being shown to users. Rule-based fallbacks are used by default; watsonx.ai can be
          optionally configured via environment variables.
        </p>
      </div>
    </div>
  )
}
