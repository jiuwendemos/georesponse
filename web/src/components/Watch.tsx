import { useEffect, useMemo, useState } from 'react'
import { asset, dataPath, loadJson } from '../lib/data'
import { compactEuro, cx, number, pct } from '../lib/format'
import { ConfidenceBar, Icon, Modal, SeverityChip } from './ui'
import WatchMap from './WatchMap'
import type {
  ProactiveAlert,
  ProactiveData,
  ProactivePreferences,
  ProactiveScope,
  Severity,
} from '../types'

type Tab = 'inbox' | 'scopes' | 'coverage' | 'digest' | 'settings'
type StatusFilter = 'open' | 'all' | 'new' | 'assigned' | 'investigating' | 'resolved' | 'dismissed'

const DISMISS_REASONS = [
  ['false_positive', 'False positive'],
  ['known_event', 'Known event'],
  ['cloud_shadow', 'Cloud / shadow'],
  ['no_action', 'No action warranted'],
  ['duplicate', 'Duplicate'],
  ['access', 'Access / out of scope'],
  ['other', 'Other'],
] as const

const CHANNELS = ['email', 'slack', 'teams', 'sms', 'pager', 'webhook']
const OPEN_STATES = new Set(['new', 'acknowledged', 'assigned', 'investigating'])

function ago(value: string | null | undefined): string {
  if (!value) return 'never'
  const then = new Date(value).getTime()
  const diff = Date.now() - then
  const minutesAgo = Math.round(diff / 60000)
  if (minutesAgo < 1) return 'just now'
  if (minutesAgo < 60) return `${minutesAgo}m ago`
  const hours = Math.round(minutesAgo / 60)
  if (hours < 48) return `${hours}h ago`
  return `${Math.round(hours / 24)}d ago`
}

function remaining(value: string | null): string {
  if (!value) return '—'
  const mins = Math.round((new Date(value).getTime() - Date.now()) / 60000)
  if (mins < 0) return `${Math.abs(mins)}m overdue`
  if (mins < 60) return `${mins}m left`
  return `${Math.round(mins / 60)}h left`
}

function statusLabel(value: string): string {
  return value === 'new' ? 'New' : value === 'acknowledged' ? 'Acknowledged' : value === 'assigned' ? 'Assigned' : value === 'investigating' ? 'Investigating' : value === 'resolved' ? 'Resolved' : value === 'dismissed' ? 'Dismissed' : value
}

const severityOrder: Record<string, number> = { red: 3, orange: 2, yellow: 1 }

function Sparkline({ values, color = '#22d3ee' }: { values: number[]; color?: string }) {
  if (!values.length) return <span className="spark-empty">no baseline</span>
  const low = Math.min(...values)
  const high = Math.max(...values)
  const span = high - low || 1
  const points = values.map((value, index) => `${(index / Math.max(1, values.length - 1)) * 70},${28 - ((value - low) / span) * 24}`).join(' ')
  return (
    <svg className="sparkline" viewBox="0 0 70 30" aria-hidden>
      <polyline points={points} fill="none" stroke={color} strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

export default function Watch() {
  const [data, setData] = useState<ProactiveData | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [tab, setTab] = useState<Tab>('inbox')
  const [filter, setFilter] = useState<StatusFilter>('open')
  const [severity, setSeverity] = useState<'all' | Severity>('all')
  const [query, setQuery] = useState('')
  const [selectedAlert, setSelectedAlert] = useState<string | null>(null)
  const [selectedScope, setSelectedScope] = useState<string | null>(null)
  const [dismissReason, setDismissReason] = useState('false_positive')
  const [toast, setToast] = useState<string | null>(null)
  const [drawing, setDrawing] = useState(false)
  const [draftBbox, setDraftBbox] = useState<[number, number, number, number] | null>(null)
  const [createOpen, setCreateOpen] = useState(false)
  const [scopeName, setScopeName] = useState('')
  const [scopeRegion, setScopeRegion] = useState('Ahrweiler, Germany')
  const [scopeClass, setScopeClass] = useState('utility')
  const [scopeCadence, setScopeCadence] = useState('daily')
  const [scopeChange, setScopeChange] = useState('flood')
  const [prefs, setPrefs] = useState<ProactivePreferences | null>(null)

  useEffect(() => {
    let alive = true
    loadJson<ProactiveData>(dataPath('proactive.json'))
      .then((payload) => {
        if (!alive) return
        setData(payload)
        setPrefs(payload.preferences)
        setSelectedAlert(payload.alerts.find((a) => OPEN_STATES.has(a.status))?.id ?? payload.alerts[0]?.id ?? null)
        setSelectedScope(payload.scopes[0]?.id ?? null)
      })
      .catch((err) => alive && setError(err instanceof Error ? err.message : 'Could not load proactive data'))
    return () => {
      alive = false
    }
  }, [])

  useEffect(() => {
    if (!toast) return
    const timer = window.setTimeout(() => setToast(null), 3200)
    return () => window.clearTimeout(timer)
  }, [toast])

  const alerts = data?.alerts ?? []
  const scopes = data?.scopes ?? []
  const current = alerts.find((a) => a.id === selectedAlert) ?? null

  const filtered = useMemo(
    () =>
      alerts
        .filter((alert) => {
          if (filter === 'all') return true
          if (filter === 'open') return OPEN_STATES.has(alert.status)
          return alert.status === filter
        })
        .filter((alert) => severity === 'all' || alert.severity === severity)
        .filter((alert) => !query || `${alert.title} ${alert.scope_id} ${alert.asset ?? ''} ${alert.change_type}`.toLowerCase().includes(query.toLowerCase()))
        .sort((a, b) => severityOrder[b.severity] - severityOrder[a.severity] || b.created_at.localeCompare(a.created_at)),
    [alerts, filter, severity, query],
  )

  const openCount = alerts.filter((a) => OPEN_STATES.has(a.status)).length
  const highRisk = alerts.filter((a) => a.severity === 'red' && OPEN_STATES.has(a.status)).length

  const updateAlert = (id: string, patch: Partial<ProactiveAlert>) => {
    setData((currentData) =>
      currentData ? { ...currentData, alerts: currentData.alerts.map((a) => (a.id === id ? { ...a, ...patch } : a)) } : currentData,
    )
  }

  const act = (alert: ProactiveAlert, action: string) => {
    if (action === 'acknowledge') {
      updateAlert(alert.id, { status: 'acknowledged', acknowledged_at: new Date().toISOString() })
      setToast(`${alert.id} acknowledged. The SLA clock keeps running until resolution.`)
    } else if (action === 'assign') {
      updateAlert(alert.id, { status: 'assigned', assignee: alert.assignee ?? 'A. Weber' })
      setToast(`${alert.id} assigned to ${alert.assignee ?? 'A. Weber'}.`)
    } else if (action === 'investigate') {
      updateAlert(alert.id, { status: 'investigating' })
      setToast(`${alert.id} moved to investigating. Add the field note when known.`)
    } else if (action === 'resolve') {
      updateAlert(alert.id, { status: 'resolved', resolved_at: new Date().toISOString() })
      setToast(`${alert.id} resolved. The decision is in the audit trail.`)
    } else if (action === 'dismiss') {
      updateAlert(alert.id, { status: 'dismissed', dismissed_reason: dismissReason, dismissal_note: 'Dismissed from the Watch inbox.' })
      setToast(`${alert.id} dismissed as ${DISMISS_REASONS.find((r) => r[0] === dismissReason)?.[1]}.`)
    }
  }

  const handoff = (target: string) => {
    setToast(`${target === 'claim' ? 'Claim draft' : target === 'inspection' ? 'Inspection request' : target === 'dispatch' ? 'Dispatch draft' : 'Assessment'} queued — human approval required.`)
  }

  const toggleScope = (scope: ProactiveScope) => {
    if (!data) return
    const next = scope.status === 'active' ? 'paused' : 'active'
    setData({
      ...data,
      scopes: data.scopes.map((s) => (s.id === scope.id ? { ...s, status: next } : s)),
      plans: data.plans.map((p) => (p.scope_id === scope.id ? { ...p, paused: next === 'paused' } : p)),
    })
    setToast(`${scope.name} ${next === 'paused' ? 'paused' : 'resumed'}.`)
  }

  const watchNow = (scope: ProactiveScope) => {
    setToast(`Acquisition queued for ${scope.name}. Priority ${scope.priority}; human-approved tasking.`)
  }

  const createScope = () => {
    if (!data || !scopeName.trim()) return
    const bbox = draftBbox ?? [7.02, 50.52, 7.18, 50.57]
    const center: [number, number] = [(bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2]
    const next: ProactiveScope = {
      id: `scope-${Date.now()}`,
      tenant: data.tenant,
      name: scopeName,
      kind: 'aoi',
      region: scopeRegion,
      center,
      bbox,
      asset_class: scopeClass,
      change_types: [scopeChange],
      cadence: scopeCadence,
      priority: 3,
      subscription_tier: scopeCadence === 'daily' ? 'daily' : 'weekly',
      status: 'active',
      freshness_slo_hours: scopeCadence === 'daily' ? 48 : 168,
      recipients: ['ops@example.com'],
      tags: ['new-scope'],
      created_at: new Date().toISOString(),
      metadata: { valueEur: 0, population: 0, assets: [] },
    }
    setData({
      ...data,
      scopes: [...data.scopes, next],
      plans: [
        ...data.plans,
        {
          ...data.plans[0],
          scope_id: next.id,
          cadence: scopeCadence,
          paused: false,
          digest: 'daily',
        },
      ],
      coverage: [
        ...data.coverage,
        {
          scopeId: next.id,
          name: next.name,
          kind: next.kind,
          region: next.region,
          bbox: next.bbox,
          center: next.center,
          areaKm2: 24,
          cadence: next.cadence,
          status: 'active',
          lastAcquisition: null,
          nextExpected: new Date(Date.now() + 86400000).toISOString(),
          freshnessHours: null,
          readiness: 0,
          coverageStatus: 'blind',
          blindSpot: true,
          mode: 'best-effort',
          source: null,
        },
      ],
    })
    setSelectedScope(next.id)
    setCreateOpen(false)
    setDrawing(false)
    setDraftBbox(null)
    setScopeName('')
    setToast(`Scope ${next.name} created. First acquisition is queued for approval.`)
  }

  const savePrefs = () => {
    setToast('Notification preferences saved. Quiet hours are enforced server-side.')
  }

  const retryNotification = (id: string) => {
    if (!data) return
    setData({ ...data, notifications: data.notifications.map((n) => (n.id === id ? { ...n, status: 'queued', nextAttemptAt: new Date().toISOString() } : n)) })
    setToast(`Notification ${id} requeued with backoff.`)
  }

  const deployModel = (name: string) => {
    if (!data) return
    setData({
      ...data,
      models: data.models.map((m) =>
        m.name === name
          ? { ...m, status: 'deployed', rollback_to: m.version, notes: 'Promoted from the Watch console.' }
          : { ...m, status: m.status === 'deployed' ? 'retired' : m.status },
      ),
    })
    setToast(`${name} marked deployed. The pinned version is recorded on every new alert.`)
  }

  if (error) return <div className="page-state">{error}</div>
  if (!data || !prefs) return <div className="page-state">Loading the watch portfolio…</div>

  const selectedScopeRow = data.coverage.find((row) => row.scopeId === selectedScope)
  const calendarRows = selectedScope ? data.calendar[selectedScope] ?? [] : []

  return (
    <div className="watch-page">
      <header className="watch-head">
        <div>
          <div className="eyebrow">
            <span className="dot" /> Proactive watch · {data.tenant}
          </div>
          <h1>The portfolio is already moving.<br />Here is what changed.</h1>
          <p>{data.disclaimer} Human review is mandatory. No automatic dispatch.</p>
        </div>
        <div className="watch-head-right">
          <div className="watch-oncall">
            <span>on call · {data.dashboard.onCall.window}</span>
            <b>{data.dashboard.onCall.primary}</b>
            <small>backup {data.dashboard.onCall.secondary}</small>
          </div>
          <button className="btn" onClick={() => setTab('settings')}>
            <Icon name="shield" size={14} /> Governance
          </button>
          <button className="btn btn-primary" onClick={() => { setTab('scopes'); setDrawing(true) }}>
            <Icon name="pin" size={14} /> Draw a scope
          </button>
        </div>
      </header>

      <div className="watch-kpis">
        <div className="watch-kpi"><span>Open alerts</span><b>{openCount}</b><em>{highRisk} high risk</em></div>
        <div className="watch-kpi"><span>Monitored</span><b>{data.dashboard.monitoredKm2} km²</b><em>{data.dashboard.activeScopes} active scopes</em></div>
        <div className="watch-kpi"><span>Precision</span><b>{pct(data.dashboard.precision)}</b><em>confirmed / closed</em></div>
        <div className="watch-kpi"><span>SLA breaches</span><b className={data.dashboard.slaBreaches ? 'warn' : ''}>{data.dashboard.slaBreaches}</b><em>review clock</em></div>
        <div className="watch-kpi"><span>Alert load</span><b>{data.dashboard.fatigue.perAnalyst}</b><em>per analyst / {data.dashboard.fatigue.periodHours}h</em></div>
        <div className="watch-kpi"><span>Freshness</span><b className={data.dashboard.freshness.breached ? 'warn' : ''}>{data.dashboard.freshness.breached}</b><em>scope breach(es)</em></div>
      </div>

      <nav className="watch-tabs" aria-label="Watch sections">
        {(['inbox', 'scopes', 'coverage', 'digest', 'settings'] as Tab[]).map((item) => (
          <button key={item} className={cx('watch-tab', tab === item && 'active')} onClick={() => setTab(item)}>
            {item}
            {item === 'inbox' && <span className="watch-tab-badge">{openCount}</span>}
          </button>
        ))}
      </nav>

      {tab === 'inbox' && (
        <section className="watch-inbox">
          <aside className="watch-list">
            <div className="watch-list-head">
              <div>
                <span className="eyebrow">Alert inbox</span>
                <h2>{filtered.length} alerts</h2>
              </div>
              <button className="btn btn-sm" onClick={() => setToast('Bulk acknowledge is limited to 50 alerts and audited.')}>
                <Icon name="check" size={12} /> Bulk
              </button>
            </div>
            <input className="search" placeholder="Search alert, asset or scope…" value={query} onChange={(e) => setQuery(e.target.value)} />
            <div className="filter-row">
              {(['open', 'all', 'new', 'assigned', 'investigating', 'resolved', 'dismissed'] as StatusFilter[]).map((item) => (
                <button key={item} className={cx('filter-chip', filter === item && 'active')} onClick={() => setFilter(item)}>
                  {statusLabel(item)}
                </button>
              ))}
            </div>
            <div className="filter-row">
              {(['all', 'red', 'orange', 'yellow'] as const).map((item) => (
                <button key={item} className={cx('filter-chip', severity === item && 'active')} onClick={() => setSeverity(item)}>
                  {item === 'all' ? 'All severity' : item === 'red' ? 'High' : item === 'orange' ? 'Watch' : 'Monitor'}
                </button>
              ))}
            </div>
            <div className="watch-alert-list">
              {filtered.map((alert) => (
                <button key={alert.id} className={cx('watch-alert-row', selectedAlert === alert.id && 'active', `sev-${alert.severity}`)} onClick={() => { setSelectedAlert(alert.id); setSelectedScope(alert.scope_id) }}>
                  <span className="watch-sev-bar" />
                  <span className="watch-alert-main">
                    <span className="watch-alert-top"><SeverityChip severity={alert.severity} small /><span>{ago(alert.created_at)}</span></span>
                    <b>{alert.title}</b>
                    <small>{alert.scope_id.replace('scope-', '')} · {alert.assignee ?? 'unassigned'} · {pct(alert.confidence)}</small>
                    <span className={cx('watch-status', `status-${alert.status}`)}>{statusLabel(alert.status)} · {remaining(alert.sla_due)}</span>
                  </span>
                </button>
              ))}
              {!filtered.length && <div className="empty-list">No alerts in this filter.</div>}
            </div>
            <div className="list-foot"><span>{data.dashboard.notifications.filter((n) => n.status === 'failed').length} delivery failures</span><span>2.5σ + 6%</span></div>
          </aside>

          <div className="watch-map-wrap">
            <WatchMap
              scopes={scopes}
              alerts={alerts}
              coverage={data.coverage}
              selectedScopeId={selectedScope}
              onSelectScope={(id) => setSelectedScope(id)}
              onSelectAlert={(id) => {
                const alert = alerts.find((a) => a.id === id)
                if (alert) {
                  setSelectedAlert(id)
                  setSelectedScope(alert.scope_id)
                }
              }}
            />
            <div className="watch-map-strip">
              <span><b>{data.watch.watchlist.length}</b> scopes in pre-event watch</span>
              <span><b>{data.watch.watchlist.filter((row) => row.taskingTrigger).length}</b> tasking triggers</span>
              <span><b>{data.blindSpots.length}</b> blind spots</span>
              <button className="btn btn-sm" onClick={() => setTab('coverage')}>Coverage <Icon name="arrow" size={12} /></button>
            </div>
          </div>

          <aside className="watch-detail">
            {current ? (
              <>
                <div className="watch-detail-head">
                  <div className="detail-eyebrow"><SeverityChip severity={current.severity} small /><span>{current.change_type}</span><span className="dot-sep" /><span>{current.id}</span></div>
                  <h2>{current.title}</h2>
                  <p>{current.summary}</p>
                  <div className="watch-detail-meta">
                    <span><b>{pct(current.confidence)}</b> confidence</span>
                    <span><b>{remaining(current.sla_due)}</b> SLA</span>
                    <span><b>{current.assignee ?? 'unassigned'}</b> owner</span>
                  </div>
                </div>
                <div className="watch-evidence">
                  <img src={asset(current.evidence.before ?? 'data/scenes/ahr-2021-flood-before.png')} alt="Before observation" />
                  <img src={asset(current.evidence.after ?? 'data/scenes/ahr-2021-flood-after.png')} alt="After observation with change overlay" />
                  <span className="evidence-tag tag-before">before</span>
                  <span className="evidence-tag tag-after">after</span>
                </div>
                <div className="watch-facts">
                  <div><span>Asset</span><b>{current.asset ?? '—'}</b></div>
                  <div><span>Value</span><b>{compactEuro(current.value_eur)}</b></div>
                  <div><span>People</span><b>{number(current.population)}</b></div>
                  <div><span>Access</span><b>{current.access}</b></div>
                </div>
                <div className="watch-why">
                  <h3>Why this alert</h3>
                  <div className="why-factor"><span>change vs baseline</span><b>{pct(current.observed)} vs {pct(current.baseline)}</b></div>
                  <div className="why-track"><span style={{ width: `${Math.min(100, current.observed * 500)}%` }} /></div>
                  <div className="why-factor"><span>model confidence</span><b>{pct(current.confidence)}</b></div>
                  <ConfidenceBar value={current.confidence} />
                  <small>{String((current.why as Record<string, unknown>).summary ?? '')}</small>
                </div>
                <div className="watch-incident">
                  <span>Incident</span>
                  <b>{current.incident_id ?? 'single alert'}</b>
                  {current.incident_id && <small>{data.incidents.find((i) => i.id === current.incident_id)?.title}</small>}
                </div>
                {current.incident_id && (
                  <div className="incident-group">
                    <div className="incident-group-head"><span>Related alerts</span><b>{alerts.filter((a) => a.incident_id === current.incident_id).length}</b></div>
                    {alerts.filter((a) => a.incident_id === current.incident_id).map((related) => (
                      <button key={related.id} className="incident-link" onClick={() => setSelectedAlert(related.id)}>
                        <SeverityChip severity={related.severity} small />
                        <span>{related.title}</span>
                        <small>{statusLabel(related.status)}</small>
                      </button>
                    ))}
                  </div>
                )}
                <div className="watch-detail-actions">
                  {current.status === 'new' && <button className="btn btn-approve" onClick={() => act(current, 'acknowledge')}>Acknowledge</button>}
                  {(current.status === 'new' || current.status === 'acknowledged') && <button className="btn" onClick={() => act(current, 'assign')}>Assign to me</button>}
                  {['acknowledged', 'assigned'].includes(current.status) && <button className="btn" onClick={() => act(current, 'investigate')}>Investigate</button>}
                  {['acknowledged', 'assigned', 'investigating'].includes(current.status) && <button className="btn btn-approve" onClick={() => act(current, 'resolve')}>Resolve</button>}
                  {OPEN_STATES.has(current.status) && (
                    <div className="dismiss-row">
                      <select value={dismissReason} onChange={(e) => setDismissReason(e.target.value)} aria-label="Dismiss reason">
                        {DISMISS_REASONS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
                      </select>
                      <button className="btn btn-reject" onClick={() => act(current, 'dismiss')}>Dismiss</button>
                    </div>
                  )}
                </div>
                <div className="watch-handoff">
                  <span>Handoff — draft only</span>
                  <div>
                    <button className="btn btn-sm" onClick={() => handoff('assessment')}>Assessment</button>
                    <button className="btn btn-sm" onClick={() => handoff('claim')}>Claim draft</button>
                    <button className="btn btn-sm" onClick={() => handoff('inspection')}>Inspection</button>
                    <button className="btn btn-sm" onClick={() => handoff('dispatch')}>Dispatch draft</button>
                  </div>
                </div>
                <div className="watch-detail-foot">Model {current.model_version} · {current.source} · human review required</div>
              </>
            ) : (
              <div className="watch-empty-detail"><Icon name="radar" size={26} /><b>No alert selected</b><span>The inbox and coverage map stay in sync.</span></div>
            )}
          </aside>
        </section>
      )}

      {tab === 'scopes' && (
        <section className="watch-scopes">
          <div className="watch-section-head">
            <div>
              <span className="eyebrow">Monitored scopes</span>
              <h2>{scopes.length} scopes · {data.dashboard.monitoredKm2} km²</h2>
            </div>
            <div className="watch-section-actions">
              <button className={cx('btn', drawing && 'is-active')} onClick={() => { setDrawing((v) => !v); setTab('coverage') }}>
                <Icon name="pin" size={14} /> {drawing ? 'Drawing…' : 'Draw scope'}
              </button>
              <button className="btn btn-primary" onClick={() => setCreateOpen(true)}><Icon name="check" size={14} /> New scope</button>
            </div>
          </div>
          <div className="scope-grid">
            {scopes.map((scope) => {
              const plan = data.plans.find((p) => p.scope_id === scope.id)
              const coverageRow = data.coverage.find((c) => c.scopeId === scope.id)
              const alertCount = alerts.filter((a) => a.scope_id === scope.id && OPEN_STATES.has(a.status)).length
              return (
                <article key={scope.id} className={cx('scope-card', scope.status === 'paused' && 'paused', coverageRow?.blindSpot && 'blind')}>
                  <div className="scope-card-head">
                    <div>
                      <span className="eyebrow">{scope.kind} · {scope.cadence}</span>
                      <h3>{scope.name}</h3>
                      <p>{scope.region} · {scope.asset_class}</p>
                    </div>
                    <span className={cx('scope-state', scope.status)}>{scope.status}</span>
                  </div>
                  <div className="scope-card-stats">
                    <span><b>{alertCount}</b> open alerts</span>
                    <span><b>{coverageRow?.readiness !== undefined ? pct(coverageRow.readiness) : '—'}</b> readiness</span>
                    <span><b>{coverageRow?.freshnessHours !== undefined && coverageRow.freshnessHours !== null ? `${Math.round(coverageRow.freshnessHours)}h` : 'never'}</b> freshness</span>
                  </div>
                  <div className="scope-plan">
                    <span>{plan?.sources.join(' + ') ?? 'sentinel-2'}</span>
                    <span>SLA {plan?.sla_hours ?? 4}h</span>
                    <span>budget €{plan?.budget_eur_per_month ?? 0}/mo</span>
                  </div>
                  <div className="scope-trend">
                    <span>baseline</span>
                    <Sparkline values={data.baselines.find((b) => b.scope_id === scope.id)?.values ?? []} color={coverageRow?.blindSpot ? '#fb7185' : '#22d3ee'} />
                    <small>{data.baselines.find((b) => b.scope_id === scope.id)?.trend ?? '—'}</small>
                  </div>
                  <div className="scope-card-actions">
                    <button className="btn btn-sm" onClick={() => watchNow(scope)}><Icon name="radar" size={12} /> Watch now</button>
                    <button className="btn btn-sm btn-ghost" onClick={() => toggleScope(scope)}>{scope.status === 'active' ? 'Pause' : 'Resume'}</button>
                    <button className="btn btn-sm btn-ghost" onClick={() => { setSelectedScope(scope.id); setTab('coverage') }}>Coverage</button>
                  </div>
                </article>
              )
            })}
          </div>
        </section>
      )}

      {tab === 'coverage' && (
        <section className="watch-coverage">
          <div className="watch-section-head">
            <div>
              <span className="eyebrow">Acquisition coverage</span>
              <h2>What we can see, and what we cannot</h2>
            </div>
            <div className="watch-section-actions">
              <button className={cx('btn', drawing && 'is-active')} onClick={() => setDrawing((v) => !v)}><Icon name="pin" size={14} /> {drawing ? 'Drawing…' : 'Draw scope'}</button>
            </div>
          </div>
          <div className="coverage-layout">
            <div className="coverage-map-wrap">
              <WatchMap
                scopes={scopes}
                alerts={alerts}
                coverage={data.coverage}
                selectedScopeId={selectedScope}
                onSelectScope={(id) => setSelectedScope(id)}
                drawing={drawing}
                onDraw={(bbox) => { setDraftBbox(bbox); setDrawing(false); setCreateOpen(true); setToast('Scope drawn. Name it and confirm the cadence.') }}
              />
              <div className="coverage-legend">
                <span><i className="dot-red" /> alert</span><span><i className="dot-cyan" /> scope</span><span><i className="dash" /> blind spot</span><span><i className="dash green" /> healthy</span>
              </div>
            </div>
            <aside className="coverage-side">
              <div className="coverage-summary">
                <div><span>Scopes</span><b>{data.coverage.length}</b></div>
                <div><span>Blind spots</span><b className={data.blindSpots.length ? 'warn' : ''}>{data.blindSpots.length}</b></div>
                <div><span>SLO breaches</span><b className={data.freshness.breached ? 'warn' : ''}>{data.freshness.breached}</b></div>
              </div>
              <div className="coverage-list">
                {data.coverage.map((row) => (
                  <button key={row.scopeId} className={cx('coverage-row', selectedScope === row.scopeId && 'active', row.blindSpot && 'blind')} onClick={() => setSelectedScope(row.scopeId)}>
                    <span className={cx('coverage-status-dot', row.coverageStatus)} />
                    <div><b>{row.name}</b><small>{row.cadence} · {row.areaKm2} km² · {row.source ?? 'no source'}</small></div>
                    <span className="coverage-fresh">{row.freshnessHours === null ? 'never' : `${Math.round(row.freshnessHours)}h`}</span>
                  </button>
                ))}
              </div>
              {selectedScope && selectedScopeRow && (
                <div className="coverage-detail">
                  <div className="eyebrow">Acquisition calendar</div>
                  <h3>{selectedScopeRow.name}</h3>
                  <div className="calendar-list">
                    {calendarRows.slice(0, 6).map((row) => (
                      <div className="calendar-row" key={row.id}>
                        <span className={cx('calendar-status', row.status)} />
                        <span>{new Date(row.scheduledFor).toLocaleDateString()} {new Date(row.scheduledFor).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
                        <b>{row.source}</b>
                        <small>{row.status}{row.blindSpotReason ? ` · ${row.blindSpotReason}` : ''}</small>
                      </div>
                    ))}
                  </div>
                  <div className="coverage-detail-stats">
                    <span><b>{pct(selectedScopeRow.readiness)}</b> readiness</span>
                    <span><b>{selectedScopeRow.nextExpected ? new Date(selectedScopeRow.nextExpected).toLocaleDateString() : '—'}</b> next expected</span>
                  </div>
                </div>
              )}
            </aside>
          </div>
          {data.blindSpots.length > 0 && (
            <div className="blindspot-banner">
              <Icon name="shield" size={16} />
              <div><b>{data.blindSpots.length} blind spot(s)</b><span>{data.blindSpots.map((b) => `${b.name}: ${b.reason}`).join(' · ')}</span></div>
              <button className="btn btn-sm" onClick={() => setToast('Tasking re-planned for the blind spots. Priority raised; human approval required.')}>Re-plan tasking</button>
            </div>
          )}
          <div className="forecast-strip">
            <div className="eyebrow">Pre-event watchlist</div>
            {data.watch.watchlist.slice(0, 4).map((row) => (
              <div className="forecast-card" key={row.scopeId}>
                <span className="forecast-prob">{pct(row.probability)}</span>
                <div><b>{row.name}</b><small>{row.hazard} · lead {row.leadTimeHours}h · {row.interval[0]}–{row.interval[1]} interval</small></div>
                <span className={cx('forecast-task', row.taskingTrigger && 'on')}>{row.taskingTrigger ? 'tasking' : 'watch'}</span>
              </div>
            ))}
          </div>
        </section>
      )}

      {tab === 'digest' && (
        <section className="watch-digest">
          <div className="watch-section-head">
            <div>
              <span className="eyebrow">Digest · {data.digest.periodHours}h</span>
              <h2>{data.digest.headline}</h2>
              <p>Instant alerts for high risk; digests for everything else. “No action” is a recorded outcome, not a failure.</p>
            </div>
            <span className="digest-date">{new Date(data.digest.generatedAt).toLocaleString()}</span>
          </div>
          <div className="digest-grid">
            {(['new', 'inProgress', 'resolved', 'noAction'] as const).map((section) => (
              <div className="digest-column" key={section}>
                <div className="digest-column-head"><span>{section === 'noAction' ? 'No action' : section === 'inProgress' ? 'In progress' : section === 'new' ? 'New' : 'Resolved'}</span><b>{data.digest.sections[section].length}</b></div>
                {data.digest.sections[section].slice(0, 6).map((alert) => (
                  <button key={alert.id} className="digest-item" onClick={() => { setTab('inbox'); setSelectedAlert(alert.id); setSelectedScope(alert.scope_id) }}>
                    <SeverityChip severity={alert.severity} small />
                    <span>{alert.title}</span>
                    <small>{ago(alert.created_at)}</small>
                  </button>
                ))}
                {!data.digest.sections[section].length && <div className="empty-list">Nothing here.</div>}
              </div>
            ))}
          </div>
          <div className="digest-footer">
            <div className="card"><span className="eyebrow">Alert load</span><b>{data.dashboard.fatigue.perAnalyst} / analyst</b><p>{data.dashboard.fatigue.advice} · budget {data.dashboard.fatigue.budgetPerAnalyst}</p></div>
            <div className="card"><span className="eyebrow">Action conversion</span><b>{pct(data.dashboard.actionConversion)}</b><p>Resolved alerts / closed alerts in this seeded portfolio.</p></div>
            <div className="card"><span className="eyebrow">Cost</span><b>€{data.costs.summary.totalEur}</b><p>€{data.dashboard.costPerKm2}/km² · {data.costs.summary.entries} entries</p></div>
          </div>
        </section>
      )}

      {tab === 'settings' && (
        <section className="watch-settings">
          <div className="watch-section-head">
            <div><span className="eyebrow">Configuration & governance</span><h2>Make the watch explicit</h2></div>
            <button className="btn btn-primary" onClick={savePrefs}><Icon name="check" size={14} /> Save preferences</button>
          </div>
          <div className="settings-grid">
            <div className="card">
              <span className="eyebrow">Notifications</span>
              <h3>Channels & quiet hours</h3>
              <div className="channel-row">
                {CHANNELS.map((channel) => (
                  <label key={channel} className={cx('channel-chip', prefs.channels.includes(channel) && 'active')}>
                    <input type="checkbox" checked={prefs.channels.includes(channel)} onChange={() => setPrefs({ ...prefs, channels: prefs.channels.includes(channel) ? prefs.channels.filter((c) => c !== channel) : [...prefs.channels, channel] })} />
                    {channel}
                  </label>
                ))}
              </div>
              <label className="field-row">Digest
                <select value={prefs.digest} onChange={(e) => setPrefs({ ...prefs, digest: e.target.value })}>
                  <option value="instant">Instant</option><option value="daily">Daily</option><option value="weekly">Weekly</option>
                </select>
              </label>
              <div className="field-row">Quiet hours
                <span className="quiet-inputs">
                  <input type="number" min={0} max={23} value={prefs.quietHours?.[0] ?? 22} onChange={(e) => setPrefs({ ...prefs, quietHours: [Number(e.target.value), prefs.quietHours?.[1] ?? 7] })} />
                  <span>to</span>
                  <input type="number" min={0} max={23} value={prefs.quietHours?.[1] ?? 7} onChange={(e) => setPrefs({ ...prefs, quietHours: [prefs.quietHours?.[0] ?? 22, Number(e.target.value)] })} />
                </span>
              </div>
              <label className="field-row">Alert budget / analyst / day
                <input type="number" value={prefs.alertBudgetPerDay} onChange={(e) => setPrefs({ ...prefs, alertBudgetPerDay: Number(e.target.value) })} />
              </label>
              <label className="field-row">Escalate after (minutes)
                <input type="number" value={prefs.escalationMinutes} onChange={(e) => setPrefs({ ...prefs, escalationMinutes: Number(e.target.value) })} />
              </label>
              <p className="card-note">Red alerts bypass quiet hours. Every channel is dry-run in this demo.</p>
            </div>
            <div className="card">
              <span className="eyebrow">Notification outbox</span>
              <h3>Delivery & retries</h3>
              <div className="outbox-list">
                {data.notifications.slice(0, 8).map((n) => (
                  <div className="outbox-row" key={n.id}>
                    <span className={cx('outbox-status', n.status)} />
                    <div><b>{n.channel} · {n.recipient}</b><small>{n.alertId} · attempt {n.attempts} {n.error ? `· ${n.error}` : ''}</small></div>
                    {n.status === 'failed' && <button className="btn btn-sm" onClick={() => retryNotification(n.id)}>Retry</button>}
                  </div>
                ))}
              </div>
            </div>
            <div className="card">
              <span className="eyebrow">Model registry</span>
              <h3>Pinned, shadow, rollback</h3>
              {data.models.map((model) => (
                <div className="model-row" key={model.name}>
                  <div><b>{model.name}</b><small>{model.version} · {model.status} · rollback {model.rollback_to ?? '—'}</small></div>
                  <span className="model-metric">{model.metrics.precision ? `P ${pct(model.metrics.precision)}` : '—'}</span>
                  <button className="btn btn-sm" onClick={() => deployModel(model.name)}>{model.status === 'deployed' ? 'Pin' : 'Deploy'}</button>
                  {model.rollback_to && <button className="btn btn-sm btn-ghost" onClick={() => setToast(`Rollback target ${model.rollback_to} is pinned. The live registry records every rollback.`)}>Rollback</button>}
                </div>
              ))}
              <p className="card-note">Shadow versions never reach a customer alert.</p>
            </div>
            <div className="card">
              <span className="eyebrow">Pilot gates</span>
              <h3>Launch readiness</h3>
              <div className="gate-list">
                {Object.entries(data.pilot.gates).map(([gate, passed]) => <div className={cx('gate-row', passed ? 'pass' : 'fail')} key={gate}><span>{passed ? '✓' : '×'}</span><b>{gate}</b><small>{passed ? 'passed' : 'open'}</small></div>)}
              </div>
              <p className="card-note">{data.pilot.launchReady ? 'Ready for the launch gate.' : 'Do not launch: at least one gate is red.'}</p>
            </div>
            <div className="card">
              <span className="eyebrow">Escalation contacts</span>
              <h3>Who gets the alert</h3>
              <div className="contact-list">
                {prefs.recipients.map((recipient, index) => (
                  <div className="contact-row" key={`${recipient.email ?? recipient.name}-${index}`}>
                    <span>{recipient.name ?? recipient.email}</span>
                    <b>{recipient.channels?.join(' · ') ?? 'email'}</b>
                  </div>
                ))}
                <div className="contact-row"><span>Escalation</span><b>{prefs.escalationMinutes}m → team lead</b></div>
              </div>
              <p className="card-note">Least privilege: each recipient only receives the channels and scopes assigned to them.</p>
            </div>
            <div className="card">
              <span className="eyebrow">Safety</span>
              <h3>Kill switch</h3>
              <p className="card-note">Stops all acquisition, alerts and notifications for this tenant. Reversible.</p>
              <button className={cx('btn', data.killSwitch ? 'btn-danger' : '')} onClick={() => setToast('Kill switch is an API action in the live service; demo state is local.')}>
                {data.killSwitch ? 'Monitoring stopped' : 'Stop all monitoring'}
              </button>
            </div>
            <div className="card">
              <span className="eyebrow">Governance</span>
              <h3>Audit & privacy</h3>
              <div className="governance-facts">
                <span><b>{String((data.governance as { audit?: { ok?: boolean } }).audit?.ok ?? false)}</b> audit chain</span>
                <span><b>{String((data.governance as { killSwitch?: boolean }).killSwitch ?? false)}</b> kill switch</span>
                <span><b>{(data.governance as { nonGoals?: string[] }).nonGoals?.length ?? 0}</b> non-goals</span>
              </div>
              <p className="card-note">No auto-approval. No auto-dispatch. No person surveillance. No live video.</p>
            </div>
          </div>
        </section>
      )}

      {toast && <div className="watch-toast">{toast}</div>}

      <Modal open={createOpen} onClose={() => setCreateOpen(false)} className="scope-create-card" label="Create scope">
        <div className="eyebrow">New monitored scope</div>
        <h2>Make the watch explicit</h2>
        <p className="audit-sub">One purpose, one asset class, one cadence. The first acquisition is queued for human approval.</p>
        <label className="field-row">Name<input value={scopeName} onChange={(e) => setScopeName(e.target.value)} placeholder="Ahr corridor — north bank" /></label>
        <label className="field-row">Region<input value={scopeRegion} onChange={(e) => setScopeRegion(e.target.value)} /></label>
        <label className="field-row">Asset class<select value={scopeClass} onChange={(e) => setScopeClass(e.target.value)}><option>utility</option><option>insurance</option><option>agriculture</option><option>mining</option><option>construction</option></select></label>
        <label className="field-row">Cadence<select value={scopeCadence} onChange={(e) => setScopeCadence(e.target.value)}><option>6h</option><option>12h</option><option>daily</option><option>weekly</option></select></label>
        <label className="field-row">Change type<select value={scopeChange} onChange={(e) => setScopeChange(e.target.value)}><option>flood</option><option>wildfire</option><option>construction</option><option>vegetation</option><option>erosion</option></select></label>
        <div className="scope-bbox">{draftBbox ? `Drawn bbox: ${draftBbox.map((v) => v.toFixed(3)).join(', ')}` : 'No bbox drawn — the default demo bbox will be used.'}</div>
        <div className="modal-actions"><button className="btn btn-primary" onClick={createScope}>Create scope</button><button className="btn btn-ghost" onClick={() => setCreateOpen(false)}>Cancel</button></div>
      </Modal>
    </div>
  )
}
