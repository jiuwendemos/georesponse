import { AppProvider, useApp } from './store'
import { Icon, Modal, Toast, TopBar } from './components/ui'
import Stage from './components/Stage'
import Analyst from './components/Analyst'
import Dashboard from './components/Dashboard'
import Method from './components/Method'
import Booth from './components/Booth'
import Report from './components/Report'
import FieldOrder from './components/FieldOrder'
import { pct } from './lib/format'

function Provenance() {
  const app = useApp()
  const scenario = app.scenario
  if (!scenario) return null
  const provenance = scenario.provenance
  return (
    <Modal open={app.provenanceOpen} onClose={() => app.openProvenance(false)} className="provenance-card" label="Provenance">
      <div className="eyebrow">
        <span className="dot" /> Provenance panel
      </div>
      <h2>{scenario.meta.title}</h2>
      <p className="audit-sub">
        {scenario.meta.region} · {scenario.meta.eventDate} · generated {provenance.generatedAt}
      </p>
      <div className="provenance-grid">
        <div>
          <span>Imagery</span>
          <b>{scenario.meta.imagery.source}</b>
          <small>{scenario.meta.imagery.resolution} · {scenario.meta.imagery.acquired}</small>
        </div>
        <div>
          <span>Model</span>
          <b>{provenance.model}</b>
          <small>pinned on every finding</small>
        </div>
        <div>
          <span>Status</span>
          <b>{scenario.meta.imagery.simulated ? 'Simulated demo pack' : 'Customer imagery'}</b>
          <small>never presented as operational truth</small>
        </div>
        <div>
          <span>Human review</span>
          <b>Mandatory</b>
          <small>no automated property decision</small>
        </div>
      </div>
      <div className="provenance-weights">
        <h3>Ranking weights</h3>
        {Object.entries(provenance.weights).map(([key, value]) => (
          <div className="weight-row" key={key}>
            <span>{key}</span>
            <div><span style={{ width: `${pct(value)}` }} /></div>
            <b>{pct(value)}</b>
          </div>
        ))}
      </div>
      <div className="provenance-rights">
        <h3>Data rights</h3>
        <ul>
          {provenance.dataRights.map((right) => (
            <li key={right}><Icon name="check" size={12} /> {right}</li>
          ))}
        </ul>
      </div>
      <div className="provenance-disclaimer">
        <Icon name="shield" size={15} />
        <span>{provenance.disclaimer}</span>
      </div>
      <div className="provenance-foot">
        <span>{scenario.meta.imagery.attribution} · © OpenStreetMap contributors (ODbL)</span>
        <span>{scenario.meta.sites} sites · {scenario.meta.areaKm2.toFixed(0)} km²</span>
      </div>
    </Modal>
  )
}

function Shell() {
  const app = useApp()

  if (app.loading && !app.scenario) {
    return (
      <div className="loading-screen">
        <div className="loading-mark">
          <Icon name="radar" size={34} />
        </div>
        <b>GeoResponse</b>
        <span>Loading the offline imagery pack…</span>
      </div>
    )
  }

  if (app.error) {
    return (
      <div className="loading-screen error-screen">
        <Icon name="x" size={30} />
        <b>Could not load the demo pack</b>
        <span>{app.error}</span>
        <span>Run <code>py -m georesponse.datapack</code> then reload.</span>
      </div>
    )
  }

  return (
    <div className={`app app-${app.mode}`}>
      <TopBar />
      <main className="app-main">
        {app.mode === 'stage' && <Stage />}
        {app.mode === 'analyst' && <Analyst />}
        {app.mode === 'dashboard' && <Dashboard />}
        {app.mode === 'method' && <Method />}
        {app.mode === 'booth' && <Booth />}
      </main>
      <Report />
      <FieldOrder />
      <Provenance />
      <Toast />
    </div>
  )
}

export default function App() {
  return (
    <AppProvider>
      <Shell />
    </AppProvider>
  )
}
