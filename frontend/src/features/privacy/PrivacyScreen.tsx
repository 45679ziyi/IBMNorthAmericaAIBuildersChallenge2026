import { useEffect, useState } from 'react'
import './PrivacyScreen.css'
import { getConnectors, getCampusPulse, resetDemoData, deleteUserData, ConnectorStatus, SensorReading } from '../../api/client'

function fmtTime(iso: string) {
  return new Date(iso).toLocaleString('en-US', { timeZone: 'America/New_York', hour: 'numeric', minute: '2-digit' })
}

export default function PrivacyScreen() {
  const [connectors, setConnectors] = useState<ConnectorStatus[]>([])
  const [pulse, setPulse] = useState<SensorReading[]>([])
  const [loading, setLoading] = useState(true)
  const [resetMsg, setResetMsg] = useState<string | null>(null)
  const [deleteMsg, setDeleteMsg] = useState<string | null>(null)

  useEffect(() => {
    Promise.all([getConnectors(), getCampusPulse()])
      .then(([c, p]) => { setConnectors(c); setPulse(p); setLoading(false) })
      .catch(() => setLoading(false))
  }, [])

  async function handleReset() {
    if (!confirm('Reset all demo data to initial state?')) return
    const r = await resetDemoData().catch(e => ({ status: 'error', message: String(e) }))
    setResetMsg(r.message)
  }

  async function handleDelete() {
    if (!confirm('Delete all local prototype data? This cannot be undone.')) return
    const r = await deleteUserData().catch(e => ({ status: 'error', message: String(e) }))
    setDeleteMsg(r.message)
  }

  return (
    <div>
      <div className="screen-title">
        <h1>Privacy &amp; Sources</h1>
        <p>See how AURORA uses data, what is stored, and what leaves this device.</p>
      </div>

      {/* Data policy summary */}
      <div className="card mb-2" style={{ borderColor: '#86efac', background: '#f0fdf4' }}>
        <h3>AURORA Prototype Data Policy</h3>
        <ul className="text-sm">
          <li>All demo academic records are <strong>synthetic fiction</strong>. No real student data is used.</li>
          <li>No NetID, Stony Brook ID, SSN, real grades, or private messages are collected.</li>
          <li>No connection to SBU SOLAR, Brightspace, campus networks, or real sensors is made.</li>
          <li>Calendar data you import stays in your local browser session and the local SQLite database.</li>
          <li>If an external AI provider is enabled via <code>AI_PROVIDER</code>, your assistant questions may be sent to that provider. Check the connector table below.</li>
          <li>This prototype does not claim FERPA compliance, end-to-end encryption, or SBU approval.</li>
        </ul>
      </div>

      {/* Connector status table */}
      <section aria-labelledby="sources-heading">
        <h2 id="sources-heading">Connected Sources</h2>
        {loading
          ? <div className="state-loading">Loading…</div>
          : <div className="sources-table-wrap">
              <table className="sources-table" aria-label="Data sources">
                <thead>
                  <tr>
                    <th scope="col">Source</th>
                    <th scope="col">Status</th>
                    <th scope="col">Data categories</th>
                    <th scope="col">Purpose</th>
                    <th scope="col">Sends to external AI?</th>
                    <th scope="col">Last checked</th>
                  </tr>
                </thead>
                <tbody>
                  {connectors.map(c => (
                    <tr key={c.name}>
                      <td><strong>{c.name}</strong></td>
                      <td>
                        <span className={`badge badge-${c.status === 'connected' ? 'ok' : c.status === 'demo' ? 'demo' : 'warn'}`}>
                          {c.status}
                        </span>
                      </td>
                      <td className="text-sm text-muted">{c.data_categories.join(', ')}</td>
                      <td className="text-sm">{c.purpose}</td>
                      <td className="text-sm">{c.sends_to_external_model ? <span style={{ color: 'var(--warning)' }}>Yes</span> : 'No'}</td>
                      <td className="text-sm text-muted">{fmtTime(c.last_checked)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
        }
      </section>

      {/* Campus Pulse */}
      <section aria-labelledby="pulse-sec-heading" className="mt-2">
        <h2 id="pulse-sec-heading">Campus Pulse — Synthetic Data Only</h2>
        <div className="card" style={{ borderColor: '#c4b5fd', background: '#faf5ff' }}>
          <p className="text-sm" style={{ fontWeight: 700, color: 'var(--synth-badge)' }}>
            SIMULATED DATA — NOT CONNECTED TO SBU SYSTEMS
          </p>
          <p className="text-sm">
            These readings are generated locally in real time and represent no real building, sensor, or infrastructure.
            No campus network access, device scanning, or SNMP/SSH is used.
          </p>
          {pulse.length > 0 && (
            <ul className="pulse-list">
              {pulse.map(r => (
                <li key={r.id} className="pulse-row">
                  <span className="text-sm">{r.sensor_label}</span>
                  <span className="badge badge-synth">{r.data_origin}</span>
                  <span className="text-sm"><strong>{r.value} {r.unit}</strong> — {r.metric_type}</span>
                  <span className="text-muted text-sm">{fmtTime(r.recorded_at_utc)}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </section>

      {/* Data controls */}
      <section aria-labelledby="data-ctrl-heading" className="mt-2">
        <h2 id="data-ctrl-heading">Data Controls</h2>
        <div className="card">
          <div className="data-controls">
            <div>
              <button className="btn btn-ghost" onClick={handleReset}>🔄 Reset Demo Data</button>
              <p className="text-muted text-sm">Restores all synthetic demo records to their initial state.</p>
              {resetMsg && <p className="text-sm" style={{ color: 'var(--success)' }}>{resetMsg}</p>}
            </div>
            <div>
              <button className="btn btn-danger" onClick={handleDelete}>🗑 Delete All Local Data</button>
              <p className="text-muted text-sm">Removes all locally stored events, tasks, plans, and announcements. Cannot be undone.</p>
              {deleteMsg && <p className="text-sm" style={{ color: 'var(--success)' }}>{deleteMsg}</p>}
            </div>
          </div>
        </div>
      </section>
    </div>
  )
}
