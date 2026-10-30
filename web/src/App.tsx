import { lazy, Suspense, useEffect, useRef } from 'react'
import { AppProvider, useApp } from './store'
import { PrefsProvider, usePrefs } from './prefs'
import { UiProvider, useUi } from './ui-context'
import { Icon, Modal, MobileNav, Toast, TopBar } from './components/ui'
import Stage from './components/Stage'
import Report from './components/Report'
import FieldOrder from './components/FieldOrder'
import CommandPalette from './components/CommandPalette'
import AgentPanel from './components/AgentPanel'
import StyleGuide from './components/StyleGuide'
import SettingsPanel from './components/SettingsPanel'
import { Spinner } from './components/ds'
import { ErrorBoundary, OfflineBanner } from './components/Resilience'
import { pct } from './lib/format'

const Analyst = lazy(() => import('./components/Analyst'))
const Watch = lazy(() => import('./components/Watch'))
const Dashboard = lazy(() => import('./components/Dashboard'))
const Method = lazy(() => import('./components/Method'))
const Booth = lazy(() => import('./components/Booth'))

function Provenance() {
  const app = useApp()
  const scenario = app.scenario
  if (!scenario) return null
  const provenance = scenario.provenance
  return (
    <Modal open={app.provenanceOpen} onClose={() => app.openProvenance(false)} className="provenance-card" label="Provenance">
      <div className="eyebrow"><span className="dot" /> Provenance panel</div>
      <h2>{scenario.meta.title}</h2>
      <p className="audit-sub">{scenario.meta.region} · {scenario.meta.eventDate} · generated {provenance.generatedAt}</p>
      <div className="provenance-grid">
        <div><span>Imagery</span><b>{scenario.meta.imagery.source}</b><small>{scenario.meta.imagery.resolution} · {scenario.meta.imagery.acquired}</small></div>
        <div><span>Model</span><b>{provenance.model}</b><small>pinned on every finding</small></div>
        <div><span>Status</span><b>{scenario.meta.imagery.simulated ? 'Simulated demo pack' : 'Customer imagery'}</b><small>never presented as operational truth</small></div>
        <div><span>Human review</span><b>Mandatory</b><small>no automated property decision</small></div>
      </div>
      <div className="provenance-weights">
        <h3>Ranking weights</h3>
        {Object.entries(provenance.weights).map(([key, value]) => (
          <div className="weight-row" key={key}><span>{key}</span><div><span style={{ width: `${pct(value)}` }} /></div><b>{pct(value)}</b></div>
        ))}
      </div>
      <div className="provenance-rights">
        <h3>Data rights</h3>
        <ul>{provenance.dataRights.map((right) => <li key={right}><Icon name="check" size={12} /> {right}</li>)}</ul>
      </div>
      <div className="provenance-disclaimer"><Icon name="shield" size={15} /><span>{provenance.disclaimer}</span></div>
      <div className="provenance-foot"><span>{scenario.meta.imagery.attribution} · © OpenStreetMap contributors (ODbL)</span><span>{scenario.meta.sites} sites · {scenario.meta.areaKm2.toFixed(0)} km²</span></div>
    </Modal>
  )
}

function RouteAnnouncer() {
  const app = useApp()
  return (
    <div className="sr-only" aria-live="polite" aria-atomic="true">
      {app.mode === 'stage' ? 'Stage' : app.mode === 'watch' ? 'Watch inbox' : app.mode === 'analyst' ? 'Analyst workspace' : app.mode === 'dashboard' ? 'Pilot dashboard' : app.mode === 'method' ? 'Method and provenance' : 'Booth'} view
    </div>
  )
}

function Shell() {
  const app = useApp()
  const ui = useUi()
  const prefs = usePrefs()
  const go = useRef<string | null>(null)

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null
      const typing = target?.tagName === 'INPUT' || target?.tagName === 'TEXTAREA' || target?.tagName === 'SELECT' || target?.isContentEditable
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault()
        ui.openPalette()
        return
      }
      if (typing) return
      if (event.key === '?' && !event.metaKey && !event.ctrlKey) {
        event.preventDefault()
        ui.openAgent()
        return
      }
      if (event.key.toLowerCase() === 'g') {
        go.current = 'g'
        window.setTimeout(() => { go.current = null }, 900)
        return
      }
      if (go.current === 'g') {
        const map: Record<string, 'stage' | 'watch' | 'analyst' | 'dashboard' | 'method' | 'booth'> = {
          s: 'stage', w: 'watch', a: 'analyst', p: 'dashboard', m: 'method', b: 'booth',
        }
        const next = map[event.key.toLowerCase()]
        if (next) {
          event.preventDefault()
          app.setMode(next)
        }
        go.current = null
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [app, ui])

  if (app.loading && !app.scenario) {
    return (
      <div className="loading-screen">
        <div className="loading-mark"><Icon name="radar" size={34} /></div>
        <b>GeoResponse</b>
        <span>Loading the offline imagery pack…</span>
        <Spinner />
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
    <div className={`app app-${app.mode}`} lang={prefs.language}>
      <a className="skip-link" href="#main-content">Skip to main content</a>
      <TopBar />
      <OfflineBanner />
      <main id="main-content" className="app-main" tabIndex={-1} role="main">
        <ErrorBoundary>
          <Suspense fallback={<div className="page-state"><Spinner label="Loading workspace" /> Loading workspace…</div>}>
            {app.mode === 'stage' && <Stage />}
            {app.mode === 'watch' && <Watch />}
            {app.mode === 'analyst' && <Analyst />}
            {app.mode === 'dashboard' && <Dashboard />}
            {app.mode === 'method' && <Method />}
            {app.mode === 'booth' && <Booth />}
          </Suspense>
        </ErrorBoundary>
      </main>
      <MobileNav />
      <Report />
      <FieldOrder />
      <Provenance />
      <CommandPalette />
      <AgentPanel />
      <StyleGuide />
      <SettingsPanel />
      <RouteAnnouncer />
      <Toast />
    </div>
  )
}

export default function App() {
  return (
    <PrefsProvider>
      <UiProvider>
        <AppProvider>
          <Shell />
        </AppProvider>
      </UiProvider>
    </PrefsProvider>
  )
}
