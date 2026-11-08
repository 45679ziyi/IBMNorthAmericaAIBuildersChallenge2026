import './components.css'

interface EmptyStateProps {
  message: string
  action?: { label: string; onClick: () => void }
}

export function EmptyState({ message, action }: EmptyStateProps): JSX.Element {
  return (
    <div className="state-empty" role="status">
      <p className="state-message">{message}</p>
      {action && (
        <button
          className="btn btn-ghost btn-sm state-action"
          onClick={action.onClick}
        >
          {action.label}
        </button>
      )}
    </div>
  )
}
