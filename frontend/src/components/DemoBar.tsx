import { useState, useEffect, useRef, useCallback } from 'react'
import { RotateCcw, Play, Pause, SkipForward, Users, ChevronDown, ChevronUp } from 'lucide-react'
import { advanceSim, resetSim, setDirectorMode, simTakeOver, getDirectorState } from '../api/client'
import type { SimState } from '../api/client'
import { getTz } from '../lib/time'
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
    timeZone: getTz(),
  })
}

export function DemoBar({ simState, onAdvance, onReset, onStop: _onStop, onStaffView }: DemoBarProps) {
  const [playing, setPlaying] = useState(false)
  const [speedIdx, setSpeedIdx] = useState(0)
  const [speedOpen, setSpeedOpen] = useState(false)
  const [directorOpen, setDirectorOpen] = useState(false)
  const [directorMode, setDirMode] = useState(false)
  const [pendingSteps, setPendingSteps] = useState<string[]>([])
  const [takingOver, setTakingOver] = useState(false)
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

  // Load director state
  useEffect(() => {
    getDirectorState()
      .then(s => { setDirMode(s.director_mode === 'autopilot'); setPendingSteps(s.pending_step_ids ?? []) })
      .catch(() => {})
  }, [simState])

  async function handleToggleDirector() {
    const newMode = !directorMode
    try {
      const s = await setDirectorMode(newMode)
      setDirMode(s.director_mode === 'autopilot'); setPendingSteps(s.pending_step_ids ?? [])
    } catch { /* ignore */ }
  }

  async function handleTakeOver() {
    setTakingOver(true)
    try {
      const s = await simTakeOver()
      setDirMode(s.director_mode === 'autopilot'); setPendingSteps(s.pending_step_ids ?? [])
      onAdvance()
    } catch { /* ignore */ } finally { setTakingOver(false) }
  }

  const virtualTime = simState.virtual_now ? formatVirtualTime(simState.virtual_now) : '–'

  return (
    <div className="demo-bar" role="status" aria-label="Simulation bar">
      <span className="demo-bar-label">SIMULATION</span>
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

        {/* Director toggle */}
        <button
          className="btn btn-ghost btn-sm demo-bar-btn"
          onClick={() => setDirectorOpen(o => !o)}
          aria-expanded={directorOpen}
          aria-label="Director panel"
        >
          Director {directorOpen ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
        </button>
      </div>

      {/* Director panel */}
      {directorOpen && (
        <div className="demo-bar-director">
          <label className="demo-bar-director-toggle">
            <input
              type="checkbox"
              checked={directorMode}
              onChange={handleToggleDirector}
              aria-label="Autopilot"
            />
            <span>Autopilot {directorMode ? 'ON' : 'OFF'}</span>
          </label>

          <button
            className="btn btn-primary btn-sm"
            disabled={takingOver}
            onClick={handleTakeOver}
            title="Take over as Morgan (Facilities)"
          >
            {takingOver ? 'Switching…' : 'Take over as Morgan'}
          </button>

          {pendingSteps.length > 0 && (
            <div className="demo-bar-steps">
              <span className="demo-bar-steps-label">Pending steps ({pendingSteps.length})</span>
              <ul className="demo-bar-steps-list">
                {pendingSteps.slice(0, 5).map(id => (
                  <li key={id} className="demo-bar-step-item">{id}</li>
                ))}
                {pendingSteps.length > 5 && (
                  <li className="demo-bar-step-item demo-bar-step-more">+{pendingSteps.length - 5} more</li>
                )}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
