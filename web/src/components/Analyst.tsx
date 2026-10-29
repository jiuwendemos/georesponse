import { useEffect, useMemo, useState } from 'react'
import { useApp } from '../store'
import MapView from './MapView'
import SiteDetail from './SiteDetail'
import { ConfidenceBar, Icon, Modal, SeverityChip } from './ui'
import { compactEuro, cx, pct, reviewLabel } from '../lib/format'
import { exportAssessmentPdf, exportGeoJson } from '../lib/exports'
import { verifyAudit } from '../lib/audit'

type Filter = 'all' | 'red' | 'orange' | 'pending' | 'approved' | 'rejected'

export default function Analyst() {
  const app = useApp()
  const scenario = app.scenario
  const [filter, setFilter] = useState<Filter>('all')
  const [query, setQuery] = useState('')
  const [auditOpen, setAuditOpen] = useState(false)
  const [auditState, setAuditState] = useState<{ ok: boolean; message: string } | null>(null)

  const selected = scenario?.sites.find((site) => site.id === app.selectedId)
  const selectedRank = app.ranked.find((item) => item.site.id === selected?.id)?.rank ?? 0

  useEffect(() => {
    if (scenario) {
      app.setTime(scenario.timeline.end)
      const top = app.ranked[0]
      if (top && !app.selectedId) app.selectSite(top.site.id)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scenario?.meta.id])

  const filtered = useMemo(() => {
    return app.ranked.filter(({ site }) => {
      const status = app.reviews[site.id] ?? 'pending'
      if (filter === 'red' && site.severity !== 'red') return false
      if (filter === 'orange' && site.severity !== 'orange') return false
      if (filter === 'pending' && status !== 'pending') return false
      if (filter === 'approved' && status !== 'approved') return false
      if (filter === 'rejected' && status !== 'rejected') return false
      if (query && !`${site.id} ${site.name} ${site.kindLabel}`.toLowerCase().includes(query.toLowerCase())) return false
      return true
    })
  }, [app.ranked, app.reviews, filter, query])

  if (!scenario) return null

  const rejected = Object.values(app.reviews).filter((status) => status === 'rejected').length
  const approved = Object.values(app.reviews).filter((status) => status === 'approved').length
  const flagged = Object.values(app.reviews).filter((status) => status === 'flagged').length

  const verify = async () => {
    const result = await verifyAudit(scenario.meta.id)
    setAuditState({ ok: result.ok, message: result.message })
  }

  return (
    <div className="analyst">
      <MapView variant="analyst" />

      <div className="analyst-toolbar">
        <div>
          <div className="eyebrow">
            <span className="dot" /> Analyst workspace
          </div>
          <h1>
            {scenario.meta.title} <span>{scenario.meta.region}</span>
          </h1>
        </div>
        <div className="analyst-stats">
          <span><b>{app.ranked.length}</b> active</span>
          <span><b>{approved}</b> approved</span>
          <span><b>{flagged}</b> flagged</span>
          <span><b>{rejected}</b> rejected</span>
        </div>
        <div className="analyst-actions">
          <button className="btn" onClick={() => setAuditOpen(true)}>
            <Icon name="shield" size={14} /> Audit trail
          </button>
          <button
            className="btn"
            onClick={() => {
              exportGeoJson(scenario, app.reviews, app.notes, app.assignments)
              app.notify('GeoJSON exported.', 'success')
            }}
          >
            <Icon name="download" size={14} /> GeoJSON
          </button>
          <button
            className="btn btn-primary"
            onClick={async () => {
              const assessment = scenario.assessmentAfterReview
              exportAssessmentPdf(scenario, assessment, app.ranked, app.reviews, app.notes, await app.captureMap())
              app.notify('Assessment PDF generated.', 'success')
            }}
          >
            <Icon name="download" size={14} /> PDF
          </button>
        </div>
      </div>

      <aside className="hud analyst-list">
        <div className="list-head">
          <div>
            <span className="eyebrow">Ranked queue</span>
            <h2>{filtered.length} sites</h2>
          </div>
          <button className="btn btn-sm" onClick={() => app.batchApprove(scenario.reviewPolicy.batchThreshold)}>
            <Icon name="check" size={12} /> Approve ≥{pct(scenario.reviewPolicy.batchThreshold)}
          </button>
        </div>
        <input
          className="search"
          placeholder="Search site, id or asset…"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
        <div className="filter-row">
          {(['all', 'red', 'orange', 'pending', 'approved', 'rejected'] as Filter[]).map((value) => (
            <button key={value} className={cx('filter-chip', filter === value && 'active')} onClick={() => setFilter(value)}>
              {value === 'all' ? 'All' : value === 'red' ? 'High' : value === 'orange' ? 'Watch' : value[0].toUpperCase() + value.slice(1)}
            </button>
          ))}
        </div>

        <div className="site-list">
          {filtered.map(({ site, rank, score }) => {
            const review = app.reviews[site.id] ?? 'pending'
            const team = app.assignments[site.id]
            return (
              <button
                key={site.id}
                className={cx('site-row', app.selectedId === site.id && 'active', `review-${review}`)}
                onClick={() => app.selectSite(site.id)}
              >
                <span className="site-rank">{rank}</span>
                <span className="site-main">
                  <span className="site-name">{site.name}</span>
                  <span className="site-meta">
                    {site.id} · {compactEuro(site.valueEur)} · {site.responseMinutes}′
                    {team && <em> · {team}</em>}
                    {review !== 'pending' && <em className={`review-text review-${review}`}> · {reviewLabel(review)}</em>}
                  </span>
                  <ConfidenceBar value={site.confidence} />
                </span>
                <span className="site-side">
                  <SeverityChip severity={site.severity} small />
                  <span className="site-score">{score.toFixed(2)}</span>
                </span>
              </button>
            )
          })}
          {!filtered.length && <div className="empty-list">No sites match this filter.</div>}
        </div>

        <div className="list-foot">
          <span>{app.workCount} reviewed</span>
          <span>Cloud screen 30%</span>
          <span>Model {scenario.meta.model}</span>
        </div>
      </aside>

      {selected ? (
        <SiteDetail site={selected} rank={selectedRank} mode="analyst" />
      ) : (
        <div className="hud analyst-empty">
          <Icon name="pin" size={22} />
          <b>Select a location</b>
          <span>The map, the queue and the evidence stay in sync.</span>
        </div>
      )}

      <Modal open={auditOpen} onClose={() => setAuditOpen(false)} className="audit-card" label="Audit trail">
        <h2>Audit trail</h2>
        <p className="audit-sub">
          Hash-chained review decisions. Imagery, model version, analyst, corrections. {scenario.meta.model} ·{' '}
          {scenario.meta.imagery.source}
        </p>
        <div className="audit-actions">
          <button className="btn btn-primary" onClick={verify}>
            Verify chain
          </button>
          <a
            className="btn"
            href={`data:application/json,${encodeURIComponent(JSON.stringify(app.audit, null, 2))}`}
            download={`georesponse-audit-${scenario.meta.id}.json`}
          >
            <Icon name="download" size={14} /> Export events
          </a>
          {auditState && <span className={cx('audit-status', auditState.ok ? 'ok' : 'bad')}>{auditState.message}</span>}
        </div>
        <div className="audit-list">
          {app.audit.length ? (
            [...app.audit].reverse().map((event) => (
              <div className="audit-row" key={event.hash}>
                <span className="audit-dot" />
                <div>
                  <b>{event.action}</b>
                  <span>
                    {new Date(event.at).toLocaleString()} · {event.siteId ?? 'event'} · {event.analyst}
                  </span>
                  {event.detail && Object.keys(event.detail).length > 0 && (
                    <small>{Object.entries(event.detail).map(([key, value]) => `${key}: ${String(value)}`).join(' · ')}</small>
                  )}
                </div>
                <code>{event.hash.slice(0, 10)}</code>
              </div>
            ))
          ) : (
            <div className="empty-list">No decisions yet. Approve, flag or reject a site to start the chain.</div>
          )}
        </div>
      </Modal>
    </div>
  )
}
