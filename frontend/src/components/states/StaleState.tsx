import React from 'react'

interface StaleStateProps {
  minutesAgo: number
  children: React.ReactNode
}

export function StaleState({ minutesAgo, children }: StaleStateProps) {
  return (
    <div className="state-stale-wrapper">
      <div className="state-stale-banner" role="status">
        Data from {minutesAgo} minute{minutesAgo !== 1 ? 's' : ''} ago
      </div>
      {children}
    </div>
  )
}
