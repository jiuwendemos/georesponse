import { useMemo, useState } from 'react'
import { useApp } from '../store'
import { asset } from '../lib/data'
import { accessLabel, compactEuro, confidenceWords, cx, euro, number, pct, reviewLabel, severityLabel, timeLabel } from '../lib/format'
import { ConfidenceBar, Icon, SeverityChip } from './ui'
import type { Site } from '../types'

export default function SiteDetail({ site, rank, mode }: { site: Site; rank: number; mode: 'stage' | 'analyst' }) {
  const app = useApp()
  const scenario = app.scenario!
  const [split, setSplit] = useState(56)
  const review = app.reviews[site.id] ?? 'pending'
  const team = app.assignments[site.id]
  const note = app.notes[site.id] ?? ''
  const rejected = review === 'rejected'
  const inRisk = mode === 'analyst' || app.time + 0.001 >= site.riskAt
  const shownSeverity = inRisk ? site.severity : site.severity === 'red' ? 'orange' : site.severity

  const factors = useMemo(
    () =>
      Object.entries(app.ranked.find((r) => r.site.id === site.id)?.contributions ?? {})
        .sort((a, b) => b[1] - a[1])
        .map(([key, value]) => ({ key, value })),
    [app.ranked, site.id],
  )

  const maxFactor = Math.max(0.001, ...factors.map((f) => f.value))
  const url = (path: string) => asset(path)
  const showTrust = scenario.falsePositive?.siteId === site.id && !rejected

  return (
    <section className={cx('site-detail', mode === 'analyst' && 'site-detail-analyst')} aria-label={`Site ${site.name}`}>
      <header className="detail-head">
        <div className="detail-rank">
          <span>#{rank || '–'}</span>
          <small>rank</small>
        </div>
        <div className="detail-title">
          <div className="detail-eyebrow">
            <SeverityChip severity={shownSeverity} small />
            <span>{inRisk ? severityLabel(site.severity) : 'Watch'}</span>
            <span className="dot-sep" />
            <span>{site.kindLabel}</span>
            <span className="dot-sep" />
            <span>{site.id}</span>
          </div>
          <h2>{site.name}</h2>
          <div className="detail-loc">
            {site.lon.toFixed(4)}, {site.lat.toFixed(4)} · {site.detectedAt}
            {mode === 'stage' && site.flooded && (
              <span className="risk-arrival">{inRisk ? `Flood edge reached this site at ${timeLabel(site.riskAt)}` : `Flood edge arrives ${timeLabel(site.riskAt)}`}</span>
            )}
          </div>
        </div>
        <button className="icon-btn" onClick={() => app.selectSite(null)} aria-label="Close site panel">
          <Icon name="close" size={16} />
        </button>
      </header>

      {showTrust && (
        <div className="trust-block">
          <div className="trust-label">
            <span className="pulse-dot" /> Agent’s top finding — check before dispatch
          </div>
          <p>
            {scenario.falsePositive?.title}. The model reads this as {confidenceWords(site.confidence).word} ({confidenceWords(site.confidence).interval}). Zoom the evidence: the roof edge is
            intact; the dark shape is water reflection.
          </p>
          <button className="btn btn-danger btn-block" onClick={() => app.review(site.id, 'rejected')}>
            <Icon name="x" size={14} /> Reject this finding
          </button>
        </div>
      )}

      <div className="evidence">
        <div className="evidence-frame">
          <img src={url(site.evidence.before)} alt={`${site.name} before`} loading="lazy" />
          <img
            src={url(site.evidence.after)}
            alt={`${site.name} after with change outline`}
            loading="lazy"
            style={{ clipPath: `inset(0 ${100 - split}% 0 0)` }}
          />
          <div className="evidence-line" style={{ left: `${split}%` }} />
          <span className="evidence-tag tag-before">before</span>
          <span className="evidence-tag tag-after">after</span>
          {site.falsePositive && <span className="evidence-tag tag-fp">false positive</span>}
        </div>
        <div className="evidence-controls">
          <span>Before</span>
          <input
            type="range"
            min={0}
            max={100}
            value={split}
            onChange={(event) => setSplit(Number(event.target.value))}
            aria-label="Evidence comparison"
          />
          <span>After</span>
        </div>
        <div className="evidence-caption">{site.evidence.caption}</div>
      </div>

      <div className="detail-stats">
        <div>
          <b>{number(site.changeExtentM2)}</b>
          <span>m² change</span>
        </div>
        <div>
          <b>{compactEuro(site.valueEur)}</b>
          <span>value at risk</span>
        </div>
        <div>
          <b>{number(site.population)}</b>
          <span>people 700 m</span>
        </div>
        <div>
          <b>{site.responseMinutes}′</b>
          <span>response</span>
        </div>
      </div>

      <div className="confidence-row">
        <span>Model confidence</span>
        <b>{pct(site.confidence)}</b>
      </div>
      <ConfidenceBar value={site.confidence} />

      <div className="why-chain">
        <h3>The “why” chain</h3>
        {site.why.map((item) => (
          <div className="why-item" key={item.label}>
            <span className={cx('why-icon', `why-${item.icon}`)}>
              <Icon name={item.icon === 'access' ? 'road' : item.icon === 'power' ? 'bolt' : 'people'} size={15} />
            </span>
            <div>
              <b>{item.label}</b>
              <strong>{item.value}</strong>
              <small>{item.detail}</small>
            </div>
          </div>
        ))}
      </div>

      <div className="factors">
        <h3>Rank contribution</h3>
        {factors.map((factor) => (
          <div className="factor-row" key={factor.key}>
            <span>{factor.key}</span>
            <div className="factor-track">
              <span style={{ width: `${(factor.value / maxFactor) * 100}%` }} />
            </div>
            <b>{factor.value.toFixed(3)}</b>
          </div>
        ))}
      </div>

      <div className="policy-row">
        <div>
          <span>Policy</span>
          <b>{site.policy.id}</b>
        </div>
        <div>
          <span>Access</span>
          <b>{accessLabel(site.accessStatus)}</b>
        </div>
        <div>
          <span>Review</span>
          <b className={cx('review-text', `review-${review}`)}>{reviewLabel(review)}</b>
        </div>
      </div>

      {site.assets && site.assets.length > 0 && (
        <div className="asset-row">
          {site.assets.slice(0, 3).map((assetItem) => (
            <span key={assetItem.id}>
              <Icon name="bolt" size={12} /> {assetItem.name} · {euro(assetItem.valueEur)}
            </span>
          ))}
        </div>
      )}

      {mode === 'analyst' && (
        <div className="notes-block">
          <label htmlFor={`note-${site.id}`}>Analyst note</label>
          <textarea
            id={`note-${site.id}`}
            value={note}
            placeholder="Visible reason, correction, adjuster instruction…"
            onChange={(event) => app.setNote(site.id, event.target.value)}
            rows={2}
          />
        </div>
      )}

      <div className="detail-actions">
        <div className="review-actions">
          <button
            className={cx('btn btn-approve', review === 'approved' && 'is-active')}
            onClick={() => app.review(site.id, 'approved')}
            disabled={rejected}
          >
            <Icon name="check" size={14} /> Approve
          </button>
          <button
            className={cx('btn btn-flag', review === 'flagged' && 'is-active')}
            onClick={() => app.review(site.id, 'flagged')}
            disabled={rejected}
          >
            <Icon name="flag" size={14} /> Flag
          </button>
          <button
            className={cx('btn btn-reject', rejected && 'is-active')}
            onClick={() => app.review(site.id, 'rejected')}
          >
            <Icon name="x" size={14} /> Reject
          </button>
        </div>

        <div className="team-actions">
          <label>
            <span>{team ? `${team} assigned` : 'Assign team'}</span>
            <select
              value={team ?? ''}
              onChange={(event) => {
                if (event.target.value) app.assign(site.id, event.target.value)
                else app.unassign(site.id)
              }}
              disabled={rejected}
            >
              <option value="">—</option>
              {Array.from({ length: scenario.meta.teams }, (_, i) => `Team ${i + 1}`).map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
          </label>
          {team && (
            <button className="btn btn-ghost" onClick={() => app.unassign(site.id)}>
              Free
            </button>
          )}
        </div>
      </div>

      {rejected && (
        <div className="rejected-note">
          <Icon name="x" size={13} /> Rejected and removed from the ranking. The original finding and reason stay in the audit
          trail.
        </div>
      )}
    </section>
  )
}
