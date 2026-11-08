import './components.css'

interface ErrorStateProps {
  message: string
  onRetry?: () => void
}

export function ErrorState({ message, onRetry }: ErrorStateProps): JSX.Element {
  return (
    <div className="state-error" role="alert">
      <p className="state-message">{message}</p>
      {onRetry && (
        <button
          className="btn btn-ghost btn-sm state-action"
          onClick={onRetry}
        >
          Try again
        </button>
      )}
    </div>
  )
}
