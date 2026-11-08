import { useEffect, useState } from 'react'
import { Sheet } from '../../components/Sheet'
import { useToast } from '../../components/Toast'
import { getAutonomy, updateAutonomy } from '../../api/client'
import type { AutonomyPolicy } from '../../api/client'

// ── Policy display labels ─────────────────────────────────────────────────────
const CATEGORY_LABELS: Record<string, string> = {
  calendar_tasks:         'Calendar, tasks & reminders',
  plan_changes:           'Plan changes I chose',
  external_requests:      'Simulated external requests',
  message_drafts:         'Message drafts',
}

const SETTING_LABELS: Record<string, string> = {
  auto: 'Auto',
  ask:  'Ask me',
}

// ── AutonomySheet ─────────────────────────────────────────────────────────────
export function AutonomySheet({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [autonomy, setAutonomy] = useState<AutonomyPolicy | null>(null)
  const [saving, setSaving] = useState<string | null>(null)
  const { showToast } = useToast()

  useEffect(() => {
    if (!open) return
    getAutonomy()
      .then(setAutonomy)
      .catch(e => showToast(`Could not load autonomy settings: ${String(e)}`, 'error'))
  }, [open]) // eslint-disable-line react-hooks/exhaustive-deps

  async function handleToggle(category: string, current: string) {
    const next = current === 'auto' ? 'ask' : 'auto'
    setSaving(category)
    try {
      const updated = await updateAutonomy(category, next)
      setAutonomy(updated)
      showToast('Autonomy setting saved', 'success')
    } catch (e) {
      showToast(String(e), 'error')
    }
    setSaving(null)
  }

  const categories = autonomy ? Object.keys(autonomy.policy) : Object.keys(CATEGORY_LABELS)

  return (
    <Sheet open={open} onClose={onClose} title="Autonomy settings">
      <p className="autonomy-intro text-muted text-sm">
        Control what AURORA can do on your behalf without asking first.
      </p>

      {!autonomy ? (
        <p className="text-muted">Loading…</p>
      ) : (
        <table className="autonomy-table">
          <thead>
            <tr>
              <th>Category</th>
              <th>Current setting</th>
              <th>Locked?</th>
            </tr>
          </thead>
          <tbody>
            {categories.map(cat => {
              const setting = autonomy.policy[cat] ?? 'ask'
              const locked  = autonomy.locked.includes(cat)
              const label   = CATEGORY_LABELS[cat] ?? cat.replace(/_/g, ' ')
              return (
                <tr key={cat} className="autonomy-row">
                  <td className="autonomy-cat-label">{label}</td>
                  <td>
                    {locked ? (
                      <span className="badge badge-warn">{SETTING_LABELS[setting] ?? setting}</span>
                    ) : (
                      <button
                        className={`autonomy-toggle ${setting === 'auto' ? 'autonomy-toggle-auto' : 'autonomy-toggle-ask'}`}
                        onClick={() => handleToggle(cat, setting)}
                        disabled={saving === cat}
                        aria-label={`Toggle ${label}: currently ${setting}`}
                      >
                        {saving === cat ? '…' : (SETTING_LABELS[setting] ?? setting)}
                      </button>
                    )}
                  </td>
                  <td>
                    {locked ? (
                      <span className="autonomy-locked-note text-sm text-muted">
                        Cannot change — external or messaging actions always need your approval.
                      </span>
                    ) : (
                      <span className="text-muted text-sm">No</span>
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      )}

      {autonomy?.note && (
        <p className="autonomy-note text-sm text-muted">{autonomy.note}</p>
      )}
    </Sheet>
  )
}
