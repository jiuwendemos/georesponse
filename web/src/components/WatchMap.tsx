import { useMemo, useState } from 'react'
import type { ProactiveAlert, ProactiveScope, CoverageEntry } from '../types'
import { severityLabel } from '../lib/format'

const W = 1000
const H = 560

export default function WatchMap({
  scopes,
  alerts,
  coverage = [],
  selectedScopeId,
  onSelectScope,
  onSelectAlert,
  drawing = false,
  onDraw,
}: {
  scopes: ProactiveScope[]
  alerts: ProactiveAlert[]
  coverage?: CoverageEntry[]
  selectedScopeId?: string | null
  onSelectScope?: (id: string) => void
  onSelectAlert?: (id: string) => void
  drawing?: boolean
  onDraw?: (bbox: [number, number, number, number]) => void
}) {
  const [start, setStart] = useState<[number, number] | null>(null)
  const [preview, setPreview] = useState<[number, number] | null>(null)
  const [tableOpen, setTableOpen] = useState(false)

  const bounds = useMemo(() => {
    if (!scopes.length) return [6.2, 50.3, 7.4, 51.0]
    const west = Math.min(...scopes.map((s) => s.bbox[0])) - 0.12
    const south = Math.min(...scopes.map((s) => s.bbox[1])) - 0.1
    const east = Math.max(...scopes.map((s) => s.bbox[2])) + 0.12
    const north = Math.max(...scopes.map((s) => s.bbox[3])) + 0.1
    return [west, south, east, north]
  }, [scopes])

  const [west, south, east, north] = bounds
  const project = (lon: number, lat: number): [number, number] => [
    ((lon - west) / (east - west)) * W,
    ((north - lat) / (north - south)) * H,
  ]
  const unproject = (x: number, y: number): [number, number] => [
    west + (x / W) * (east - west),
    north - (y / H) * (north - south),
  ]
  const toSvg = (clientX: number, clientY: number, element: SVGSVGElement): [number, number] => {
    const rect = element.getBoundingClientRect()
    return [((clientX - rect.left) / rect.width) * W, ((clientY - rect.top) / rect.height) * H]
  }
  const scopeBox = (bbox: [number, number, number, number]) => {
    const [x1, y1] = project(bbox[0], bbox[3])
    const [x2, y2] = project(bbox[2], bbox[1])
    return { x: Math.min(x1, x2), y: Math.min(y1, y2), width: Math.abs(x2 - x1), height: Math.abs(y2 - y1) }
  }
  const alertDot = (alert: ProactiveAlert) => project(alert.lon, alert.lat)
  const coverageById = new Map(coverage.map((row) => [row.scopeId, row]))
  const colors = { red: '#fb7185', orange: '#fbbf24', yellow: '#facc15' }

  const click = (event: React.MouseEvent<SVGSVGElement>) => {
    if (!drawing) return
    const [x, y] = toSvg(event.clientX, event.clientY, event.currentTarget)
    if (!start) {
      setStart([x, y])
      setPreview([x, y])
      return
    }
    const [lon1, lat1] = unproject(start[0], start[1])
    const [lon2, lat2] = unproject(x, y)
    const bbox: [number, number, number, number] = [
      Math.min(lon1, lon2),
      Math.min(lat1, lat2),
      Math.max(lon1, lon2),
      Math.max(lat1, lat2),
    ]
    setStart(null)
    setPreview(null)
    onDraw?.(bbox)
  }

  return (
    <div className={`watch-map ${drawing ? 'drawing' : ''}`}>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        role="group"
        aria-label="Monitoring coverage map. Use Enter on a scope or alert."
        onClick={click}
        onMouseMove={(event) => {
          if (drawing && start) setPreview(toSvg(event.clientX, event.clientY, event.currentTarget))
        }}
      >
        <defs>
          <pattern id="watch-grid" width="42" height="42" patternUnits="userSpaceOnUse">
            <path d="M42 0H0V42" fill="none" stroke="#14313c" strokeWidth="0.7" />
          </pattern>
          <linearGradient id="watch-bg" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stopColor="#071821" />
            <stop offset="1" stopColor="#0b2530" />
          </linearGradient>
        </defs>
        <rect width={W} height={H} fill="url(#watch-bg)" />
        <rect width={W} height={H} fill="url(#watch-grid)" opacity={0.65} />
        <path
          d="M30 390 C150 340 220 410 330 365 C450 315 540 380 660 335 C780 290 880 330 980 300"
          fill="none"
          stroke="#0d4a5c"
          strokeWidth={11}
          opacity={0.55}
          strokeLinecap="round"
        />
        <path
          d="M30 390 C150 340 220 410 330 365 C450 315 540 380 660 335 C780 290 880 330 980 300"
          fill="none"
          stroke="#22d3ee"
          strokeWidth={1.4}
          opacity={0.28}
        />

        {scopes.map((scope) => {
          const box = scopeBox(scope.bbox)
          const coverageRow = coverageById.get(scope.id)
          const selected = selectedScopeId === scope.id
          return (
            <g
              key={scope.id}
              className={`scope-shape ${selected ? 'selected' : ''} ${coverageRow?.blindSpot ? 'blind' : ''}`}
              onClick={(event) => {
                event.stopPropagation()
                if (!drawing) onSelectScope?.(scope.id)
              }}
              role="button"
              tabIndex={0}
              onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') onSelectScope?.(scope.id) }}
            >
              <rect x={box.x} y={box.y} width={box.width} height={box.height} rx={4} />
              <text x={box.x + 6} y={box.y + 14} className="scope-label">
                {scope.name}
              </text>
              <text x={box.x + 6} y={box.y + 24} className="scope-sub">
                {scope.cadence} · {scope.asset_class}
              </text>
              {coverageRow?.blindSpot && (
                <text x={box.x + box.width - 8} y={box.y + 14} textAnchor="end" className="scope-blind">
                  blind spot
                </text>
              )}
            </g>
          )
        })}

        {alerts.map((alert) => {
          const [x, y] = alertDot(alert)
          const dim = alert.status === 'resolved' || alert.status === 'dismissed'
          return (
            <g
              key={alert.id}
              className={`watch-alert-pin ${dim ? 'dim' : ''}`}
              transform={`translate(${x} ${y})`}
              onClick={(event) => {
                event.stopPropagation()
                if (!drawing) onSelectAlert?.(alert.id)
              }}
              role="button"
              tabIndex={0}
              onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') onSelectAlert?.(alert.id) }}
            >
              <circle r={13} fill={colors[alert.severity]} opacity={0.14} />
              <circle r={5.4} fill={colors[alert.severity]} stroke="#061018" strokeWidth={1.2} />
              <title>{`${alert.title} · ${severityLabel(alert.severity)}`}</title>
            </g>
          )
        })}

        {drawing && start && preview && (
          <rect
            x={Math.min(start[0], preview[0])}
            y={Math.min(start[1], preview[1])}
            width={Math.abs(preview[0] - start[0])}
            height={Math.abs(preview[1] - start[1])}
            className="draw-box"
          />
        )}

        <g transform={`translate(${W - 250} ${H - 34})`} className="watch-map-legend">
          <circle cx={0} cy={0} r={4} fill="#fb7185" />
          <text x={8} y={3}>high risk</text>
          <circle cx={68} cy={0} r={4} fill="#fbbf24" />
          <text x={76} y={3}>watch</text>
          <rect x={128} y={-5} width={12} height={10} rx={2} fill="none" stroke="#67e8f9" strokeDasharray="3 3" />
          <text x={146} y={3}>scope</text>
        </g>
      </svg>
      <button className="watch-map-table-btn" onClick={() => setTableOpen((value) => !value)} aria-label="Accessible coverage table">Table</button>
      {tableOpen && (
        <div className="watch-map-table" role="dialog" aria-label="Coverage table">
          <div className="map-table-head"><b>Coverage table</b><button className="icon-btn" onClick={() => setTableOpen(false)} aria-label="Close table">×</button></div>
          <table>
            <caption>Scopes and open alerts</caption>
            <thead><tr><th>Scope</th><th>Cadence</th><th>Readiness</th><th>Freshness</th><th>Open alerts</th></tr></thead>
            <tbody>
              {scopes.map((scope) => {
                const row = coverageById.get(scope.id)
                const open = alerts.filter((a) => a.scope_id === scope.id && ['new', 'acknowledged', 'assigned', 'investigating'].includes(a.status)).length
                return <tr key={scope.id}><td>{scope.name}</td><td>{scope.cadence}</td><td>{row ? `${Math.round(row.readiness * 100)}%` : '—'}</td><td>{row?.freshnessHours != null ? `${Math.round(row.freshnessHours)}h` : 'never'}</td><td>{open}</td></tr>
              })}
            </tbody>
          </table>
        </div>
      )}
      {drawing && <div className="draw-hint">Click two corners to draw a scope · {start ? 'second corner' : 'first corner'}</div>}
    </div>
  )
}
