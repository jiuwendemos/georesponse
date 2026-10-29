import { useEffect, useState } from 'react'
import { useApp } from '../store'
import { asset } from '../lib/data'
import { cx, hazardLabel } from '../lib/format'
import { Icon, Modal } from './ui'
import type { Scenario } from '../types'

async function buildKitImage(scenario: Scenario): Promise<string | null> {
  try {
    const image = new Image()
    image.src = asset(scenario.imageryPair.after)
    await image.decode()
    const canvas = document.createElement('canvas')
    canvas.width = 1400
    canvas.height = 875
    const context = canvas.getContext('2d')
    if (!context) return null
    context.drawImage(image, 0, 0, canvas.width, canvas.height)
    const [west, south, east, north] = scenario.meta.bbox
    const project = (lon: number, lat: number) => [
      ((lon - west) / (east - west)) * canvas.width,
      ((north - lat) / (north - south)) * canvas.height,
    ] as const
    const colors: Record<string, string> = { red: '#fb7185', orange: '#fbbf24', yellow: '#facc15' }
    scenario.sites.forEach((site) => {
      const [x, y] = project(site.lon, site.lat)
      context.beginPath()
      context.arc(x, y, 11, 0, Math.PI * 2)
      context.fillStyle = colors[site.severity]
      context.fill()
      context.lineWidth = 2.5
      context.strokeStyle = 'rgba(4,16,26,0.9)'
      context.stroke()
      context.fillStyle = '#041014'
      context.font = '700 11px ui-monospace, monospace'
      context.textAlign = 'center'
      context.textBaseline = 'middle'
      context.fillText(String(site.rank), x, y + 0.5)
    })
    const [dx, dy] = project(scenario.hero.depot[0], scenario.hero.depot[1])
    context.save()
    context.translate(dx, dy)
    context.rotate(Math.PI / 4)
    context.fillStyle = '#4ade80'
    context.fillRect(-6, -6, 12, 12)
    context.restore()
    context.fillStyle = 'rgba(4,16,26,0.75)'
    context.fillRect(0, canvas.height - 28, canvas.width, 28)
    context.fillStyle = '#8ca3ad'
    context.font = '12px ui-monospace, monospace'
    context.textAlign = 'left'
    context.fillText('GeoResponse · simulated pack · human review required · © OpenStreetMap contributors · © Copernicus Sentinel data', 12, canvas.height - 10)
    return canvas.toDataURL('image/png')
  } catch {
    return null
  }
}

const SCRIPT = [
  { t: '0:00–0:10', label: 'Cold open', line: '“14:32. Forty square kilometres under water. Eighteen places that matter. Three teams.”' },
  { t: '0:10–0:25', label: 'First touch', line: 'Scrub to 18:00. “The flood edge is moving east. The answer changes with the clock.”' },
  { t: '0:25–0:40', label: 'Agent ranks', line: 'Open the top site. “Road, substation, people. That is why it ranks first.”' },
  { t: '0:40–0:55', label: 'Trust beat', line: '“The model was confident. The analyst was right. This is why a human signs the assessment.”' },
  { t: '0:55–1:10', label: 'Audience choice', line: '“Team 3: the substation or the housing block? Both are defensible. You decide.”' },
  { t: '1:10–1:20', label: 'The reveal', line: 'Zoom out. “40 square kilometres. 18 sites. 42 minutes. Here is the field order.”' },
  { t: '1:20–1:30', label: 'The line', line: '“We knew where to send the teams before the second coffee.”' },
]

export default function Booth() {
  const app = useApp()
  const [seconds, setSeconds] = useState(180)
  const [running, setRunning] = useState(false)
  const [scriptOpen, setScriptOpen] = useState(false)
  const [kitOpen, setKitOpen] = useState(false)
  const [kitImage, setKitImage] = useState<string | null>(null)

  useEffect(() => {
    if (!running) return
    const timer = window.setInterval(() => {
      setSeconds((value) => {
        if (value <= 1) {
          setRunning(false)
          return 0
        }
        return value - 1
      })
    }, 1000)
    return () => window.clearInterval(timer)
  }, [running])

  useEffect(() => {
    if (!kitOpen) return
    const timer = window.setTimeout(async () => {
      if (app.scenario) setKitImage(await buildKitImage(app.scenario))
    }, 300)
    return () => window.clearTimeout(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kitOpen])

  const resetTimer = () => {
    setRunning(false)
    setSeconds(180)
  }

  const start = (id: string) => {
    app.selectScenario(id)
    app.setMode('stage')
    resetTimer()
  }

  const time = `${String(Math.floor(seconds / 60)).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`

  return (
    <div className="page booth">
      <header className="page-head">
        <div>
          <div className="eyebrow">
            <span className="dot" /> Booth mode
          </div>
          <h1>One event. One decision. Three minutes.</h1>
          <p>
            Pick a scenario, reset in under five seconds, run the same deterministic story. No network, no login, no live
            download. The QR points at the playable demo, not a signup form.
          </p>
        </div>
        <div className="page-head-actions">
          <button className="btn" onClick={() => setScriptOpen(true)}>
            <Icon name="book" size={14} /> 90-second script
          </button>
          <button
            className="btn"
            onClick={() => {
              setKitImage(null)
              setKitOpen(true)
            }}
          >
            <Icon name="print" size={14} /> Print map & tokens
          </button>
          <button className="btn btn-primary" onClick={() => void app.saveOffline()}>
            <Icon name="download" size={14} /> Offline pack
          </button>
        </div>
      </header>

      <section className="booth-hero">
        <div className="booth-timer">
          <span className="eyebrow">Run clock</span>
          <b>{time}</b>
          <div className="timer-actions">
            <button className="btn btn-primary" onClick={() => setRunning((value) => !value)}>
              <Icon name={running ? 'pause' : 'play'} size={14} /> {running ? 'Pause' : 'Start'}
            </button>
            <button className="btn" onClick={resetTimer}>
              <Icon name="reset" size={14} /> Reset
            </button>
          </div>
          <div className="timer-track">
            <span style={{ width: `${(1 - seconds / 180) * 100}%` }} />
          </div>
        </div>
        <div className="booth-steps">
          {SCRIPT.map((beat) => (
            <div className="booth-step" key={beat.label}>
              <span>{beat.t}</span>
              <b>{beat.label}</b>
              <p>{beat.line}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="scenario-grid">
        {app.index?.scenarios.map((entry) => (
          <article className={cx('scenario-card', app.scenario?.meta.id === entry.id && 'active')} key={entry.id}>
            <div className="scenario-thumb">
              <img src={asset(entry.thumb)} alt={`${entry.title} basemap`} loading="lazy" />
              <span className="scenario-hazard">{hazardLabel(entry.hazard)}</span>
              <span className="scenario-sites">{entry.sites} sites</span>
            </div>
            <div className="scenario-body">
              <h2>{entry.title}</h2>
              <p>{entry.subtitle}</p>
              <div className="scenario-meta">
                <span>{entry.region}</span>
                <span>{entry.date}</span>
                <span>{entry.teams} teams</span>
              </div>
              <p className="scenario-quote">“{entry.quote}”</p>
              <div className="scenario-actions">
                <button className="btn btn-primary" onClick={() => start(entry.id)}>
                  Start 3-min run <Icon name="arrow" size={13} />
                </button>
                <button
                  className="btn btn-ghost"
                  onClick={() => {
                    app.selectScenario(entry.id)
                  }}
                >
                  Load only
                </button>
              </div>
            </div>
          </article>
        ))}
      </section>

      <section className="booth-notes">
        <div className="card">
          <span className="eyebrow">Stagecraft</span>
          <h2>Props & fallback</h2>
          <ul>
            <li>Printed A1 map with three magnetic team tokens; the screen mirrors it.</li>
            <li>One low flood/rain bed. A single ping when a site flips to high risk. Silence under the trust beat.</li>
            <li>Amber for watch, red for high risk, cyan for assigned teams.</li>
            <li>Reset: <kbd>R</kbd> in the stage view, under five seconds.</li>
            <li>Fallback: offline pack loaded on a second laptop. No cable, no CDN, no account.</li>
          </ul>
        </div>
        <div className="card">
          <span className="eyebrow">Data provenance</span>
          <h2>What the audience is seeing</h2>
          <p>
            The bundled raster is a deterministic simulation, clearly labelled in-app. Sentinel-2 is the production
            before-image source; commercial and drone imagery require a licence even for a public stage.
          </p>
          <div className="booth-links">
            <button className="btn btn-ghost" onClick={() => app.setMode('method')}>
              Read the method
            </button>
            <a className="btn btn-ghost" href="mailto:pilot@georesponse.example?subject=GeoResponse%20pilot">
              Pilot in 90 days
            </a>
          </div>
        </div>
      </section>

      <Modal open={kitOpen} onClose={() => setKitOpen(false)} className="kit-card" label="Stage kit">
        <div className="print-target stage-kit">
          <div className="kit-head">
            <div>
              <div className="field-eyebrow">A1 printed map · magnetic tokens</div>
              <h2>GeoResponse stage kit — {app.scenario?.meta.title}</h2>
              <p>Print the map at A1. Cut out the three tokens. The screen mirrors this layout.</p>
            </div>
            <div className="kit-brand"><Icon name="radar" size={22} /> GeoResponse</div>
          </div>
          {kitImage ? <img className="kit-map" src={kitImage} alt="Stage map" /> : <div className="kit-map placeholder">Capturing map…</div>}
          <div className="kit-tokens">
            {['Team 1', 'Team 2', 'Team 3'].map((team) => (
              <div className="kit-token" key={team}>
                <span className="kit-token-ring" />
                <b>{team}</b>
              </div>
            ))}
            <div className="kit-legend">
              <span>Amber = watch</span>
              <span>Red = high risk</span>
              <span>Cyan = flood edge</span>
              <span>Green = assigned</span>
            </div>
          </div>
          <p className="kit-foot">© OpenStreetMap contributors (ODbL) · © Copernicus Sentinel data (simulated demo pack) · Human review required.</p>
        </div>
        <div className="field-actions">
          <button className="btn btn-primary" onClick={() => window.print()}>
            <Icon name="print" size={14} /> Print kit
          </button>
          <button className="btn btn-ghost" onClick={() => setKitOpen(false)}>Close</button>
        </div>
      </Modal>

      <Modal open={scriptOpen} onClose={() => setScriptOpen(false)} className="script-card" label="90-second script">
        <h2>The 90-second script</h2>
        <p className="audit-sub">Word-for-word for the first 20 seconds; beats are fixed, wording can breathe.</p>
        <div className="script-list">
          {SCRIPT.map((beat) => (
            <div className="script-row" key={beat.label}>
              <span>{beat.t}</span>
              <div>
                <b>{beat.label}</b>
                <p>{beat.line}</p>
              </div>
            </div>
          ))}
        </div>
        <div className="script-foot">
          <span>Acceptance: 5 strangers, 4 can explain the decision; reset under 5 s; network cable unplugged.</span>
        </div>
      </Modal>
    </div>
  )
}
