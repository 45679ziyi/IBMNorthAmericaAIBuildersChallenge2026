import { useState, useEffect } from 'react'
import { getCampusBuildings, getCampusIncidents, type Building, type CanonicalEvent } from '../../api/client'
import './CampusMap.css'

interface Props {
  highlightBuildings?: string[]   // building IDs to highlight (incidents)
  compact?: boolean               // smaller embedded mode
}

interface WalkEdge { a: string; b: string; minutes: number }

// Deterministic SVG coordinate from building index (0-based layout)
// The actual coordinates come from the API, which hashes the building ID.
// We scale them to the viewBox here.
function scaleCoord(val: number, min: number, range: number, mapSize: number): number {
  if (range === 0) return mapSize / 2
  return 10 + ((val - min) / range) * (mapSize - 20)
}

export function CampusMap({ highlightBuildings = [], compact = false }: Props) {
  const [buildings, setBuildings] = useState<Building[]>([])
  const [incidents, setIncidents] = useState<CanonicalEvent[]>([])
  const [selected, setSelected] = useState<Building | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([getCampusBuildings(), getCampusIncidents()])
      .then(([b, i]) => { setBuildings(b); setIncidents(i) })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <div className="campus-map-placeholder">Loading map…</div>
  if (buildings.length === 0) return <div className="campus-map-placeholder">No campus data</div>

  const SIZE = compact ? 300 : 500
  const RADIUS = compact ? 10 : 15

  // Normalize coordinates to viewBox
  const xs = buildings.map(b => b.x)
  const ys = buildings.map(b => b.y)
  const minX = Math.min(...xs), maxX = Math.max(...xs)
  const minY = Math.min(...ys), maxY = Math.max(...ys)
  const rangeX = maxX - minX, rangeY = maxY - minY

  function sx(x: number) { return scaleCoord(x, minX, rangeX, SIZE) }
  function sy(y: number) { return scaleCoord(y, minY, rangeY, SIZE) }

  // Build incident set for quick lookup
  const incidentBldSet = new Set(
    incidents.flatMap(ev => {
      try {
        const refs = JSON.parse(ev.entity_refs as unknown as string ?? '[]') as Array<{ type: string; id: string }>
        return refs.filter(r => r.type === 'building').map(r => r.id)
      } catch { return [] }
    })
  )

  // Combine highlight props + incident buildings
  const allHighlight = new Set([...highlightBuildings, ...incidentBldSet])

  return (
    <div className={`campus-map-wrapper${compact ? ' campus-map-compact' : ''}`}>
      <svg
        viewBox={`0 0 ${SIZE} ${SIZE}`}
        width={SIZE}
        height={SIZE}
        className="campus-map-svg"
        role="img"
        aria-label="Campus map"
      >
        {/* Connection lines (placeholder edges between all building pairs) */}
        {buildings.map((a, i) =>
          buildings.slice(i + 1).map(b => (
            <line
              key={`${a.id}-${b.id}`}
              x1={sx(a.x)} y1={sy(a.y)}
              x2={sx(b.x)} y2={sy(b.y)}
              className="campus-map-edge"
              strokeOpacity={0.25}
            />
          ))
        )}

        {/* Building nodes */}
        {buildings.map(b => {
          const cx = sx(b.x), cy = sy(b.y)
          const isHighlighted = allHighlight.has(b.id)
          const isSelected = selected?.id === b.id
          return (
            <g
              key={b.id}
              className="campus-map-node"
              onClick={() => setSelected(prev => prev?.id === b.id ? null : b)}
              aria-label={b.name}
              role="button"
              tabIndex={0}
              onKeyDown={e => e.key === 'Enter' && setSelected(prev => prev?.id === b.id ? null : b)}
            >
              {isHighlighted && (
                <circle
                  cx={cx} cy={cy} r={RADIUS + 6}
                  className="campus-map-pulse"
                  aria-hidden="true"
                />
              )}
              <circle
                cx={cx} cy={cy} r={RADIUS}
                className={`campus-map-circle ${isHighlighted ? 'campus-map-circle-incident' : ''} ${isSelected ? 'campus-map-circle-selected' : ''} campus-map-circle-${b.kind}`}
              />
              <text
                x={cx} y={cy + (compact ? 3 : 4)}
                textAnchor="middle"
                className="campus-map-label-code"
              >
                {b.code}
              </text>
              {!compact && (
                <text
                  x={cx} y={cy + RADIUS + 14}
                  textAnchor="middle"
                  className="campus-map-label-name"
                >
                  {b.name.replace(' (demo)', '')}
                </text>
              )}
            </g>
          )
        })}
      </svg>

      {/* Popup for selected building */}
      {selected && (
        <div className="campus-map-popup" role="dialog" aria-label={selected.name}>
          <button className="campus-map-popup-close" onClick={() => setSelected(null)} aria-label="Close">×</button>
          <strong>{selected.name}</strong>
          <dl className="campus-map-popup-dl">
            <dt>Code</dt><dd>{selected.code}</dd>
            <dt>Kind</dt><dd>{selected.kind}</dd>
            <dt>Floors</dt><dd>{selected.floors}</dd>
            {allHighlight.has(selected.id) && (
              <><dt>Status</dt><dd className="campus-map-popup-incident">⚠ Active incident</dd></>
            )}
          </dl>
        </div>
      )}
    </div>
  )
}
