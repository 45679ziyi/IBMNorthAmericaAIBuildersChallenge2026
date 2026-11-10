import React from 'react'

interface PermissionDeniedProps {
  requiredRole?: string
  currentRole?: string
}

export function PermissionDenied({ requiredRole, currentRole }: PermissionDeniedProps) {
  return (
    <div className="state-container state-denied" role="alert">
      <p className="state-title">Access denied</p>
      {requiredRole && (
        <p className="state-message">
          Only <strong>{requiredRole}</strong> may see this.
          {currentRole && <> You are acting as <strong>{currentRole}</strong>.</>}
        </p>
      )}
    </div>
  )
}
