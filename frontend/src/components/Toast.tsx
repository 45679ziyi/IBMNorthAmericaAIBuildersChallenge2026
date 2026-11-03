/**
 * Toast notification system
 * Usage:
 *   const { showToast } = useToast()
 *   showToast('Task created', 'success')
 */
import { createContext, useContext, useState, useCallback, useRef } from 'react'
import { CheckCircle, AlertCircle, Info, X } from 'lucide-react'
import './Toast.css'

type ToastType = 'success' | 'error' | 'info'
interface ToastItem { id: number; message: string; type: ToastType }
interface ToastContextValue { showToast: (message: string, type?: ToastType) => void }

const ToastContext = createContext<ToastContextValue>({ showToast: () => {} })
export const useToast = () => useContext(ToastContext)

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([])
  const counter = useRef(0)

  const showToast = useCallback((message: string, type: ToastType = 'info') => {
    const id = ++counter.current
    setToasts(prev => [...prev, { id, message, type }])
    setTimeout(() => setToasts(prev => prev.filter(t => t.id !== id)), 3500)
  }, [])

  const dismiss = (id: number) => setToasts(prev => prev.filter(t => t.id !== id))

  return (
    <ToastContext.Provider value={{ showToast }}>
      {children}
      <div className="toast-stack" role="region" aria-label="Notifications" aria-live="polite">
        {toasts.map(t => (
          <div key={t.id} className={`toast toast-${t.type}`} role="status">
            <span className="toast-icon" aria-hidden="true">
              {t.type === 'success' && <CheckCircle size={16} />}
              {t.type === 'error' && <AlertCircle size={16} />}
              {t.type === 'info' && <Info size={16} />}
            </span>
            <span className="toast-msg">{t.message}</span>
            <button className="toast-close" onClick={() => dismiss(t.id)} aria-label="Dismiss">
              <X size={14} />
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}

// Empty component — toasts are rendered by provider
export function Toast() { return null }
