import { useEffect, useMemo, useState } from 'react'
import { useApp } from '../store'
import { asset, dataPath, loadJson } from '../lib/data'
import type { MonitoringData, PilotData, RegionalEvents } from '../types'
import { compactEuro, cx, minutes, number, pct } from '../lib/format'
import { Icon } from './ui'

function LineChart({ data }: { data: { date: string; precision: number; recall: number }[] }) {
  const width = 560
  const height = 170
  const pad = { left: 30, right: 12, top: 14, bottom: 22 }
  const xs = data.map((_, i) => pad.left + (i / Math.max(1, data.length - 1)) * (width - pad.left - pad.right))
  const y = (value: number) => pad.top + (1 - value) * (height - pad.top - pad.bottom)
  const path = (key: 'precision' | 'recall') =>
    data.map((item, i) => `${i === 0 ? 'M' : 'L'}${xs[i].toFixed(1)},${y(item[key]).toFixed(1)}`).join(' ')
  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="line-chart" role="img" aria-label="Precision and recall trend">
      {[0.6, 0.8, 1].map((tick) => (
        <g key={tick}>
          <line x1={pad.left} x2={width - pad.right} y1={y(tick)} y2={y(tick)} stroke="#1c3541" strokeWidth={1} />
          <text x={pad.left - 6} y={y(tick) + 3} textAnchor="end" fill="#5f7782" fontSize={8}>
            {Math.round(tick * 100)}%
          </text>
        </g>
      ))}
      <path d={path('recall')} fill="none" stroke="#a78bfa" strokeWidth={2} strokeLinecap="round" />
      <path d={path('precision')} fill="none" stroke="#22d3ee" strokeWidth={2} strokeLinecap="round" />
      {data.map((item, i) => (
        <g key={item.date}>
          <circle cx={xs[i]} cy={y(item.precision)} r={2.6} fill="#22d3ee" />
          <circle cx={xs[i]} cy={y(item.recall)} r={2.6} fill="#a78bfa" />
          <text x={xs[i]} y={height - 6} textAnchor="middle" fill="#5f7782" fontSize={7.5}>
            {item.date.slice(5)}
          </text>
        </g>
      ))}
      <g transform={`translate(${width - 160}, 8)`}>
        <rect x={0} y={0} width={6} height={6} fill="#22d3ee" />
        <text x={10} y={6} fill="#9fb4bd" fontSize={8}>Precision</text>
        <rect x={70} y={0} width={6} height={6} fill="#a78bfa" />
        <text x={80} y={6} fill="#9fb4bd" fontSize={8}>Recall</text>
      </g>
    </svg>
  )
}

function RegionalMap({ data }: { data: RegionalEvents }) {
  const [west, south, east, north] = data.bbox
  const project = (lon: number, lat: number) => ({
    x: 20 + ((lon - west) / (east - west)) * 560,
    y: 20 + ((north - lat) / (north - south)) * 300,
  })
  const colors = { red: '#fb7185', orange: '#fbbf24', yellow: '#facc15' }
  return (
    <svg viewBox="0 0 600 340" className="regional-map" role="img" aria-label="Regional events by severity">
      <defs>
        <linearGradient id="region-bg" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#071821" />
          <stop offset="1" stopColor="#0b2530" />
        </linearGradient>
      </defs>
      <rect width={600} height={340} rx={10} fill="url(#region-bg)" />
      {Array.from({ length: 11 }, (_, i) => (
        <g key={i}>
          <line x1={20 + i * 56} x2={20 + i * 56} y1={20} y2={320} stroke="#12313d" strokeWidth={1} />
          <line x1={20} x2={580} y1={20 + i * 30} y2={20 + i * 30} stroke="#12313d" strokeWidth={1} />
        </g>
      ))}
      <path
        d="M40 240 C140 210 170 260 250 225 C330 190 380 235 470 205 C510 192 545 200 570 190"
        fill="none"
        stroke="#0d4a5c"
        strokeWidth={9}
        opacity={0.7}
        strokeLinecap="round"
      />
      <path
        d="M40 240 C140 210 170 260 250 225 C330 190 380 235 470 205 C510 192 545 200 570 190"
        fill="none"
        stroke="#22d3ee"
        strokeWidth={1.6}
        opacity={0.35}
      />
      {data.events.map((event) => {
        const { x, y } = project(event.lon, event.lat)
        return (
          <g key={event.id} className="region-event">
            <circle cx={x} cy={y} r={6 + event.sites / 2.4} fill={colors[event.severity]} opacity={0.16} />
            <circle cx={x} cy={y} r={4} fill={colors[event.severity]} stroke="#061018" strokeWidth={1.4} />
            <text x={x + 9} y={y + 3} fill="#c6dbe3" fontSize={7.5}>
              {event.name}
            </text>
            <text x={x + 9} y={y + 11} fill="#5f7782" fontSize={6.5}>
              {event.sites} sites · {event.date.slice(5)}
            </text>
          </g>
        )
      })}
      <g transform="translate(24, 312)">
        <text fill="#5f7782" fontSize={7}>REGIONAL MAP · EVENTS BY SEVERITY · 2026</text>
      </g>
    </svg>
  )
}

export default function Dashboard() {
  const app = useApp()
  const [pilot, setPilot] = useState<PilotData | null>(null)
  const [regional, setRegional] = useState<RegionalEvents | null>(null)
  const [monitoring, setMonitoring] = useState<MonitoringData | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let alive = true
    Promise.all([
      loadJson<PilotData>(dataPath('pilot.json')),
      loadJson<RegionalEvents>(dataPath('regional-events.json')),
      loadJson<MonitoringData>(dataPath('monitoring.json')),
    ])
      .then(([pilotData, regionalData, monitoringData]) => {
        if (!alive) return
        setPilot(pilotData)
        setRegional(regionalData)
        setMonitoring(monitoringData)
      })
      .catch((err) => alive && setError(err instanceof Error ? err.message : 'Could not load pilot data'))
    return () => {
      alive = false
    }
  }, [])

  const reasons = useMemo(() => pilot?.byReason ?? [], [pilot])

  if (error) return <div className="page-state">{error}</div>
  if (!pilot || !regional || !monitoring) return <div className="page-state">Loading pilot evidence…</div>

  return (
    <div className="page dashboard">
      <header className="page-head">
        <div>
          <div className="eyebrow">
            <span className="dot" /> Pilot evidence · {pilot.generatedAt.slice(0, 10)}
          </div>
          <h1>Days became hours. Here is the audit trail.</h1>
          <p>
            One property insurer, six storm and flood events, adjuster-confirmed outcomes. The numbers below are the demo
            pack; the measurement functions are the same ones used in a real pilot.
          </p>
        </div>
        <div className="page-head-actions">
          <button className="btn" onClick={() => void app.saveOffline()}>
            <Icon name="download" size={14} /> Save offline pack
          </button>
          <a className="btn btn-primary" href={asset('data/precision-recall.json')} target="_blank" rel="noreferrer">
            <Icon name="chart" size={14} /> Accuracy report
          </a>
        </div>
      </header>

      <section className="kpi-grid">
        <div className="kpi">
          <span>Time to assessment</span>
          <b>{minutes(pilot.timeToAssessment.georesponseMinutes)}</b>
          <em>from {minutes(pilot.timeToAssessment.manualMinutes)} manual</em>
          <div className="kpi-bar"><span style={{ width: `${100 - pilot.timeToAssessment.savedPct}%` }} /></div>
        </div>
        <div className="kpi">
          <span>Precision</span>
          <b>{pct(pilot.summary.precision)}</b>
          <em>{pilot.summary.confirmed} confirmed of {pilot.summary.detected} detected</em>
          <div className="kpi-bar"><span style={{ width: `${pilot.summary.precision * 100}%` }} /></div>
        </div>
        <div className="kpi">
          <span>Analyst hours saved</span>
          <b>{pilot.summary.analystHoursSaved}h</b>
          <em>{compactEuro(pilot.cost.savedEur)} at {pilot.cost.analystHourlyEur} EUR/h</em>
          <div className="kpi-bar"><span style={{ width: '68%' }} /></div>
        </div>
        <div className="kpi">
          <span>False positives</span>
          <b>{pilot.summary.falsePositives}</b>
          <em>{number(pilot.summary.claims)} claims · {pilot.summary.events} events</em>
          <div className="kpi-bar warn"><span style={{ width: `${(pilot.summary.falsePositives / pilot.summary.detected) * 900}%` }} /></div>
        </div>
        <div className="kpi">
          <span>Review SLA</span>
          <b>4h</b>
          <em>human approval before any claim action</em>
          <div className="kpi-bar"><span style={{ width: '82%' }} /></div>
        </div>
      </section>

      <section className="dash-grid">
        <div className="card chart-card">
          <div className="card-head">
            <div>
              <span className="eyebrow">Accuracy trend</span>
              <h2>Precision and recall</h2>
            </div>
            <span className="card-tag">adjuster-confirmed</span>
          </div>
          <LineChart data={pilot.summary.accuracyTrend} />
          <p className="card-note">Precision = confirmed / detected. Recall = confirmed / claims. Every point is a reviewed event.</p>
        </div>

        <div className="card">
          <div className="card-head">
            <div>
              <span className="eyebrow">Time saved</span>
              <h2>Manual vs GeoResponse</h2>
            </div>
          </div>
          <div className="time-compare">
            <div className="compare-row">
              <span>Manual</span>
              <div className="compare-track"><span className="manual" style={{ width: '100%' }} /></div>
              <b>{minutes(pilot.timeToAssessment.manualMinutes)}</b>
            </div>
            <div className="compare-row">
              <span>GeoResponse</span>
              <div className="compare-track">
                <span className="auto" style={{ width: `${(pilot.timeToAssessment.georesponseMinutes / pilot.timeToAssessment.manualMinutes) * 100}%` }} />
              </div>
              <b>{minutes(pilot.timeToAssessment.georesponseMinutes)}</b>
            </div>
          </div>
          <div className="saved-callout">
            <b>{pilot.timeToAssessment.savedPct}%</b> faster. That is the 42 minutes on stage, not a projection.
          </div>
          <p className="card-note">{pilot.disclaimer}</p>
        </div>

        <div className="card map-card">
          <div className="card-head">
            <div>
              <span className="eyebrow">Regional map</span>
              <h2>Events by severity</h2>
            </div>
            <span className="card-tag">{regional.summary.events} events · {regional.summary.sites} sites</span>
          </div>
          <RegionalMap data={regional} />
        </div>

        <div className="card">
          <div className="card-head">
            <div>
              <span className="eyebrow">Monitoring</span>
              <h2>Change alerts</h2>
            </div>
            <span className="card-tag">{monitoring.summary.alerts} alerts</span>
          </div>
          <div className="monitor-list">
            {monitoring.alerts.map((alert) => {
              const region = monitoring.regions.find((r) => r.id === alert.regionId)
              return (
                <div className={cx('monitor-row', alert.alert && 'alert')} key={alert.regionId}>
                  <span className="monitor-dot" />
                  <div>
                    <b>{region?.name ?? alert.regionId}</b>
                    <small>
                      {(alert.observedChange * 100).toFixed(0)}% change · z {alert.zScore.toFixed(1)} · baseline{' '}
                      {(alert.baseline.mean * 100).toFixed(0)}%
                    </small>
                  </div>
                  <span className={cx('monitor-state', alert.severity)}>{alert.alert ? 'ALERT' : 'normal'}</span>
                </div>
              )
            })}
          </div>
          <p className="card-note">Recurring monitoring against a 6-period baseline. Alerts above 2.5σ and 6% change.</p>
        </div>
      </section>

      <section className="dash-grid wide">
        <div className="card">
          <div className="card-head">
            <div>
              <span className="eyebrow">False-positive log</span>
              <h2>Why the model was wrong</h2>
            </div>
            <span className="card-tag">by reason</span>
          </div>
          <div className="reason-bars">
            {reasons.map((reason) => (
              <div className="reason-row" key={reason.category}>
                <span>{reason.category}</span>
                <div className="reason-track">
                  <span style={{ width: `${(reason.count / Math.max(...reasons.map((r) => r.count))) * 100}%` }} />
                </div>
                <b>{reason.count}</b>
              </div>
            ))}
          </div>
          <table className="data-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Reason</th>
                <th>Location</th>
                <th>Conf.</th>
                <th>Review</th>
              </tr>
            </thead>
            <tbody>
              {pilot.falsePositiveLog.map((item) => (
                <tr key={item.id}>
                  <td>{item.id}</td>
                  <td>{item.reason}</td>
                  <td>{item.location}</td>
                  <td>{pct(item.confidence)}</td>
                  <td><span className={cx('review-pill', `review-${item.review}`)}>{item.review}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="card offer-card">
          <div className="card-head">
            <div>
              <span className="eyebrow">Next step</span>
              <h2>Pilot in 90 days</h2>
            </div>
          </div>
          <p>
            One insurer, one storm or flood event, one region. Run the AI assessment in parallel with the manual process and
            compare results.
          </p>
          <ul className="offer-list">
            <li>Imagery pipeline for the customer’s event</li>
            <li>Ranked site list with confidence and value at risk</li>
            <li>Claims first-notice assessment, human-signed</li>
            <li>Accuracy, false-positive and time-saved report</li>
            <li>On-site or private-cloud deployment option</li>
          </ul>
          <div className="offer-actions">
            <a className="btn btn-primary" href="mailto:pilot@georesponse.example?subject=GeoResponse%20pilot">
              Book a pilot
            </a>
            <button className="btn btn-ghost" onClick={() => app.openProvenance(true)}>
              Read the method
            </button>
          </div>
          <p className="card-note">Fixed pilot fee credited against the annual subscription. Human review always on.</p>
        </div>
      </section>

      <footer className="page-foot">
        <span>{pilot.disclaimer}</span>
        <span>Model {app.scenario?.meta.model} · {pilot.history[0]?.region} pilot</span>
      </footer>
    </div>
  )
}
