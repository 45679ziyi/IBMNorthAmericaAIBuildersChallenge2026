/**
 * SkeletonCard — animated shimmer placeholder for loading states.
 * Usage:
 *   <SkeletonCard lines={3} />
 *   <SkeletonList count={4} />
 */
import './Skeleton.css'

export function SkeletonCard({ lines = 2, height }: { lines?: number; height?: string }) {
  return (
    <div className="skeleton-card" style={height ? { height } : undefined} aria-hidden="true">
      <div className="skeleton-line skeleton-line-title" />
      {Array.from({ length: lines - 1 }).map((_, i) => (
        <div key={i} className={`skeleton-line ${i === lines - 2 ? 'skeleton-line-short' : ''}`} />
      ))}
    </div>
  )
}

export function SkeletonList({ count = 3, lines = 2 }: { count?: number; lines?: number }) {
  return (
    <div className="skeleton-list" aria-hidden="true" aria-label="Loading…">
      {Array.from({ length: count }).map((_, i) => (
        <SkeletonCard key={i} lines={lines} />
      ))}
    </div>
  )
}
