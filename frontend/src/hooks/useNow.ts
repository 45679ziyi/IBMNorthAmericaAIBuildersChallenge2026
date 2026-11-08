/**
 * Returns the current virtual time (in scenario mode) or real time.
 * Polls GET /sim/state every 2s in scenario mode, every 30s in real mode.
 * Guaranteed to never return a Date constructed from Date.now() directly in screens.
 */
import { useState, useEffect, useRef } from 'react'
import { getSimState } from '../api/client'
import type { SimState } from '../api/client'

export function useNow(): { now: Date; simState: SimState | null } {
  const [simState, setSimState] = useState<SimState | null>(null)
  const [now, setNow] = useState<Date>(() => new Date())
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  function deriveNow(state: SimState | null): Date {
    if (state?.mode === 'scenario' && state.virtual_now) {
      return new Date(state.virtual_now)
    }
    return new Date()
  }

  useEffect(() => {
    let active = true

    async function poll() {
      try {
        const state = await getSimState()
        if (!active) return
        setSimState(state)
        setNow(deriveNow(state))

        // Reschedule at interval matching mode
        const intervalMs = state.mode === 'scenario' ? 2_000 : 30_000
        timerRef.current = setTimeout(poll, intervalMs)
      } catch {
        if (!active) return
        // On error fall back to real time, retry in 10s
        setNow(new Date())
        timerRef.current = setTimeout(poll, 10_000)
      }
    }

    poll()

    return () => {
      active = false
      if (timerRef.current !== null) clearTimeout(timerRef.current)
    }
  }, [])

  return { now, simState }
}
