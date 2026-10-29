import { useMemo } from 'react'
import { useApp } from '../store'
import { accessLabel, minutes } from '../lib/format'
import { exportFieldOrderPdf } from '../lib/exports'
import { Icon, Modal, SeverityChip } from './ui'

export default function FieldOrder() {
  const app = useApp()
  const scenario = app.scenario
  if (!scenario) return null

  const rows = useMemo(() => {
    const teamNames = Array.from({ length: scenario.meta.teams }, (_, i) => `Team ${i + 1}`)
    return teamNames.map((team) => {
      const siteId = Object.keys(app.assignments).find((id) => app.assignments[id] === team)
      return { team, site: siteId ? scenario.sites.find((s) => s.id === siteId) ?? null : null }
    })
  }, [app.assignments, scenario])

  const watch = scenario.sites
    .filter((site) => !app.assignments[site.id] && (app.reviews[site.id] ?? 'pending') !== 'rejected')
    .sort((a, b) => b.rankScore - a.rankScore)
    .slice(0, 6)

  const print = async () => {
    const image = await app.captureMap()
    exportFieldOrderPdf(scenario, scenario.assessmentAfterReview, app.assignments, image)
    app.notify('Field order PDF generated.', 'success')
  }

  return (
    <Modal open={app.fieldOrderOpen} onClose={() => app.openFieldOrder(false)} className="field-card" label="Field order">
      <div className="print-target">
        <div className="field-head">
          <div>
            <div className="field-eyebrow">One-page field order</div>
            <h2>FIELD ORDER · {scenario.meta.title}</h2>
            <p>
              {scenario.meta.region} · issued {scenario.fieldOrder.issuedAt} · {scenario.meta.areaKm2.toFixed(0)} km²
            </p>
          </div>
          <div className="field-time">
            <b>{minutes(scenario.meta.assessmentMinutes)}</b>
            <span>to assessment</span>
          </div>
        </div>

        <div className="field-assignments">
          {rows.map(({ team, site }) => (
            <div className="field-team" key={team}>
              <div className="field-team-name">{team}</div>
              {site ? (
                <>
                  <div className="field-team-site">
                    <b>{site.name}</b>
                    <span>
                      {site.id} · {accessLabel(site.accessStatus)} access · {site.responseMinutes} min
                    </span>
                  </div>
                  <SeverityChip severity={site.severity} small />
                </>
              ) : (
                <div className="field-team-site empty">Unassigned — hold for the next confirmed site</div>
              )}
            </div>
          ))}
        </div>

        <div className="field-body">
          <div>
            <h3>Assessment</h3>
            <p>{scenario.assessmentAfterReview.summary}</p>
            <h3 style={{ marginTop: 14 }}>Watch list</h3>
            <div className="field-watch">
              {watch.map((site) => (
                <span key={site.id}>
                  {site.id} {site.name} · {Math.round(site.confidence * 100)}%
                </span>
              ))}
            </div>
          </div>
          <div className="field-note">
            <h3>Human in the loop</h3>
            <p>{scenario.fieldOrder.signature}</p>
            <p>
              AI-assisted. Model {scenario.fieldOrder.modelVersion}. Imagery: {scenario.fieldOrder.imagery}. Do not dispatch on
              model output alone.
            </p>
            <p className="field-quote">“{scenario.hero.quote}”</p>
          </div>
        </div>

        <div className="field-foot">
          <span>{scenario.meta.imagery.attribution}</span>
          <span>© OpenStreetMap contributors (ODbL)</span>
          <span>Simulated demo pack</span>
        </div>
      </div>

      <div className="field-actions">
        <button className="btn btn-primary" onClick={print}>
          <Icon name="download" size={14} /> Field order PDF
        </button>
        <button className="btn" onClick={() => window.print()}>
          <Icon name="print" size={14} /> Print
        </button>
        <button className="btn btn-ghost" onClick={() => app.openFieldOrder(false)}>
          Back to map
        </button>
      </div>
    </Modal>
  )
}
