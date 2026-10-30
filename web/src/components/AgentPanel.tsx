import { useEffect, useRef, useState } from 'react'
import { useApp } from '../store'
import { usePrefs } from '../prefs'
import { useUi } from '../ui-context'
import { dataPath, loadJson } from '../lib/data'
import { parseIntent, SUGGESTIONS } from '../lib/agent'
import type { ProactiveData } from '../types'
import { Icon } from './ui'
import { Badge, Kbd } from './ds'

interface AgentAction {
  label: string
  run: () => void | Promise<void>
  undo?: () => void | Promise<void>
}

interface Result {
  label: string
  meta: string
  run: () => void
}

interface Message {
  id: number
  role: 'user' | 'agent'
  text: string
  steps?: string[]
  action?: AgentAction
  results?: Result[]
  applied?: boolean
  tone?: 'normal' | 'warn' | 'refuse'
}

let messageId = 0

export default function AgentPanel() {
  const app = useApp()
  const prefs = usePrefs()
  const ui = useUi()
  const [messages, setMessages] = useState<Message[]>([
    {
      id: ++messageId,
      role: 'agent',
      text: 'I can navigate, brief you, change the interface, explain an alert or prepare an action for your approval. I use local tools only — no external model sees your data.',
      steps: ['local intent parser', 'current scenario + Watch pack'],
    },
  ])
  const [input, setInput] = useState('')
  const [thinking, setThinking] = useState(false)
  const [proactive, setProactive] = useState<ProactiveData | null>(null)
  const [live, setLive] = useState<boolean | null>(null)
  const [liveModel, setLiveModel] = useState<string>('')
  const timer = useRef<number | null>(null)
  const liveRef = useRef(false)
  const lastSeed = useRef('')
  const log = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    liveRef.current = Boolean(live)
  }, [live])

  useEffect(() => {
    if (!ui.agentOpen) return
    loadJson<ProactiveData>(dataPath('proactive.json')).then(setProactive).catch(() => undefined)
    fetch('/api/watch/production/agent/health')
      .then((response) => (response.ok ? response.json() : null))
      .then((health) => {
        setLive(Boolean(health?.configured))
        setLiveModel(String(health?.model ?? ''))
      })
      .catch(() => setLive(false))
  }, [ui.agentOpen])

  useEffect(() => {
    if (!ui.agentOpen || !ui.agentSeed || ui.agentSeed === lastSeed.current) return
    lastSeed.current = ui.agentSeed
    setInput(ui.agentSeed)
    window.setTimeout(() => submit(ui.agentSeed), 80)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ui.agentOpen, ui.agentSeed])

  useEffect(() => {
    log.current?.scrollTo({ top: log.current.scrollHeight, behavior: prefs.motion ? 'smooth' : 'auto' })
  }, [messages, prefs.motion])

  const openWatch = (alertId: string) => {
    app.openWatchAlert(alertId)
    ui.closeAgent()
  }

  const push = (message: Omit<Message, 'id'>) => setMessages((items) => [...items, { ...message, id: ++messageId }])

  const submit = (raw: string) => {
    const query = raw.trim()
    if (!query || thinking) return
    push({ role: 'user', text: query })
    setInput('')
    setThinking(true)
    if (liveRef.current) {
      const history = messages.filter((message) => message.role === 'user' || message.role === 'agent').slice(-6).map((message) => ({ role: message.role === 'user' ? 'user' : 'assistant', content: message.text }))
      fetch('/api/watch/production/agent/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: query,
          history,
          tenant: 'demo',
          context: {
            mode: app.mode,
            scenarioId: app.scenario?.meta.id,
            alertId: new URLSearchParams(window.location.hash.slice(1)).get('alert') ?? undefined,
            scopeId: new URLSearchParams(window.location.hash.slice(1)).get('scope') ?? undefined,
          },
        }),
      })
        .then(async (response) => {
          if (!response.ok) throw new Error((await response.json().catch(() => ({}))).detail || `agent HTTP ${response.status}`)
          return response.json()
        })
        .then((result) => {
          const steps = (result.trace ?? []).map((step: { tool: string; arguments: Record<string, unknown> }) => `${step.tool}(${Object.keys(step.arguments ?? {}).join(', ')})`)
          const proposals = (result.proposals ?? []).map((proposal: { id?: string; action: string; alertId: string; reason?: string; target?: string; team?: string }) => ({
            label: proposal.action === 'assign'
              ? `Open ${proposal.alertId} to assign ${proposal.team ?? 'a team'}`
              : proposal.action === 'dismiss'
                ? `Dismiss ${proposal.alertId} as ${proposal.reason}`
                : `Prepare ${proposal.target} draft for ${proposal.alertId}`,
            run: async () => {
              if (proposal.id) {
                const response = await fetch(`/api/watch/proposals/${proposal.id}/approve`, {
                  method: 'POST',
                  headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({ actor: 'analyst', reason: 'Approved from agent panel' }),
                })
                if (!response.ok) throw new Error((await response.json().catch(() => ({}))).detail || 'proposal approval failed')
              }
              app.openWatchAlert(proposal.alertId)
            },
          }))
          push({
            role: 'agent',
            text: result.answer || 'The live agent returned no text.',
            steps: [`live model · ${result.model ?? liveModel}`, ...steps],
            results: proposals,
          })
          setThinking(false)
        })
        .catch((error) => {
          setLive(false)
          liveRef.current = false
          push({ role: 'agent', text: `Live agent unavailable (${String(error.message ?? error)}). Falling back to deterministic local tools.`, steps: ['live.fallback'] })
          setThinking(false)
          window.setTimeout(() => submit(query), 0)
        })
      return
    }
    if (timer.current) window.clearTimeout(timer.current)
    timer.current = window.setTimeout(() => {
      const intent = parseIntent(query)
      const steps: string[] = ['intent.parse']
      let text = ''
      let action: AgentAction | undefined
      let results: Result[] | undefined
      let tone: Message['tone'] = 'normal'

      switch (intent.kind) {
        case 'navigate': {
          const labels: Record<string, string> = { stage: 'Stage', watch: 'Watch', analyst: 'Analyst', dashboard: 'Pilot', method: 'Method', booth: 'Booth' }
          app.setMode(intent.target)
          steps.push('workspace.open')
          text = `${labels[intent.target]} is open.`
          break
        }
        case 'theme': {
          prefs.setTheme(intent.theme)
          steps.push('theme.set')
          text = `Theme set to ${intent.theme}. The map stays dark, the chrome adapts.`
          break
        }
        case 'density': {
          prefs.setDensity(intent.density)
          steps.push('density.set')
          text = `Density set to ${intent.density}.`
          break
        }
        case 'motion': {
          prefs.setMotion(intent.enabled)
          steps.push('motion.set')
          text = `Motion ${intent.enabled ? 'enabled' : 'reduced'}.`
          break
        }
        case 'language': {
          prefs.setLanguage(intent.language)
          steps.push('language.set')
          text = intent.language === 'de' ? 'Sprache auf Deutsch gestellt.' : 'Language set to English.'
          break
        }
        case 'assign': {
          const top = app.ranked[0]
          if (!top) { text = 'There is no active site to assign.'; break }
          const previous = app.assignments[top.site.id]
          action = {
            label: `Assign ${intent.team} to ${top.site.name}`,
            run: () => {
              app.setMode('stage')
              app.selectSite(top.site.id)
              app.assign(top.site.id, intent.team)
            },
            undo: () => {
              if (previous) app.assign(top.site.id, previous)
              else app.unassign(top.site.id)
            },
          }
          steps.push('ranking.read', 'assignment.preview')
          text = `${intent.team} would go to ${top.site.name} (#${top.rank}, ${Math.round(top.site.confidence * 100)}% confidence). Review the action before applying.`
          break
        }
        case 'scrub': {
          if (intent.time === null || !app.scenario) { text = 'Tell me a time between 12:00 and 18:00.'; break }
          const previous = app.time
          action = {
            label: `Scrub to ${intent.time}:00`,
            run: () => { app.setMode('stage'); app.setTime(intent.time as number) },
            undo: () => app.setTime(previous),
          }
          steps.push('timeline.preview')
          text = `The timeline would move to ${intent.time}:00. The flood edge and site risk will update.`
          break
        }
        case 'reject-false-positive': {
          const fp = app.scenario?.falsePositive
          if (!fp) { text = 'This scenario has no false-positive finding.'; break }
          const site = app.scenario?.sites.find((s) => s.id === fp.siteId)
          const previous = app.reviews[fp.siteId] ?? 'pending'
          action = {
            label: `Reject ${fp.siteId} · ${site?.name ?? 'finding'}`,
            run: () => app.review(fp.siteId, 'rejected'),
            undo: () => app.review(fp.siteId, previous),
          }
          steps.push('review.preview', 'ranking.reorder')
          text = `Rejecting ${fp.siteId} removes it from the ranking and frees any team assigned to it. The reason is recorded.`
          break
        }
        case 'open-report':
          action = { label: 'Open the assessment', run: () => app.openReport(true), undo: () => app.openReport(false) }
          steps.push('assessment.open')
          text = 'The human-signed assessment is ready to open. I will not sign it for you.'
          break
        case 'open-field-order':
          action = { label: 'Open the field order', run: () => app.openFieldOrder(true), undo: () => app.openFieldOrder(false) }
          steps.push('field-order.open')
          text = 'The one-page field order is ready. Review the teams before printing.'
          break
        case 'offline':
          action = { label: 'Save the offline pack', run: () => app.saveOffline() }
          steps.push('offline.precache')
          text = 'I can pre-cache the current scenario, evidence and Watch pack for offline use.'
          break
        case 'explain-alert': {
          const alert = proactive?.alerts.find((a) => a.id === intent.alertId)
          if (!alert) { text = `I could not find ${intent.alertId} in the local Watch pack.`; break }
          steps.push('alert.read', 'evidence.read', 'explanation.compose')
          text = `${alert.title}. ${alert.summary} Confidence ${Math.round(alert.confidence * 100)}%, status ${alert.status}, owner ${alert.assignee ?? 'unassigned'}. The evidence is in Watch.`
          results = [{ label: `Open ${alert.id} in Watch`, meta: `${alert.severity} · ${alert.status}`, run: () => openWatch(alert.id) }]
          break
        }
        case 'search-alerts': {
          const words = intent.query.toLowerCase().split(/\s+/)
          const matches = (proactive?.alerts ?? [])
            .filter((alert) => words.some((word) => `${alert.title} ${alert.scope_id} ${alert.change_type} ${alert.severity}`.toLowerCase().includes(word)))
            .slice(0, 5)
          steps.push('alerts.search', 'ranking.sort')
          text = matches.length ? `${matches.length} alert(s) match. Open one in Watch to review the evidence.` : 'No matching alert in the local pack.'
          results = matches.map((alert) => ({
            label: alert.title,
            meta: `${alert.severity} · ${alert.status} · ${Math.round(alert.confidence * 100)}%`,
            run: () => openWatch(alert.id),
          }))
          break
        }
        case 'briefing': {
          const top = app.ranked[0]?.site
          const open = proactive?.alerts.filter((alert) => ['new', 'acknowledged', 'assigned', 'investigating'].includes(alert.status)).length ?? 0
          steps.push('scenario.read', 'alerts.read', 'briefing.compose')
          text = app.scenario
            ? `${app.scenario.meta.title}: ${app.ranked.length} active sites. Top risk: ${top?.name ?? 'none'}. Watch has ${open} open alerts. ${proactive ? `${proactive.dashboard.slaBreaches} SLA breach(es).` : ''}`
            : 'The scenario is still loading.'
          break
        }
        case 'design-system':
          ui.openStyleGuide()
          steps.push('design-system.open')
          text = 'The living design system is open: tokens, type, components and themes.'
          break
        case 'help':
          text = 'I can navigate, brief you, explain an alert, change theme/density/language, scrub the timeline, suggest a team assignment, reject the false positive, or open the assessment, field order and offline pack. Anything that changes data requires your approval.'
          steps.push('capability.list')
          break
        case 'refuse':
          tone = 'refuse'
          steps.push('safety.refuse')
          text = intent.reason
          break
        default:
          steps.push('intent.unknown')
          text = `I did not map “${intent.query}” to a safe local action. Try “Brief me”, “Open Watch”, “Explain ALT-1001” or “Switch to light mode”.`
      }

      push({ role: 'agent', text, steps, action, results, tone })
      setThinking(false)
      timer.current = null
    }, 280)
  }

  const apply = (message: Message) => {
    if (!message.action) return
    void message.action.run()
    setMessages((items) => items.map((item) => (item.id === message.id ? { ...item, applied: true } : item)))
    push({ role: 'agent', text: `Applied: ${message.action.label}. You can undo it from this card.`, steps: ['action.apply', 'audit.append'] })
  }

  const undo = (message: Message) => {
    if (!message.action?.undo) return
    void message.action.undo()
    setMessages((items) => items.map((item) => (item.id === message.id ? { ...item, applied: false } : item)))
    push({ role: 'agent', text: 'Undone. The previous state is restored.', steps: ['action.undo'] })
  }

  const stop = () => {
    if (timer.current) window.clearTimeout(timer.current)
    timer.current = null
    setThinking(false)
    push({ role: 'agent', text: 'Stopped. Nothing was applied.' })
  }

  if (!ui.agentOpen) return null

  return (
    <div className="agent-scrim" onMouseDown={ui.closeAgent}>
      <aside className="agent-panel" role="dialog" aria-modal="true" aria-label={prefs.t('agent.title')} onMouseDown={(event) => event.stopPropagation()}>
        <header className="agent-head">
          <div className="agent-title">
            <span className="agent-orb"><Icon name="spark" size={16} /></span>
            <div><b>{prefs.t('agent.title')}</b><small>{live ? `live model · ${liveModel || 'configured'}` : 'local tools · approval required'}</small></div>
          </div>
          <button className="icon-btn" onClick={ui.closeAgent} aria-label="Close agent"><Icon name="close" size={16} /></button>
        </header>
        <div className="agent-grounding">
          <Badge tone="info">grounded</Badge>
          <span>Current scenario · Watch pack · audit</span>
          <Badge tone={live ? 'success' : 'warn'}>{live ? prefs.t('agent.live') : prefs.t('agent.local')}</Badge>
        </div>
        <div className="agent-log" ref={log} aria-live="polite">
          {messages.map((message) => (
            <div key={message.id} className={`agent-msg agent-${message.role} ${message.tone === 'refuse' ? 'agent-refuse' : ''}`}>
              <div className="agent-msg-head"><span>{message.role === 'user' ? 'You' : 'GeoResponse'}</span>{message.role === 'agent' && <small>local</small>}</div>
              <p>{message.text}</p>
              {message.steps && message.steps.length > 0 && (
                <details className="agent-steps">
                  <summary>{message.steps.length} tool step(s)</summary>
                  <ol>{message.steps.map((step) => <li key={step}>{step}</li>)}</ol>
                </details>
              )}
              {message.results && message.results.length > 0 && (
                <div className="agent-results">
                  {message.results.map((result) => (
                    <button key={result.label} className="agent-result" onClick={result.run}>
                      <span>{result.label}</span><small>{result.meta}</small>
                    </button>
                  ))}
                </div>
              )}
              {message.action && (
                <div className="agent-action">
                  <div><span>Action preview</span><b>{message.action.label}</b><small>Requires your approval. Reversible.</small></div>
                  {message.applied ? (
                    <button className="btn btn-sm" onClick={() => undo(message)}>Undo</button>
                  ) : (
                    <button className="btn btn-primary btn-sm" onClick={() => apply(message)}>Apply</button>
                  )}
                </div>
              )}
            </div>
          ))}
          {thinking && (
            <div className="agent-msg agent-agent agent-thinking">
              <span className="typing"><i /><i /><i /></span>
              <button className="btn btn-sm btn-ghost" onClick={stop}>Stop</button>
            </div>
          )}
        </div>
        {messages.length < 3 && (
          <div className="agent-suggestions">
            {SUGGESTIONS.slice(0, 5).map((suggestion) => (
              <button key={suggestion} className="agent-chip" onClick={() => submit(suggestion)}>{suggestion}</button>
            ))}
          </div>
        )}
        <form
          className="agent-input-row"
          onSubmit={(event) => {
            event.preventDefault()
            submit(input)
          }}
        >
          <input value={input} onChange={(event) => setInput(event.target.value)} placeholder="Ask for a decision, filter or action…" aria-label="Ask GeoResponse" />
          <button className="btn btn-primary" type="submit" disabled={!input.trim() || thinking}>{prefs.t('agent.send')}</button>
        </form>
        <div className="agent-foot"><span><Kbd>⌘K</Kbd> command palette</span><span>No auto-approval · no auto-dispatch</span></div>
      </aside>
    </div>
  )
}
