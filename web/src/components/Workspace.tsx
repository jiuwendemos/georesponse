import { useEffect, useMemo, useState } from 'react'
import { useApp } from '../store'
import { usePrefs } from '../prefs'
import { Button, Card, EmptyState, Field, TextInput } from './ds'
import { Icon, Modal } from './ui'
import { compactEuro, cx, number } from '../lib/format'
import {
  loadSites,
  parseAny,
  saveSites,
  templateCsv,
  toCsv,
  toGeoJson,
  type WorkspaceSeverity,
  type WorkspaceSite,
} from '../lib/workspace'

const SEVERITIES: WorkspaceSeverity[] = ['red', 'orange', 'yellow']

function download(text: string, filename: string, mime: string) {
  const blob = new Blob([text], { type: mime })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  anchor.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

function bounds(sites: WorkspaceSite[]): [number, number, number, number] {
  if (!sites.length) return [7.0, 50.5, 7.2, 50.6]
  const lons = sites.map((site) => site.lon)
  const lats = sites.map((site) => site.lat)
  const west = Math.min(...lons)
  const east = Math.max(...lons)
  const south = Math.min(...lats)
  const north = Math.max(...lats)
  const padX = Math.max(0.005, (east - west) * 0.15)
  const padY = Math.max(0.005, (north - south) * 0.15)
  return [west - padX, south - padY, east + padX, north + padY]
}

export default function Workspace() {
  const app = useApp()
  const prefs = usePrefs()
  const [sites, setSites] = useState<WorkspaceSite[]>(loadSites)
  const [selected, setSelected] = useState<string | null>(null)
  const [importOpen, setImportOpen] = useState(false)
  const [importText, setImportText] = useState('')
  const [status, setStatus] = useState<string>('')

  useEffect(() => {
    saveSites(sites)
  }, [sites])

  const current = sites.find((site) => site.id === selected) ?? null
  const parsed = useMemo(() => (importText.trim() ? parseAny(importText) : null), [importText])
  const box = bounds(sites)
  const project = (lon: number, lat: number): [number, number] => [
    24 + ((lon - box[0]) / (box[2] - box[0] || 1)) * 752,
    24 + ((box[3] - lat) / (box[3] - box[1] || 1)) * 372,
  ]

  const update = (patch: Partial<WorkspaceSite>) => {
    if (!current) return
    setSites((items) => items.map((site) => (site.id === current.id ? { ...site, ...patch } : site)))
  }

  const addSite = () => {
    const id = `S-${Date.now().toString(36).toUpperCase()}`
    const site: WorkspaceSite = {
      id,
      name: 'New site',
      lat: sites[0]?.lat ?? 50.545,
      lon: sites[0]?.lon ?? 7.1,
      severity: 'orange',
      confidence: 0.7,
      valueEur: 0,
      population: 0,
      access: 'clear',
      notes: '',
    }
    setSites((items) => [...items, site])
    setSelected(id)
    setStatus('Site added. Edit it on the right, or import a file.')
  }

  const remove = (id: string) => {
    setSites((items) => items.filter((site) => site.id !== id))
    if (selected === id) setSelected(null)
  }

  const loadExample = async () => {
    try {
      const response = await fetch(new URL('examples/workspace-example.geojson', document.baseURI).toString())
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      const parsed = parseAny(await response.text())
      if (!parsed.sites.length) throw new Error('no sites in the example file')
      setSites((items) => {
        const byId = new Map(items.map((site) => [site.id, site]))
        for (const site of parsed.sites) byId.set(site.id, site)
        return Array.from(byId.values())
      })
      setStatus(`Loaded the bundled example case: ${parsed.sites.length} sites. Values are sample data.`)
    } catch (error) {
      setStatus(`Could not load the example case: ${String((error as Error).message ?? error)}`)
    }
  }

  const runImport = () => {
    if (!parsed || !parsed.sites.length) return
    setSites((items) => {
      const byId = new Map(items.map((site) => [site.id, site]))
      for (const site of parsed.sites) byId.set(site.id, site)
      return Array.from(byId.values())
    })
    setStatus(`Imported ${parsed.sites.length} site(s).${parsed.errors.length ? ` ${parsed.errors.length} row(s) skipped.` : ''}`)
    setImportOpen(false)
    setImportText('')
  }

  const red = sites.filter((site) => site.severity === 'red').length
  const value = sites.reduce((sum, site) => sum + site.valueEur, 0)
  const people = sites.reduce((sum, site) => sum + site.population, 0)

  return (
    <div className="workspace">
      <header className="workspace-head">
        <div>
          <span className="eyebrow"><span className="dot" /> My workspace · {prefs.dataMode === 'workspace' ? 'demo data hidden' : 'demo data available in the Stage tabs'}</span>
          <h1>Your sites, your decision.</h1>
          <p className="audit-sub">Import a CSV or GeoJSON of sites. Everything stays in this browser until you connect a backend.</p>
        </div>
        <div className="workspace-actions">
          <Button variant="secondary" onClick={() => setImportOpen(true)}><Icon name="download" size={14} /> Import CSV / GeoJSON</Button>
          <Button variant="primary" onClick={addSite}><Icon name="pin" size={14} /> Add site</Button>
        </div>
      </header>

      <div className="workspace-kpis">
        <div><span>Sites</span><b>{sites.length}</b><em>{red} red</em></div>
        <div><span>Value at risk</span><b>{compactEuro(value)}</b><em>from your rows</em></div>
        <div><span>People</span><b>{number(people)}</b><em>within the import</em></div>
        <div><span>Source</span><b>{sites.length ? 'local workspace' : 'empty'}</b><em>{prefs.dataMode === 'workspace' ? 'demo hidden' : 'demo still available'}</em></div>
      </div>

      {sites.length === 0 ? (
        <div className="workspace-empty">
          <EmptyState
            icon={<Icon name="map" size={26} />}
            title="Your workspace is empty"
            body="Import sites or add one manually. The demo pack stays available from Settings whenever you want it."
            action={
              <div className="workspace-empty-actions">
                <Button variant="primary" onClick={() => setImportOpen(true)}><Icon name="download" size={14} /> Import sites</Button>
                <Button onClick={() => void loadExample()}>Load example case</Button>
                <Button onClick={addSite}>Add one manually</Button>
                <Button variant="ghost" onClick={() => { prefs.setDataMode('demo'); app.setMode('stage') }}>Open demo pack</Button>
              </div>
            }
          />
        </div>
      ) : (
        <div className="workspace-grid">
          <section className="workspace-map-card" aria-label="Workspace map">
            <div className="workspace-map-head">
              <b>{sites.length} sites</b>
              <span>Your coordinates · no synthetic basemap</span>
            </div>
            <svg viewBox="0 0 800 420" className="workspace-map" role="img" aria-label="Map of your imported sites">
              <defs>
                <pattern id="ws-grid" width="40" height="40" patternUnits="userSpaceOnUse">
                  <path d="M40 0H0V40" fill="none" stroke="var(--line)" strokeWidth="1" />
                </pattern>
              </defs>
              <rect width="800" height="420" fill="var(--bg-2)" />
              <rect width="800" height="420" fill="url(#ws-grid)" opacity="0.6" />
              {sites.map((site) => {
                const [x, y] = project(site.lon, site.lat)
                return (
                  <g
                    key={site.id}
                    transform={`translate(${x} ${y})`}
                    className={cx('ws-pin', `sev-${site.severity}`, selected === site.id && 'selected')}
                    role="button"
                    tabIndex={0}
                    aria-label={`${site.name}, ${site.severity}`}
                    onClick={() => setSelected(site.id)}
                    onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') setSelected(site.id) }}
                  >
                    <circle r={12} className="ws-pin-ring" />
                    <circle r={6} className="ws-pin-core" />
                    <text x={16} y={4} className="ws-pin-label">{site.name}</text>
                  </g>
                )
              })}
            </svg>
            <div className="workspace-map-foot">
              <span>{box[0].toFixed(4)}, {box[1].toFixed(4)} → {box[2].toFixed(4)}, {box[3].toFixed(4)}</span>
              <Button size="sm" onClick={() => download(toGeoJson(sites), 'georesponse-sites.geojson', 'application/geo+json')}>Export GeoJSON</Button>
              <Button size="sm" onClick={() => download(toCsv(sites), 'georesponse-sites.csv', 'text/csv')}>Export CSV</Button>
            </div>
          </section>

          <aside className="workspace-side">
            <div className="workspace-table">
              {sites.map((site) => (
                <div
                  key={site.id}
                  className={cx('ws-row', selected === site.id && 'active')}
                  role="button"
                  tabIndex={0}
                  onClick={() => setSelected(site.id)}
                  onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') setSelected(site.id) }}
                >
                  <span className={cx('ws-dot', site.severity)} />
                  <span className="ws-row-name">{site.name}<small>{site.lat.toFixed(4)}, {site.lon.toFixed(4)}</small></span>
                  <span className="ws-row-value">{compactEuro(site.valueEur)}</span>
                  <span
                    className="ws-row-delete"
                    role="button"
                    tabIndex={0}
                    aria-label={`Delete ${site.name}`}
                    onClick={(event) => { event.stopPropagation(); remove(site.id) }}
                    onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') { event.stopPropagation(); remove(site.id) } }}
                  >
                    <Icon name="close" size={12} />
                  </span>
                </div>
              ))}
            </div>

            {current ? (
              <Card eyebrow="Selected site" title={current.name}>
                <div className="workspace-form">
                  <Field label="Name"><TextInput value={current.name} onChange={(event) => update({ name: event.target.value })} /></Field>
                  <div className="workspace-form-row">
                    <Field label="Latitude"><TextInput type="number" step="0.0001" value={current.lat} onChange={(event) => update({ lat: Number(event.target.value) })} /></Field>
                    <Field label="Longitude"><TextInput type="number" step="0.0001" value={current.lon} onChange={(event) => update({ lon: Number(event.target.value) })} /></Field>
                  </div>
                  <div className="workspace-form-row">
                    <Field label="Severity">
                      <select value={current.severity} onChange={(event) => update({ severity: event.target.value as WorkspaceSeverity })}>
                        {SEVERITIES.map((severity) => <option key={severity} value={severity}>{severity}</option>)}
                      </select>
                    </Field>
                    <Field label="Confidence"><TextInput type="number" min="0" max="1" step="0.01" value={current.confidence} onChange={(event) => update({ confidence: Number(event.target.value) })} /></Field>
                  </div>
                  <div className="workspace-form-row">
                    <Field label="Value (EUR)"><TextInput type="number" value={current.valueEur} onChange={(event) => update({ valueEur: Number(event.target.value) })} /></Field>
                    <Field label="People"><TextInput type="number" value={current.population} onChange={(event) => update({ population: Number(event.target.value) })} /></Field>
                  </div>
                  <Field label="Access">
                    <select value={current.access} onChange={(event) => update({ access: event.target.value })}>
                      {['clear', 'slow', 'restricted', 'flooded', 'blocked', 'debris'].map((access) => <option key={access} value={access}>{access}</option>)}
                    </select>
                  </Field>
                  <Field label="Notes"><TextInput value={current.notes} onChange={(event) => update({ notes: event.target.value })} /></Field>
                  <div className="workspace-form-actions">
                    <Button variant="danger" size="sm" onClick={() => remove(current.id)}>Delete site</Button>
                    <Button variant="ghost" size="sm" onClick={() => { prefs.setDataMode('demo'); app.setMode('stage') }}>Open demo pack</Button>
                  </div>
                </div>
              </Card>
            ) : (
              <Card eyebrow="Details" title="Select a site">
                <p className="card-note">Pick a row or a pin to edit it. Changes are saved in this browser.</p>
              </Card>
            )}
          </aside>
        </div>
      )}

      {status && <div className="workspace-status" role="status">{status}</div>}

      <Modal open={importOpen} onClose={() => setImportOpen(false)} className="workspace-import" label="Import sites">
        <div className="eyebrow">Import · CSV or GeoJSON</div>
        <h2>Bring your own sites</h2>
        <p className="audit-sub">
          Required: name, lat, lon. Optional: id, severity, confidence, value_eur, population, access, notes.
          GeoJSON must be a FeatureCollection of Points.
        </p>
        <div className="workspace-import-actions">
          <label className="btn btn-sm">
            Choose file
            <input
              type="file"
              accept=".csv,text/csv,.json,.geojson,application/geo+json"
              hidden
              onChange={async (event) => {
                const file = event.target.files?.[0]
                if (file) setImportText(await file.text())
              }}
            />
          </label>
          <Button size="sm" variant="ghost" onClick={() => void loadExample()}>Load example case</Button>
          <Button size="sm" variant="ghost" onClick={() => setImportText(templateCsv())}>Use template</Button>
          <Button size="sm" variant="ghost" onClick={() => download(templateCsv(), 'georesponse-sites-template.csv', 'text/csv')}>Download template</Button>
        </div>
        <textarea
          className="workspace-import-text"
          value={importText}
          onChange={(event) => setImportText(event.target.value)}
          placeholder="Paste CSV or GeoJSON here"
          aria-label="CSV or GeoJSON content"
          spellCheck={false}
        />
        {parsed && (
          <div className={cx('workspace-import-preview', parsed.errors.length > 0 && 'has-errors')}>
            <b>{parsed.sites.length} valid site(s)</b>
            {parsed.errors.length > 0 && <span>{parsed.errors.length} skipped: {parsed.errors.slice(0, 3).join('; ')}</span>}
          </div>
        )}
        <div className="modal-actions">
          <Button variant="primary" onClick={runImport} disabled={!parsed || !parsed.sites.length}>Import {parsed?.sites.length ?? 0} site(s)</Button>
          <Button variant="ghost" onClick={() => setImportOpen(false)}>Cancel</Button>
        </div>
      </Modal>
    </div>
  )
}

export function WorkspaceGate({ mode }: { mode: string }) {
  const app = useApp()
  const prefs = usePrefs()
  return (
    <div className="workspace-gate">
      <Card eyebrow="Workspace mode" title={`${mode === 'watch' ? 'Watch' : mode === 'dashboard' ? 'Pilot' : mode === 'analyst' ? 'Analyst' : 'Stage'} is using your data`}>
        <p>Demo data is hidden because the data source is set to <b>My workspace</b>. Import your own sites, or switch back to the synthetic demo pack.</p>
        <div className="component-row">
          <Button variant="primary" onClick={() => app.setMode('workspace')}>Open my workspace</Button>
          <Button variant="ghost" onClick={() => { prefs.setDataMode('demo'); app.setMode('stage') }}>Switch to demo pack</Button>
        </div>
      </Card>
    </div>
  )
}
