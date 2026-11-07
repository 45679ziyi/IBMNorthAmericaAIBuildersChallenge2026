interface EmptyStateProps {
  message: string
  action?: { label: string; onClick: () => void }
}

export function EmptyState({ message, action }: EmptyStateProps): JSX.Element {
  return (
    <div className="state-empty" role="status">
      <p style={{ margin: 0 }}>{message}</p>
      {action && (
        <button
          className="btn btn-ghost btn-sm"
          style={{ marginTop: 'var(--sp-3)' }}
          onClick={action.onClick}
        >
          {action.label}
        </button>
      )}
    </div>
  )
}
