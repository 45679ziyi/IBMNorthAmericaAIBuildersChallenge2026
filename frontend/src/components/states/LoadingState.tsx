import React from 'react'

interface LoadingStateProps {
  message?: string
}

export function LoadingState({ message = 'Loading…' }: LoadingStateProps) {
  return (
    <div className="state-container" role="status" aria-live="polite">
      <div className="state-spinner" aria-hidden="true" />
      <p className="state-message">{message}</p>
    </div>
  )
}
