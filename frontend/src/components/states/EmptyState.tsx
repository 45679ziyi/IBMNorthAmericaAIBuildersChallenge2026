import React from 'react'

interface EmptyStateProps {
  title?: string
  message?: string
}

export function EmptyState({ title = 'Nothing here yet', message }: EmptyStateProps) {
  return (
    <div className="state-container state-empty">
      <p className="state-title">{title}</p>
      {message && <p className="state-message">{message}</p>}
    </div>
  )
}
