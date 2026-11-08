import { useState, useEffect, useRef, useCallback } from 'react'
import { RotateCcw, Play, Pause, SkipForward, Users } from 'lucide-react'
import { advanceSim, resetSim } from '../api/client'
import type { SimState } from '../api/client'
import { CAMPUS_TZ } from '../lib/time'
import './DemoBar.css'

type SpeedOption = { label: string; intervalMs: number }
const SPEED_OPTIONS: SpeedOption[] = [
  { label: '60×',  intervalMs: 1000 },
  { label: '300×', intervalMs: 200  },
  { label: '600×', intervalMs: 100  },
]

export interface DemoBarProps {
  simState: SimState
  onAdvance: () => void
  onReset: () => void
  onStop: () => void
  onStaffView: () => void
}

function formatVirtualTime(iso: string): string {
  const d = new Date(iso)
  return d.toLocaleString('en-US', {
    hour: 'numeric',
    minute: '2-digit',
    hour12: true,
    weekday: 'short',
    month: 'short',
    day: 'numeric',
    timeZone: CAMPUS_TZ,
  })
}

export function DemoBar({ simState, onAdvance, onReset, onStop: _onStop, onStaffView }: DemoBarProps) {
  const [playing, setPlaying] = useState(false)
  const [speedIdx, setSpeedIdx] = useState(0)
  const [speedOpen, setSpeedOpen] = useState(false)
  const speedRef = useRef<HTMLDivElement>(null)
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const currentSpeed = SPEED_OPTIONS[speedIdx]

  // Auto-advance loop
  const tick = useCallback(async () => {
    try {
      await advanceSim({ minutes: 1 })
      onAdvance()
    } catch {
      // Silently skip on error
    }
  }, [onAdvance])

  useEffect(() => {
    if (playing) {
      intervalRef.current = setInterval(tick, currentSpeed.intervalMs)
    } else {
      if (intervalRef.current !== null) {
        clearInterval(intervalRef.current)
        intervalRef.current = null
      }
    }
    return () => {
      if (intervalRef.current !== null) {
        clearInterval(intervalRef.current)
        intervalRef.current = null
      }
    }
  }, [playing, currentSpeed.intervalMs, tick])

  // Close speed dropdown on outside click
  useEffect(() => {
    if (!speedOpen) return
    function close(e: MouseEvent) {
      if (speedRef.current && !speedRef.current.contains(e.target as Node)) {
        setSpeedOpen(false)
      }
    }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [speedOpen])

  async function handleReset() {
    setPlaying(false)
    try {
      await resetSim()
      onReset()
    } catch { /* ignore */ }
  }

  async function handleNextSignal() {
    setPlaying(false)
    try {
      await advanceSim({ to_next_signal: true })
      onAdvance()
    } catch { /* ignore */ }
  }

  const virtualTime = simState.virtual_now ? formatVirtualTime(simState.virtual_now) : '–'

  return (
    <div className="demo-bar" role="status" aria-label="Simulation bar">
      <span className="demo-bar-label">Simulation</span>
      <span className="demo-bar-time" aria-label={`Virtual time: ${virtualTime}`}>{virtualTime}</span>

      <div className="demo-bar-actions">
        <button
          className="btn btn-ghost btn-sm demo-bar-btn"
          onClick={handleReset}
          title="Reset simulation"
          aria-label="Reset simulation"
        >
          <RotateCcw size={13} aria-hidden="true" /> Reset
        </button>

        <button
          className="btn btn-ghost btn-sm demo-bar-btn demo-bar-play"
          onClick={() => setPlaying(p => !p)}
          title={playing ? 'Pause auto-advance' : 'Play auto-advance'}
          aria-label={playing ? 'Pause' : 'Play'}
          aria-pressed={playing}
        >
          {playing
            ? <><Pause size={13} aria-hidden="true" /> Pause</>
            : <><Play  size={13} aria-hidden="true" /> Play</>
          }
        </button>

        <div className="demo-bar-speed-wrap" ref={speedRef}>
          <button
            className="btn btn-ghost btn-sm demo-bar-btn"
            onClick={() => setSpeedOpen(o => !o)}
            aria-haspopup="listbox"
            aria-expanded={speedOpen}
            title="Change speed"
          >
            {currentSpeed.label} ▾
          </button>
          {speedOpen && (
            <ul className="demo-bar-speed-menu" role="listbox" aria-label="Speed">
              {SPEED_OPTIONS.map((opt, i) => (
                <li
                  key={opt.label}
                  role="option"
                  aria-selected={i === speedIdx}
                  className={`demo-bar-speed-item${i === speedIdx ? ' demo-bar-speed-item-active' : ''}`}
                  onClick={() => { setSpeedIdx(i); setSpeedOpen(false) }}
                >
                  {opt.label}
                </li>
              ))}
            </ul>
          )}
        </div>

        <button
          className="btn btn-ghost btn-sm demo-bar-btn"
          onClick={handleNextSignal}
          title="Jump to next signal"
          aria-label="Jump to next signal"
        >
          <SkipForward size={13} aria-hidden="true" /> Next signal
        </button>

        <button
          className="btn btn-ghost btn-sm demo-bar-btn"
          onClick={onStaffView}
          title="Staff operations view"
          aria-label="Staff view"
        >
          <Users size={13} aria-hidden="true" /> Staff view
        </button>
      </div>
    </div>
  )
}
