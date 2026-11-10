/**
 * useTenantConfig — fetches GET /tenant/config and updates the time library.
 *
 * Call this hook once near the top of the app.  It applies setTz/setClock
 * from lib/time so all downstream time formatting uses the correct timezone.
 */
import { useEffect, useState } from 'react'
import { getTenantConfig, type TenantConfig } from '../api/client'
import { setTz, setClock } from '../lib/time'

export function useTenantConfig(): { config: TenantConfig | null; loading: boolean } {
  const [config, setConfig] = useState<TenantConfig | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    getTenantConfig()
      .then(cfg => {
        if (cancelled) return
        setTz(cfg.time_zone)
        setClock(cfg.clock as '12h' | '24h')
        setConfig(cfg)
      })
      .catch(() => {
        // Non-fatal: fall back to defaults already set in lib/time
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => { cancelled = true }
  }, [])

  return { config, loading }
}
