import { useEffect, useRef } from 'react'
import type { ReactNode } from 'react'
import { X } from 'lucide-react'
import './Sheet.css'

export interface SheetProps {
  open: boolean
  onClose: () => void
  title: string
  children: ReactNode
}

export function Sheet({ open, onClose, title, children }: SheetProps): JSX.Element | null {
  const firstFocusRef = useRef<HTMLButtonElement>(null)
  const backdropRef = useRef<HTMLDivElement>(null)

  // Focus trap: focus close button on open
  useEffect(() => {
    if (open) {
      setTimeout(() => firstFocusRef.current?.focus(), 50)
    }
  }, [open])

  // Close on Escape
  useEffect(() => {
    if (!open) return
    function handleKey(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', handleKey)
    return () => document.removeEventListener('keydown', handleKey)
  }, [open, onClose])

  // Prevent body scroll while open
  useEffect(() => {
    if (open) {
      document.body.style.overflow = 'hidden'
    } else {
      document.body.style.overflow = ''
    }
    return () => { document.body.style.overflow = '' }
  }, [open])

  if (!open) return null

  return (
    <div
      ref={backdropRef}
      className="sheet-backdrop"
      role="dialog"
      aria-modal="true"
      aria-label={title}
      onClick={e => { if (e.target === backdropRef.current) onClose() }}
    >
      <div className="sheet-box">
        <div className="sheet-header">
          <h3 className="sheet-title">{title}</h3>
          <button
            ref={firstFocusRef}
            className="btn btn-ghost btn-icon"
            onClick={onClose}
            aria-label="Close"
          >
            <X size={18} aria-hidden="true" />
          </button>
        </div>
        <div className="sheet-body">
          {children}
        </div>
      </div>
    </div>
  )
}
