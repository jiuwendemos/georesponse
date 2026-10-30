import { useMemo } from 'react'
import { useApp } from '../store'
import { compactEuro, euro, minutes, number, pct } from '../lib/format'
import { Icon, Modal, SeverityChip } from './ui'
import { exportAssessmentPdf, exportAssessmentJson, exportGeoJson } from '../lib/exports'
import type { Assessment } from '../types'

function compose(scenario: NonNullable<ReturnType<typeof useApp>['scenario']>, ranked: ReturnType<typeof useApp>['ranked'], reviews: Record<string, string>): Assessment {
  const rejectedCount = Object.values(reviews).filter((status) => status === 'rejected').length
  const area = scenario.meta.areaKm2
  const totalValue = ranked.reduce((sum, item) => sum + item.site.valueEur, 0)
  const totalPeople = ranked.reduce((sum, item) => sum + item.site.population, 0)
  const top = ranked.slice(0, 3)
  const topNames = top.map((item) => `${item.site.name} (${item.site.id})`).join(', ')
  const summary = `${scenario.meta.title} affects ${area.toFixed(0)} km². ${ranked.length} priority sites remain after review; ${rejectedCount} finding(s) rejected by an analyst. ${topNames || 'No sites'} carry ${euro(totalValue)} of exposed value and ${number(totalPeople)} people within 700 m. ${scenario.meta.teams} response teams are allocated by urgency, access and value at risk.`
  const findings = ranked.map((item) => ({
    id: item.site.id,
    name: item.site.name,
    rank: item.rank,
    score: item.score,
    severity: item.site.severity,
    confidence: item.site.confidence,
    confidenceLabel: item.site.confidence >= 0.85 ? 'high' : item.site.confidence >= 0.65 ? 'medium' : 'low',
    changeExtentM2: item.site.changeExtentM2,
    valueEur: item.site.valueEur,
    population: item.site.population,
    access: item.site.accessStatus,
    review: reviews[item.site.id] ?? 'pending',
    imagery: item.site.evidence,
    modelVersion: scenario.meta.model,
  }))
  return {
    ...scenario.assessmentAfterReview,
    summary,
    headline: top[0]
      ? `The highest-ranked site is ${top[0].site.name} (${top[0].site.id}), severity ${top[0].site.severity}, confidence ${pct(top[0].site.confidence)}.`
      : 'No sites remain after review.',
    metrics: {
      sites: ranked.length,
      rejected: rejectedCount,
      areaKm2: area,
      exposedValueEur: totalValue,
      population: totalPeople,
      assessmentMinutes: scenario.meta.assessmentMinutes,
      baselineMinutes: scenario.meta.baselineMinutes,
    },
    findings,
  }
}

export default function Report() {
  const app = useApp()
  const scenario = app.scenario
  const assessment = useMemo(
    () => (scenario ? compose(scenario, app.ranked, app.reviews) : null),
    [scenario, app.ranked, app.reviews],
  )
  if (!scenario || !assessment) return null

  const downloadPdf = async () => {
    const image = await app.captureMap()
    await exportAssessmentPdf(scenario, assessment, app.ranked, app.reviews, app.notes, image)
    app.notify('Assessment PDF generated.', 'success')
  }

  return (
    <Modal open={app.reportOpen} onClose={() => app.openReport(false)} className="report-card" label="Assessment">
      <div className="report-head">
        <div>
          <div className="report-eyebrow">
            <span className="live-dot" /> Assessment ready · {minutes(scenario.meta.assessmentMinutes)}
          </div>
          <h2>{scenario.meta.title}</h2>
          <p>
            {scenario.meta.region} · {scenario.meta.eventDate} {scenario.meta.eventTime} · {scenario.meta.areaKm2.toFixed(0)} km²
          </p>
        </div>
        <div className="report-quote">
          “{scenario.hero.quote}”
        </div>
      </div>

      <div className="report-metrics">
        <div>
          <b>{assessment.metrics.sites}</b>
          <span>priority sites</span>
        </div>
        <div>
          <b>{assessment.metrics.rejected}</b>
          <span>rejected by analyst</span>
        </div>
        <div>
          <b>{compactEuro(assessment.metrics.exposedValueEur)}</b>
          <span>value at risk</span>
        </div>
        <div>
          <b>{minutes(scenario.meta.assessmentMinutes)}</b>
          <span>to assessment</span>
        </div>
        <div>
          <b>{number(assessment.metrics.population)}</b>
          <span>people in footprint</span>
        </div>
      </div>

      <p className="report-summary">{assessment.summary}</p>

      <div className="report-grid">
        <div>
          <h3>Top findings</h3>
          <ol className="report-list">
            {app.ranked.slice(0, 6).map((item) => (
              <li key={item.site.id} onClick={() => app.selectSite(item.site.id)}>
                <span className="report-rank">{item.rank}</span>
                <div>
                  <b>{item.site.name}</b>
                  <small>
                    {item.site.id} · {item.site.accessStatus} access · {pct(item.site.confidence)} confidence
                  </small>
                </div>
                <SeverityChip severity={item.site.severity} small />
              </li>
            ))}
          </ol>
        </div>
        <div>
          <h3>Agent trace</h3>
          <ol className="trace-list">
            {assessment.trace.map((step) => (
              <li key={step.step}>
                <span>{step.step}</span>
                <div>
                  <b>{step.tool}</b>
                  <small>{step.detail}</small>
                </div>
              </li>
            ))}
          </ol>
        </div>
      </div>

      <details className="report-limits">
        <summary>Limitations & provenance</summary>
        <ul>
          {assessment.limitations.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
        <p>{assessment.disclosure}</p>
      </details>

      <div className="report-actions">
        <button className="btn btn-primary" onClick={() => app.openFieldOrder(true)}>
          <Icon name="print" size={14} /> Open field order
        </button>
        <button className="btn" onClick={downloadPdf}>
          <Icon name="download" size={14} /> Assessment PDF
        </button>
        <button
          className="btn"
          onClick={() => {
            exportGeoJson(scenario, app.reviews, app.notes, app.assignments)
            app.notify('GeoJSON findings and change overlay exported.', 'success')
          }}
        >
          <Icon name="download" size={14} /> GeoJSON
        </button>
        <button
          className="btn btn-ghost"
          onClick={() => {
            exportAssessmentJson(scenario, assessment, app.reviews, app.notes, app.assignments)
            app.notify('Assessment JSON exported with provenance.', 'success')
          }}
        >
          JSON
        </button>
      </div>
      <div className="report-foot">
        Human review required · Model {scenario.meta.model} · {scenario.meta.imagery.source} · {scenario.meta.imagery.attribution}
      </div>
    </Modal>
  )
}
