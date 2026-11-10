/**
 * PersonaSwitcher — U1 component.
 *
 * Shows the current actor's name with a "DEMO PERSONA, NOT AUTHENTICATION"
 * chip and a dropdown to switch personas.
 */
import { useState, useRef, useEffect } from 'react'
import { ChevronDown, User } from 'lucide-react'
import type { PersonaInfo } from '../api/client'
import './PersonaSwitcher.css'

interface Props {
  personas: PersonaInfo[]
  currentActor: string
  onSwitch: (id: string) => void
}

const ROLE_LABELS: Record<string, string> = {
  student:       'Student',
  faculty:       'Faculty',
  facilities:    'Facilities',
  it:            'IT',
  academic_ops:  'Academic Ops',
  org_organizer: 'Org',
}

export function PersonaSwitcher({ personas, currentActor, onSwitch }: Props) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  const current = personas.find(p => p.id === currentActor)
  const displayName = current?.display_name ?? currentActor

  // Close on outside click
  useEffect(() => {
    if (!open) return
    function handler(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [open])

  // Group personas by role
  const byRole = personas.reduce<Record<string, PersonaInfo[]>>((acc, p) => {
    (acc[p.role] = acc[p.role] || []).push(p)
    return acc
  }, {})

  return (
    <div className="persona-switcher" ref={ref}>
      <button
        className="persona-btn"
        onClick={() => setOpen(o => !o)}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={`Current persona: ${displayName}. Click to switch.`}
      >
        <User size={13} aria-hidden="true" />
        <span className="persona-name">{displayName}</span>
        <ChevronDown size={11} aria-hidden="true" className={open ? 'chevron-open' : ''} />
      </button>

      {open && (
        <div className="persona-dropdown" role="listbox" aria-label="Switch persona">
          {/* NOT AUTHENTICATION disclaimer */}
          <div className="persona-disclaimer" aria-live="polite">
            DEMO PERSONA, NOT AUTHENTICATION
          </div>

          {Object.entries(byRole).map(([role, list]) => (
            <div key={role} className="persona-group">
              <div className="persona-group-label">{ROLE_LABELS[role] ?? role}</div>
              {list.map(p => (
                <button
                  key={p.id}
                  role="option"
                  aria-selected={p.id === currentActor}
                  className={`persona-option${p.id === currentActor ? ' persona-option-active' : ''}`}
                  onClick={() => { onSwitch(p.id); setOpen(false) }}
                >
                  {p.display_name}
                </button>
              ))}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
