import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { Geometry, Position } from 'geojson'
import { useApp } from '../store'
import { asset } from '../lib/data'
import { clamp } from '../lib/math'

const W = 1000
const H = 625
const MIN_ZOOM = 1
const MAX_ZOOM = 7

type View = { cx: number; cy: number; zoom: number }

const hazardColors = {
  flood: { fill: '#22d3ee', line: '#a5f3fc' },
  wildfire: { fill: '#f97316', line: '#fdba74' },
  construction: { fill: '#a78bfa', line: '#ddd6fe' },
}

function ringPath(ring: Position[], project: (lon: number, lat: number) => [number, number]): string {
  if (!ring.length) return ''
  return (
    ring
      .map(([lon, lat], i) => {
        const [x, y] = project(lon, lat)
        return `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`
      })
      .join(' ') + 'Z'
  )
}

function geometryPath(geometry: Geometry | undefined, project: (lon: number, lat: number) => [number, number]): string {
  if (!geometry) return ''
  const line = (coords: Position[]) =>
    coords
      .map(([lon, lat], i) => {
        const [x, y] = project(lon, lat)
        return `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`
      })
      .join(' ')
  switch (geometry.type) {
    case 'Polygon':
      return geometry.coordinates.map((ring) => ringPath(ring, project)).join(' ')
    case 'MultiPolygon':
      return geometry.coordinates.map((poly) => poly.map((ring) => ringPath(ring, project)).join(' ')).join(' ')
    case 'LineString':
      return line(geometry.coordinates)
    case 'MultiLineString':
      return geometry.coordinates.map(line).join(' ')
    default:
      return ''
  }
}

export default function MapView({ variant = 'stage' }: { variant?: 'stage' | 'analyst' }) {
  const app = useApp()
  const { scenario, time, selectedId, previewId, reviews, assignments, layers, ranked, fitSignal } = app
  const containerRef = useRef<HTMLDivElement | null>(null)
  const svgRef = useRef<SVGSVGElement | null>(null)
  const [view, setView] = useState<View>({ cx: W / 2, cy: H / 2, zoom: 1 })
  const drag = useRef<{ x: number; y: number; cx: number; cy: number; moved: boolean } | null>(null)

  const project = useCallback(
    (lon: number, lat: number): [number, number] => {
      if (!scenario) return [0, 0]
      const [west, south, east, north] = scenario.meta.bbox
      return [((lon - west) / (east - west)) * W, ((north - lat) / (north - south)) * H]
    },
    [scenario],
  )

  const latest = useMemo(() => {
    if (!scenario) return null
    const frames = scenario.timeline.frames.filter((frame) => frame.t <= time + 0.001)
    return frames.length ? frames[frames.length - 1] : scenario.timeline.frames[0]
  }, [scenario, time])

  useEffect(() => {
    setView({ cx: W / 2, cy: H / 2, zoom: 1 })
  }, [scenario?.meta.id])

  useEffect(() => {
    if (!scenario || fitSignal === 0) return
    setView({ cx: W / 2, cy: H / 2, zoom: 1 })
  }, [fitSignal, scenario])

  useEffect(() => {
    if (!scenario || variant !== 'analyst' || !selectedId) return
    const site = scenario.sites.find((s) => s.id === selectedId)
    if (!site) return
    const [x, y] = project(site.lon, site.lat)
    setView((current) => ({ cx: x, cy: y, zoom: Math.max(current.zoom, 1.6) }))
  }, [selectedId, scenario, variant, project])

  const registerCapture = useCallback(() => {
    const capture = async (): Promise<string | null> => {
      if (!svgRef.current || !scenario) return null
      try {
        const clone = svgRef.current.cloneNode(true) as SVGSVGElement
        const response = await fetch(asset(scenario.map.basemap.file))
        if (response.ok) {
          const blob = await response.blob()
          const dataUrl = await new Promise<string>((resolve, reject) => {
            const reader = new FileReader()
            reader.onload = () => resolve(String(reader.result))
            reader.onerror = () => reject(new Error('basemap encode failed'))
            reader.readAsDataURL(blob)
          })
          for (const image of Array.from(clone.querySelectorAll('image'))) image.setAttribute('href', dataUrl)
        } else {
          for (const image of Array.from(clone.querySelectorAll('image'))) image.remove()
        }
        const xml = new XMLSerializer().serializeToString(clone)
        const blob = new Blob([xml], { type: 'image/svg+xml;charset=utf-8' })
        const url = URL.createObjectURL(blob)
        const image = new Image()
        await new Promise<void>((resolve, reject) => {
          image.onload = () => resolve()
          image.onerror = () => reject(new Error('snapshot failed'))
          image.src = url
        })
        const canvas = document.createElement('canvas')
        canvas.width = W * 2
        canvas.height = H * 2
        const context = canvas.getContext('2d')
        if (!context) return null
        context.fillStyle = '#04101a'
        context.fillRect(0, 0, canvas.width, canvas.height)
        context.drawImage(image, 0, 0, canvas.width, canvas.height)
        URL.revokeObjectURL(url)
        return canvas.toDataURL('image/png')
      } catch {
        return null
      }
    }
    app.registerMap({ toDataURL: capture })
  }, [app, scenario])

  useEffect(() => {
    registerCapture()
  }, [registerCapture])

  const screenToView = (clientX: number, clientY: number): [number, number] => {
    const rect = containerRef.current?.getBoundingClientRect()
    if (!rect) return [0, 0]
    const scale = Math.max(rect.width / W, rect.height / H)
    const offsetX = (rect.width - W * scale) / 2
    const offsetY = (rect.height - H * scale) / 2
    return [(clientX - rect.left - offsetX) / scale, (clientY - rect.top - offsetY) / scale]
  }

  const onWheel = (event: React.WheelEvent<SVGSVGElement>) => {
    event.preventDefault()
    const [sx, sy] = screenToView(event.clientX, event.clientY)
    setView((current) => {
      const zoom = clamp(current.zoom * (event.deltaY > 0 ? 0.88 : 1.14), MIN_ZOOM, MAX_ZOOM)
      const px = current.cx + (sx - W / 2) / current.zoom
      const py = current.cy + (sy - H / 2) / current.zoom
      const cx = clamp(px - (sx - W / 2) / zoom, W * 0.15, W * 0.85)
      const cy = clamp(py - (sy - H / 2) / zoom, H * 0.15, H * 0.85)
      return { cx, cy, zoom }
    })
  }

  const onPointerDown = (event: React.PointerEvent<SVGSVGElement>) => {
    if (event.button !== 0) return
    const [x, y] = screenToView(event.clientX, event.clientY)
    drag.current = { x, y, cx: view.cx, cy: view.cy, moved: false }
    event.currentTarget.setPointerCapture(event.pointerId)
  }

  const onPointerMove = (event: React.PointerEvent<SVGSVGElement>) => {
    if (!drag.current) return
    const [x, y] = screenToView(event.clientX, event.clientY)
    const dx = (x - drag.current.x) / view.zoom
    const dy = (y - drag.current.y) / view.zoom
    if (Math.abs(dx) + Math.abs(dy) > 0.3) drag.current.moved = true
    setView((current) => ({
      ...current,
      cx: clamp(drag.current!.cx - dx, W * 0.1, W * 0.9),
      cy: clamp(drag.current!.cy - dy, H * 0.1, H * 0.9),
    }))
  }

  const onPointerUp = () => {
    drag.current = null
  }

  const zoomBy = (factor: number) => {
    setView((current) => ({ ...current, zoom: clamp(current.zoom * factor, MIN_ZOOM, MAX_ZOOM) }))
  }

  if (!scenario) return null

  const rankById = new Map(ranked.map((item) => [item.site.id, item.rank]))
  const colors = hazardColors[scenario.meta.hazard] ?? hazardColors.flood
  const transform = `translate(${W / 2} ${H / 2}) scale(${view.zoom}) translate(${-view.cx} ${-view.cy})`
  const pinScale = 1 / view.zoom
  const coverageFeatures = scenario.sites.filter((site) => assignments[site.id] || previewId === site.id)
  const showLabels = view.zoom >= 1.5
  const path = (geometry: Geometry | undefined) => geometryPath(geometry, project)

  return (
    <div className="map map-svg" ref={containerRef}>
      <svg
        ref={svgRef}
        viewBox={`0 0 ${W} ${H}`}
        preserveAspectRatio="xMidYMid slice"
        className="map-canvas"
        onWheel={onWheel}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
        role="application"
        aria-label="Operational map. Drag to pan, scroll to zoom."
      >
        <defs>
          <radialGradient id="map-glow" cx="50%" cy="45%" r="65%">
            <stop offset="0%" stopColor="#0b2a33" stopOpacity="0.55" />
            <stop offset="100%" stopColor="#04101a" stopOpacity="0" />
          </radialGradient>
          <pattern id="map-grid" width="50" height="50" patternUnits="userSpaceOnUse">
            <path d="M50 0H0V50" fill="none" stroke="#12303b" strokeWidth="0.6" />
          </pattern>
        </defs>

        <rect width={W} height={H} fill="#04101a" />
        <g transform={transform}>
          <rect width={W} height={H} fill="url(#map-grid)" opacity={0.5} />
          <image
            href={asset(scenario.map.basemap.file)}
            x={0}
            y={0}
            width={W}
            height={H}
            preserveAspectRatio="none"
            opacity={0.92}
          />
          <rect width={W} height={H} fill="url(#map-glow)" opacity={0.5} />

          {layers.landuse && (
            <g className="layer-landuse">
              {scenario.map.landuse.features.map((feature, index) => (
                <path
                  key={feature.id ?? index}
                  d={path(feature.geometry)}
                  className={`landuse-${String(feature.properties?.kind ?? 'meadow')}`}
                />
              ))}
            </g>
          )}

          {layers.buildings && (
            <g className="layer-buildings">
              {scenario.map.buildings.features.map((feature, index) => (
                <path key={feature.id ?? index} d={path(feature.geometry)} />
              ))}
            </g>
          )}

          {layers.power && (
            <g className="layer-power">
              {scenario.map.power.features.map((feature, index) => {
                if (feature.geometry.type === 'LineString') {
                  return <path key={feature.id ?? index} d={path(feature.geometry)} className="power-line" />
                }
                const [lon, lat] = (feature.geometry as { type: 'Point'; coordinates: [number, number] }).coordinates
                const [x, y] = project(lon, lat)
                return (
                  <g key={feature.id ?? index} transform={`translate(${x} ${y}) scale(${pinScale})`}>
                    <circle r={4.5} className="power-dot" />
                    <path d="M-2.2 -3 L2 -0.8 L-0.6 0.4 L2.2 3" className="power-bolt" />
                  </g>
                )
              })}
            </g>
          )}

          {layers.flood && latest && (
            <g className="layer-flood">
              <path d={path(latest.geometry)} className="flood-glow" style={{ stroke: colors.line }} />
              <path d={path(latest.geometry)} className="flood-fill" style={{ fill: colors.fill }} />
              <path d={path(latest.geometry)} className="flood-line" style={{ stroke: colors.line }} />
            </g>
          )}

          {layers.roads && (
            <g className="layer-roads">
              {scenario.map.roads.features.map((feature, index) => {
                const cls = String(feature.properties?.class ?? 'local')
                return (
                  <g key={feature.id ?? index}>
                    <path d={path(feature.geometry)} className={`road-casing road-${cls}-case`} />
                    <path d={path(feature.geometry)} className={`road road-${cls}`} />
                  </g>
                )
              })}
            </g>
          )}

          <g className="layer-water">
            {scenario.map.water.features
              .filter((feature) => feature.geometry.type === 'LineString')
              .map((feature, index) => (
                <g key={feature.id ?? index}>
                  <path d={path(feature.geometry)} className="river-wider" />
                  <path d={path(feature.geometry)} className="river" />
                </g>
              ))}
          </g>

          <g className="layer-boundary">
            {scenario.map.boundaries.features.map((feature, index) => (
              <path key={feature.id ?? index} d={path(feature.geometry)} />
            ))}
          </g>

          <g className="layer-coverage">
            {coverageFeatures.map((site) => {
              const assigned = Boolean(assignments[site.id])
              return (
                <path
                  key={site.id}
                  d={path(site.coverage as unknown as Geometry)}
                  className={assigned ? 'coverage assigned' : 'coverage preview'}
                />
              )
            })}
          </g>

          <g transform={`translate(${project(scenario.hero.depot[0], scenario.hero.depot[1]).join(' ')}) scale(${pinScale})`}>
            <rect x={-3.5} y={-3.5} width={7} height={7} transform="rotate(45)" className="depot-dot" />
            <text className="depot-label" x={8} y={3}>
              depot
            </text>
          </g>

          <g className="layer-pins">
            {scenario.sites.map((site) => {
              const [x, y] = project(site.lon, site.lat)
              const review = reviews[site.id] ?? 'pending'
              const inRisk = time + 0.001 >= site.riskAt
              const shownSeverity = inRisk ? site.severity : site.severity === 'red' ? 'orange' : site.severity
              const rank = rankById.get(site.id)
              const assigned = assignments[site.id]
              const classes = [
                'map-pin',
                `sev-${shownSeverity}`,
                inRisk ? 'in-risk' : 'watching',
                review !== 'pending' ? `review-${review}` : '',
                assigned ? 'assigned' : '',
                selectedId === site.id ? 'selected' : '',
                previewId === site.id ? 'preview' : '',
                rank ? '' : 'excluded',
                site.falsePositive ? 'false-positive' : '',
              ]
                .filter(Boolean)
                .join(' ')
              return (
                <g
                  key={site.id}
                  transform={`translate(${x} ${y}) scale(${pinScale})`}
                  className={classes}
                  tabIndex={0}
                  role="button"
                  aria-label={`${site.name}, rank ${rank ?? 'excluded'}, ${site.severity}`}
                  data-risk={site.riskAt}
                  data-inrisk={inRisk ? 'true' : 'false'}
                  data-time={time}
                  onClick={(event) => {
                    event.stopPropagation()
                    if (drag.current?.moved) return
                    app.selectSite(site.id)
                  }}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter' || event.key === ' ') app.selectSite(site.id)
                  }}
                  onMouseEnter={() => app.previewSite(site.id)}
                  onMouseLeave={() => app.previewSite(null)}
                >
                  <circle className="pin-hit" r={18} />
                  <circle className="pin-ring-svg" r={14} />
                  <circle className="pin-core-svg" r={8.5} />
                  <text className="pin-rank-svg" y={0.5}>
                    {rank ?? '–'}
                  </text>
                  <g className={`pin-label-group ${showLabels || rank === 1 ? 'visible' : ''}`}>
                    <rect className="pin-label-bg" x={13} y={-9} width={Math.max(34, site.name.length * 3.4)} height={13} rx={3} />
                    <text className="pin-label-svg" x={17} y={0.8}>
                      {site.name}
                    </text>
                  </g>
                </g>
              )
            })}
          </g>
        </g>
      </svg>

      <div className="map-controls">
        <button className="map-ctrl" onClick={() => zoomBy(1.35)} aria-label="Zoom in">
          +
        </button>
        <button className="map-ctrl" onClick={() => zoomBy(0.74)} aria-label="Zoom out">
          −
        </button>
        <button
          className="map-ctrl"
          onClick={() => setView({ cx: W / 2, cy: H / 2, zoom: 1 })}
          aria-label="Fit the whole area"
        >
          ⤢
        </button>
      </div>
      <div className="map-attrib">
        © OpenStreetMap contributors · © Copernicus Sentinel data · {scenario.meta.imagery.simulated ? 'simulated pack' : 'licensed'}
      </div>
    </div>
  )
}
