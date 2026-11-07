interface ErrorStateProps {
  message: string
  onRetry?: () => void
}

export function ErrorState({ message, onRetry }: ErrorStateProps): JSX.Element {
  return (
    <div className="state-error" role="alert">
      <p style={{ margin: 0 }}>{message}</p>
      {onRetry && (
        <button
          className="btn btn-ghost btn-sm"
          style={{ marginTop: 'var(--sp-3)' }}
          onClick={onRetry}
        >
          Try again
        </button>
      )}
    </div>
  )
}
