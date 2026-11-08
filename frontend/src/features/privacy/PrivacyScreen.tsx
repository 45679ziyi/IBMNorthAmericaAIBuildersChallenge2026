import { useEffect, useState } from 'react'
import './PrivacyScreen.css'
import { getConnectors, resetDemoData, deleteUserData, ConnectorStatus } from '../../api/client'
import { Sheet } from '../../components/Sheet'
import { StatusChip } from '../../components/StatusChip'
import { useToast } from '../../components/Toast'

export default function PrivacyScreen() {
  const [connectors, setConnectors] = useState<ConnectorStatus[]>([])
  const [loading, setLoading] = useState(true)
  const [resetSheetOpen, setResetSheetOpen] = useState(false)
  const [deleteSheetOpen, setDeleteSheetOpen] = useState(false)
  const { showToast } = useToast()

  useEffect(() => {
    getConnectors()
      .then(c => { setConnectors(c); setLoading(false) })
      .catch(() => setLoading(false))
  }, [])

  async function handleReset() {
    setResetSheetOpen(false)
    const r = await resetDemoData().catch(e => ({ status: 'error', message: String(e) }))
    showToast(r.message, r.status === 'error' ? 'error' : 'success')
  }

  async function handleDelete() {
    setDeleteSheetOpen(false)
    const r = await deleteUserData().catch(e => ({ status: 'error', message: String(e) }))
    showToast(r.message, r.status === 'error' ? 'error' : 'success')
  }

  function connectorChipVariant(status: ConnectorStatus['status']): 'live' | 'demo' | 'warn' {
    if (status === 'connected') return 'live'
    if (status === 'demo') return 'demo'
    return 'warn'
  }

  return (
    <div className="privacy-screen">
      <div className="screen-title">
        <h1>Privacy &amp; Sources</h1>
        <p>See how AURORA uses data, what is stored, and what leaves this device.</p>
      </div>

      {/* 1 — What stays on this device */}
      <section aria-labelledby="priv-local-heading" className="priv-section">
        <h2 id="priv-local-heading">What stays on this device</h2>
        <div className="card">
          <ul className="priv-list">
            <li>Tasks you create or import</li>
            <li>Calendar events you import via .ics</li>
            <li>Daily plans generated in this session</li>
            <li>Chat history (in-memory, cleared on page reload)</li>
          </ul>
        </div>
      </section>

      {/* 2 — What can leave this device */}
      <section aria-labelledby="priv-external-heading" className="priv-section">
        <h2 id="priv-external-heading">What can leave this device</h2>
        <div className="card">
          <p className="text-sm">
            Only if a live AI provider is configured via <code>AI_PROVIDER</code>: your assistant
            questions may be sent to that external provider. Check the connector table below.
            By default, no data leaves this device.
          </p>
          <p className="text-sm text-muted">
            The connector table below shows which sources send data externally.
          </p>
        </div>
      </section>

      {/* 3 — Sources */}
      <section aria-labelledby="priv-sources-heading" className="priv-section">
        <h2 id="priv-sources-heading">Sources</h2>
        {loading
          ? <div className="state-loading">Loading…</div>
          : (
            <div className="sources-table-wrap" tabIndex={0} role="region" aria-label="Data sources table">
              <table className="sources-table" aria-label="Data sources">
                <thead>
                  <tr>
                    <th scope="col">Source</th>
                    <th scope="col">Status</th>
                    <th scope="col">Data categories</th>
                    <th scope="col">Sends externally?</th>
                  </tr>
                </thead>
                <tbody>
                  {connectors.map(c => (
                    <tr key={c.name}>
                      <td><strong>{c.name}</strong></td>
                      <td>
                        <StatusChip variant={connectorChipVariant(c.status)} label={c.status} />
                      </td>
                      <td className="text-sm text-muted">{c.data_categories.join(', ')}</td>
                      <td className="text-sm">
                        {c.sends_to_external_model
                          ? <span className="priv-external-yes">Yes</span>
                          : 'No'
                        }
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )
        }
      </section>

      {/* 4 — What AURORA does not claim */}
      <section aria-labelledby="priv-claims-heading" className="priv-section">
        <h2 id="priv-claims-heading">What AURORA does not claim</h2>
        <div className="card">
          <ul className="priv-list">
            <li>FERPA compliance — this is an independent prototype, not an official SBU system</li>
            <li>End-to-end encryption of stored data</li>
            <li>Endorsement by Stony Brook University or IBM</li>
            <li>Readiness for production or sensitive data use</li>
          </ul>
        </div>
      </section>

      {/* 5 — Where this could go (future only) */}
      <section aria-labelledby="priv-future-heading" className="priv-section">
        <h2 id="priv-future-heading">
          Where this could go
          <span className="priv-future-badge">Future only, not implemented</span>
        </h2>
        <div className="card priv-future-card">
          <ul className="priv-list">
            <li>Live connection to SBU SOLAR calendar (requires authorized OAuth)</li>
            <li>Live SBU Brightspace announcements (requires institution integration)</li>
            <li>Real building sensor telemetry (requires campus infrastructure access)</li>
            <li>Encrypted sync across devices (requires backend auth and storage)</li>
          </ul>
        </div>
      </section>

      {/* Data controls */}
      <section aria-labelledby="priv-controls-heading" className="priv-section priv-controls-section">
        <h2 id="priv-controls-heading">Data controls</h2>
        <div className="priv-controls">
          <div className="priv-control-item card">
            <div>
              <h3 className="priv-control-title">Reset demo data</h3>
              <p className="text-muted text-sm">Restores all synthetic demo records to their initial state.</p>
            </div>
            <button
              className="btn btn-ghost btn-sm"
              onClick={() => setResetSheetOpen(true)}
            >
              Reset demo data
            </button>
          </div>

          <div className="priv-control-item card">
            <div>
              <h3 className="priv-control-title">Delete all local data</h3>
              <p className="text-muted text-sm">Removes all locally stored events, tasks, plans, and announcements. Cannot be undone.</p>
            </div>
            <button
              className="btn btn-danger btn-sm"
              onClick={() => setDeleteSheetOpen(true)}
            >
              Delete all data
            </button>
          </div>
        </div>
      </section>

      {/* Reset sheet */}
      <Sheet
        open={resetSheetOpen}
        onClose={() => setResetSheetOpen(false)}
        title="Reset demo data"
      >
        <p>This will restore all synthetic demo records — events, tasks, announcements, and sensor readings — to their initial state.</p>
        <p>Your custom tasks and imported calendar events will be removed.</p>
        <div className="flex gap-1 mt-2">
          <button className="btn btn-primary btn-sm" onClick={handleReset}>Reset now</button>
          <button className="btn btn-ghost btn-sm" onClick={() => setResetSheetOpen(false)}>Cancel</button>
        </div>
      </Sheet>

      {/* Delete sheet */}
      <Sheet
        open={deleteSheetOpen}
        onClose={() => setDeleteSheetOpen(false)}
        title="Delete all local data"
      >
        <p>This will permanently delete everything stored in the local database:</p>
        <ul>
          <li>All calendar events (including imported ones)</li>
          <li>All tasks</li>
          <li>All daily plans</li>
          <li>All announcements</li>
        </ul>
        <p>This cannot be undone.</p>
        <div className="flex gap-1 mt-2">
          <button className="btn btn-danger btn-sm" onClick={handleDelete}>Delete everything</button>
          <button className="btn btn-ghost btn-sm" onClick={() => setDeleteSheetOpen(false)}>Cancel</button>
        </div>
      </Sheet>
    </div>
  )
}
