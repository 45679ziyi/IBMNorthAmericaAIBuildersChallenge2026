/**
 * ConfirmModal — accessible dialog replacing window.confirm().
 * Usage:
 *   const { confirm } = useConfirm()
 *   const ok = await confirm('Delete this task?', 'Delete', 'danger')
 *   if (ok) { ... }
 */
import { createContext, useContext, useState, useRef } from 'react'
import { AlertTriangle } from 'lucide-react'
import './ConfirmModal.css'

interface ConfirmOptions {
  message: string
  confirmLabel?: string
  variant?: 'danger' | 'primary'
}

type Resolver = (result: boolean) => void

interface ConfirmContextValue {
  confirm: (message: string, confirmLabel?: string, variant?: 'danger' | 'primary') => Promise<boolean>
}

const ConfirmContext = createContext<ConfirmContextValue>({
  confirm: () => Promise.resolve(false),
})
export const useConfirm = () => useContext(ConfirmContext)

export function ConfirmProvider({ children }: { children: React.ReactNode }) {
  const [opts, setOpts] = useState<ConfirmOptions | null>(null)
  const resolverRef = useRef<Resolver | null>(null)

  const confirm = (message: string, confirmLabel = 'Confirm', variant: 'danger' | 'primary' = 'danger') =>
    new Promise<boolean>(resolve => {
      setOpts({ message, confirmLabel, variant })
      resolverRef.current = resolve
    })

  function resolve(result: boolean) {
    resolverRef.current?.(result)
    setOpts(null)
  }

  return (
    <ConfirmContext.Provider value={{ confirm }}>
      {children}
      {opts && (
        <div className="modal-backdrop" role="dialog" aria-modal="true" aria-label="Confirmation">
          <div className="modal-box">
            <div className="modal-icon">
              <AlertTriangle size={22} aria-hidden="true" />
            </div>
            <p className="modal-msg">{opts.message}</p>
            <div className="modal-actions">
              <button className="btn btn-ghost" onClick={() => resolve(false)}>Cancel</button>
              <button
                className={`btn btn-${opts.variant === 'danger' ? 'danger' : 'primary'}`}
                onClick={() => resolve(true)}
                autoFocus
              >
                {opts.confirmLabel}
              </button>
            </div>
          </div>
        </div>
      )}
    </ConfirmContext.Provider>
  )
}
