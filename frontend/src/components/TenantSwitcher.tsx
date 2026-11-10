/**
 * TenantSwitcher — lists active tenants and lets the user switch.
 *
 * Clicking a different tenant:
 *   1. Updates the X-Demo-Tenant header (via setDemoTenant)
 *   2. Reloads the page so all caches clear and config re-fetches
 */
import { useState, useEffect, useRef } from 'react'
import { Building2 } from 'lucide-react'
import { listTenants, setDemoTenant, getDemoTenant, type TenantSummary } from '../api/client'
import './TenantSwitcher.css'

export function TenantSwitcher() {
  const [tenants, setTenants] = useState<TenantSummary[]>([])
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  const current = getDemoTenant()

  useEffect(() => {
    listTenants()
      .then(setTenants)
      .catch(() => { /* not fatal — switcher stays hidden */ })
  }, [])

  // Close dropdown on outside click
  useEffect(() => {
    if (!open) return
    function close(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [open])

  if (tenants.length <= 1) return null

  const currentTenant = tenants.find(t => t.id === current) ?? tenants[0]

  function switchTo(id: string) {
    setDemoTenant(id)
    setOpen(false)
    // Reload to flush all caches
    window.location.reload()
  }

  return (
    <div className="tenant-switcher" ref={ref}>
      <button
        className="btn btn-ghost btn-sm tenant-switcher-btn"
        onClick={() => setOpen(o => !o)}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={`Current tenant: ${currentTenant?.name ?? current}`}
        title="Switch tenant"
      >
        <Building2 size={14} aria-hidden="true" />
        <span className="tenant-switcher-label">{currentTenant?.name ?? current}</span>
        <span aria-hidden="true">▾</span>
      </button>

      {open && (
        <ul className="tenant-switcher-menu" role="listbox" aria-label="Select tenant">
          {tenants.map(t => (
            <li
              key={t.id}
              role="option"
              aria-selected={t.id === current}
              className={`tenant-switcher-item${t.id === current ? ' tenant-switcher-item-active' : ''}`}
              onClick={() => switchTo(t.id)}
            >
              {t.name}
              {t.is_default && <span className="tenant-switcher-default"> (default)</span>}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
