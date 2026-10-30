import { useEffect, useMemo, useState } from 'react'
import { useApp } from '../store'
import MapView from './MapView'
import SiteDetail from './SiteDetail'
import { Icon, SeverityChip } from './ui'
import { clamp } from '../lib/math'
import { compactEuro, cx, missionClock, number, pct, timeLabel } from '../lib/format'

const BEATS = [
  { id: 1, label: 'Scrub the flood edge to 18:00', hint: 'The answer is time-dependent.' },
  { id: 2, label: 'Inspect the #1 ranked site', hint: 'Access + power + people.' },
  { id: 3, label: 'Reject the confident false positive', hint: 'The human beats the model.' },
  { id: 4, label: 'Let the room choose Team 3', hint: 'Two defensible sites. One trade-off.' },
  { id: 5, label: 'Assign the three teams', hint: 'Coverage and response time update.' },
  { id: 6, label: 'Reveal the field order', hint: '40 km², 18 sites, 42 minutes.' },
]

export default function Stage() {
  const app = useApp()
  const scenario = app.scenario
  const [playing, setPlaying] = useState(false)
  const [votePreview, setVotePreview] = useState<'a' | 'b' | null>(null)

  const selected = scenario?.sites.find((site) => site.id === app.selectedId)
  const selectedRank = app.ranked.find((item) => item.site.id === selected?.id)?.rank ?? 0
  const latest = useMemo(() => {
    if (!scenario) return null
    const frames = scenario.timeline.frames.filter((f) => f.t <= app.time + 0.001)
    return frames.length ? frames[frames.length - 1] : scenario.timeline.frames[0]
  }, [scenario, app.time])

  useEffect(() => {
    if (!scenario) return
    if (app.time >= scenario.timeline.end - 0.001 && app.phase < 1) app.setPhase(1)
    if (app.selectedId && app.phase < 2) app.setPhase(2)
  }, [app, scenario])

  useEffect(() => {
    if (!playing || !scenario) return
    const timer = window.setInterval(() => {
      app.setTime((current) => {
        const next = current + scenario.timeline.step
        if (next >= scenario.timeline.end) {
          setPlaying(false)
          return scenario.timeline.end
        }
        return next
      })
    }, 380)
    return () => window.clearInterval(timer)
  }, [playing, scenario, app])

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.target instanceof HTMLInputElement || event.target instanceof HTMLTextAreaElement) return
      if (event.key.toLowerCase() === 'r') {
        event.preventDefault()
        app.reset()
      }
      if (event.code === 'Space') {
        event.preventDefault()
        setPlaying((value) => !value)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [app])

  if (!scenario) return null

  const teams = Array.from({ length: scenario.meta.teams }, (_, i) => `Team ${i + 1}`)
  const teamSites = teams.map((team) => ({
    team,
    site: scenario.sites.find((site) => app.assignments[site.id] === team),
  }))
  const rejected = Object.values(app.reviews).filter((status) => status === 'rejected').length
  const falsePositiveRejected = scenario.falsePositive
    ? app.reviews[scenario.falsePositive.siteId] === 'rejected'
    : true

  const beatDone = (id: number): boolean => {
    switch (id) {
      case 1:
        return app.time >= scenario.timeline.end - 0.001
      case 2:
        return Boolean(app.selectedId)
      case 3:
        return falsePositiveRejected
      case 4:
        return Boolean(app.vote)
      case 5:
        return app.teamsAssigned >= scenario.meta.teams
      default:
        return app.reportOpen || app.fieldOrderOpen || app.phase >= 5
    }
  }

  const runBeat = (id: number) => {
    if (id === 1) app.setTime(scenario.timeline.end)
    if (id === 2) {
      const top = app.ranked[0]
      if (top) app.selectSite(top.site.id)
    }
    if (id === 3) {
      if (scenario.falsePositive) app.review(scenario.falsePositive.siteId, 'rejected')
      else app.setPhase(3)
    }
    if (id === 4) {
      app.setPhase(4)
      const candidate = scenario.audience.a
      if (candidate) {
        app.previewSite(candidate.id)
        app.selectSite(candidate.id)
      }
    }
    if (id === 5) app.autoAssign()
    if (id === 6) app.reveal()
  }

  const voteCandidate = votePreview ?? app.vote ?? 'a'
  const candidate = scenario.audience[voteCandidate]

  return (
    <div className="stage">
      <MapView variant="stage" />

      <div className="stage-clock">
        <span className="live-dot" />
        <b>{missionClock(app.phase)}</b>
        <span className="clock-sep" />
        <span>{scenario.meta.areaKm2.toFixed(0)} km²</span>
        <span className="clock-sep" />
        <span>{app.ranked.length} sites</span>
        <span className="clock-sep" />
        <span>{scenario.meta.teams} teams</span>
        {latest && scenario.timeline.mode === 'time' && (
          <>
            <span className="clock-sep" />
            <span className="clock-area">{latest.areaKm2.toFixed(1)} km² water</span>
          </>
        )}
      </div>

      <section className="hud mission">
        <div className="eyebrow">
          <span className="dot" />
          {scenario.meta.hazard === 'flood' ? 'Flood response' : scenario.meta.hazard === 'wildfire' ? 'Wildfire response' : 'Construction watch'} · {scenario.meta.eventTime}
        </div>
        <h1>Assign {scenario.meta.teams} teams<br />to the highest-risk sites.</h1>
        <p>
          {scenario.timeline.caption}. Scrub time, check the why chain and assign teams before the window closes.
        </p>

        <div className="mission-stats">
          <div>
            <b>{app.ranked.length}</b>
            <span>priority sites</span>
          </div>
          <div>
            <b>
              {app.teamsAssigned}/{scenario.meta.teams}
            </b>
            <span>teams assigned</span>
          </div>
          <div>
            <b>{rejected}</b>
            <span>rejected</span>
          </div>
        </div>

        <div className="team-list">
          {teamSites.map(({ team, site }) => (
            <div className={cx('team-row', site && 'filled')} key={team}>
              <span className="team-name">{team}</span>
              {site ? (
                <>
                  <button className="team-site" onClick={() => app.selectSite(site.id)}>
                    {site.name}
                  </button>
                  <button className="team-free" onClick={() => app.unassign(site.id)} title="Free team">
                    <Icon name="close" size={12} />
                  </button>
                </>
              ) : (
                <span className="team-empty">unassigned</span>
              )}
            </div>
          ))}
        </div>

        <div className="mission-actions">
          <button
            className="btn btn-primary"
            onClick={app.reveal}
            disabled={app.teamsAssigned < scenario.meta.teams}
            title={app.teamsAssigned < scenario.meta.teams ? 'Assign all teams first' : 'Reveal the assessment'}
          >
            Run assessment
          </button>
          <button className="btn btn-ghost" onClick={app.reset}>
            <Icon name="reset" size={13} /> Reset
          </button>
        </div>

        <div className="beats">
          <div className="beats-head">
            <span>90-second story</span>
            <span>{BEATS.filter((beat) => beatDone(beat.id)).length}/6</span>
          </div>
          {BEATS.map((beat) => (
            <button
              key={beat.id}
              className={cx('beat', beatDone(beat.id) && 'done')}
              onClick={() => runBeat(beat.id)}
              title={beat.hint}
            >
              <span className="beat-index">{beatDone(beat.id) ? <Icon name="check" size={11} /> : beat.id}</span>
              <span>{beat.label}</span>
            </button>
          ))}
        </div>
      </section>

      <aside className="hud layers">
        <h2>Layers</h2>
        {(
          [
            ['flood', 'Change', scenario.meta.hazard === 'flood' ? '#22d3ee' : scenario.meta.hazard === 'wildfire' ? '#f97316' : '#a78bfa'],
            ['roads', 'Roads', '#d3c7a8'],
            ['power', 'Power', '#fbbf24'],
            ['buildings', 'Buildings', '#7b8b93'],
            ['landuse', 'Land use', '#2a361a'],
          ] as const
        ).map(([key, label, color]) => (
          <label className="layer" key={key}>
            <input type="checkbox" checked={app.layers[key]} onChange={() => app.toggleLayer(key)} />
            <span className="swatch" style={{ background: color }} />
            {label}
          </label>
        ))}
        <div className="layers-foot">
          <span className="live-dot" /> offline pack
        </div>
      </aside>

      <div className="hud legend">
        <span className="legend-red">High risk</span>
        <span className="legend-amber">Watch</span>
        <span className="legend-cyan">Change</span>
        <span className="legend-green">Team assigned</span>
        <span className="legend-white">Rejected</span>
      </div>

      {selected && <SiteDetail site={selected} rank={selectedRank} mode="stage" />}

      {app.phase >= 4 && !app.vote && scenario.audience.a && scenario.audience.b && (
        <section className="vote-panel" aria-label="Audience choice">
          <div className="vote-head">
            <div>
              <div className="eyebrow">
                <span className="dot" /> Audience choice · Team {scenario.meta.teams}
              </div>
              <h2>{scenario.audience.prompt}</h2>
            </div>
            <button className="icon-btn" onClick={() => app.setPhase(3)} aria-label="Close vote">
              <Icon name="close" size={15} />
            </button>
          </div>
          <div className="vote-options">
            {(['a', 'b'] as const).map((key) => {
              const option = scenario.audience[key]
              if (!option) return null
              return (
                <button
                  key={key}
                  className={cx('vote-option', votePreview === key && 'active')}
                  onMouseEnter={() => {
                    setVotePreview(key)
                    app.previewSite(option.id)
                  }}
                  onMouseLeave={() => app.previewSite(null)}
                  onClick={() => app.voteAudience(key)}
                >
                  <div className="vote-option-head">
                    <span className="vote-letter">{key.toUpperCase()}</span>
                    <SeverityChip severity={option.severity} small />
                    <span className="vote-response">{option.responseMinutes}′ response</span>
                  </div>
                  <b>{option.name}</b>
                  <span className="vote-meta">
                    {compactEuro(option.valueEur)} · {number(option.population)} people · {option.access} access
                  </span>
                  <small>{option.consequence}</small>
                </button>
              )
            })}
          </div>
          <div className="vote-foot">
            <span className="vote-tradeoff">{scenario.audience.tradeoff}</span>
            {candidate && (
              <button className="btn btn-primary" onClick={() => app.voteAudience(voteCandidate)}>
                Send Team {scenario.meta.teams} to {candidate.id} <Icon name="arrow" size={13} />
              </button>
            )}
          </div>
        </section>
      )}

      {app.vote && scenario.audience[app.vote] && (
        <div className="vote-confirm">
          <span className="live-dot" />
          Team {scenario.meta.teams} committed to <b>{scenario.audience[app.vote]?.name}</b>. {scenario.audience.tradeoff}
        </div>
      )}

      <div className="hud timeline">
        <div className="time-row">
          <button className="play-btn" onClick={() => setPlaying((value) => !value)} aria-label={playing ? 'Pause' : 'Play'}>
            <Icon name={playing ? 'pause' : 'play'} size={13} />
          </button>
          <b>{scenario.timeline.mode === 'time' ? timeLabel(app.time) : latest?.label ?? ''}</b>
          <span>{scenario.timeline.caption}</span>
          <span className="timeline-area">{latest ? `${latest.areaKm2.toFixed(1)} km²` : ''}</span>
        </div>
        <input
          type="range"
          min={scenario.timeline.start}
          max={scenario.timeline.end}
          step={scenario.timeline.step}
          value={clamp(app.time, scenario.timeline.start, scenario.timeline.end)}
          onChange={(event) => app.setTime(Number(event.target.value))}
          aria-label={scenario.timeline.caption}
        />
        <div className="ticks">
          {[scenario.timeline.frames[0], scenario.timeline.frames[Math.floor(scenario.timeline.frames.length / 2)], scenario.timeline.frames[scenario.timeline.frames.length - 1]].map(
            (frame) => (
              <span key={frame.t}>{frame.label}</span>
            ),
          )}
        </div>
      </div>

      {app.phase >= 5 && !app.reportOpen && !app.fieldOrderOpen && (
        <div className="reveal-banner">
          <div>
            <span className="eyebrow">Assessment ready · {scenario.meta.assessmentMinutes} minutes</span>
            <b>“{scenario.hero.quote}”</b>
          </div>
          <button className="btn btn-primary" onClick={() => app.openReport(true)}>
            Open assessment
          </button>
          <button className="btn" onClick={() => app.openFieldOrder(true)}>
            Field order
          </button>
        </div>
      )}

      <div className="stage-hint">
        <span><kbd>R</kbd> reset</span>
        <span><kbd>Space</kbd> play</span>
        <span>{scenario.meta.imagery.simulated ? 'simulated imagery' : 'live imagery'}</span>
        <span>{pct(app.ranked[0]?.site.confidence ?? 0)} top confidence</span>
      </div>
    </div>
  )
}
