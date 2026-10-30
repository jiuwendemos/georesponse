import { useEffect, useMemo, useRef, useState } from 'react'
import { useApp } from '../store'
import { usePrefs } from '../prefs'
import { useUi } from '../ui-context'
import { dataPath, loadJson } from '../lib/data'
import type { ProactiveData } from '../types'
import { Icon } from './ui'
import { Kbd } from './ds'

interface Command {
  id: string
  label: string
  group: string
  icon: string
  hint?: string
  run: () => void
}

export default function CommandPalette() {
  const app = useApp()
  const prefs = usePrefs()
  const ui = useUi()
  const [query, setQuery] = useState('')
  const [active, setActive] = useState(0)
  const [proactive, setProactive] = useState<ProactiveData | null>(null)
  const input = useRef<HTMLInputElement | null>(null)

  useEffect(() => {
    if (!ui.paletteOpen) return
    setQuery('')
    setActive(0)
    window.setTimeout(() => input.current?.focus(), 30)
    loadJson<ProactiveData>(dataPath('proactive.json')).then(setProactive).catch(() => undefined)
  }, [ui.paletteOpen])

  const commands = useMemo<Command[]>(() => {
    const close = (run: () => void) => () => {
      ui.closePalette()
      run()
    }
    const nav: Command[] = [
      { id: 'nav-stage', label: prefs.t('nav.stage'), group: 'Navigate', icon: 'play', run: close(() => app.setMode('stage')) },
      { id: 'nav-watch', label: prefs.t('nav.watch'), group: 'Navigate', icon: 'radar', run: close(() => app.setMode('watch')) },
      { id: 'nav-analyst', label: prefs.t('nav.analyst'), group: 'Navigate', icon: 'map', run: close(() => app.setMode('analyst')) },
      { id: 'nav-pilot', label: prefs.t('nav.pilot'), group: 'Navigate', icon: 'chart', run: close(() => app.setMode('dashboard')) },
      { id: 'nav-method', label: prefs.t('nav.method'), group: 'Navigate', icon: 'book', run: close(() => app.setMode('method')) },
      { id: 'nav-booth', label: prefs.t('nav.booth'), group: 'Navigate', icon: 'vote', run: close(() => app.setMode('booth')) },
    ]
    const actions: Command[] = [
      { id: 'agent', label: 'Ask GeoResponse', group: 'Actions', icon: 'spark', hint: 'local tools', run: close(() => ui.openAgent()) },
      { id: 'design', label: 'Open design system', group: 'Actions', icon: 'grid', run: close(() => ui.openStyleGuide()) },
      { id: 'settings', label: 'Open settings', group: 'Actions', icon: 'sliders', run: close(() => ui.openSettings()) },
      { id: 'offline', label: 'Save offline pack', group: 'Actions', icon: 'download', run: close(() => void app.saveOffline()) },
      { id: 'reset', label: 'Reset the stage', group: 'Actions', icon: 'reset', run: close(() => { app.setMode('stage'); app.reset() }) },
      { id: 'field', label: 'Open field order', group: 'Actions', icon: 'print', run: close(() => app.openFieldOrder(true)) },
      { id: 'report', label: 'Open assessment', group: 'Actions', icon: 'book', run: close(() => app.openReport(true)) },
    ]
    const theme: Command[] = [
      { id: 'theme-system', label: `${prefs.t('action.theme')}: ${prefs.t('theme.system')}`, group: 'Preferences', icon: 'sliders', run: close(() => prefs.setTheme('system')) },
      { id: 'theme-light', label: `${prefs.t('action.theme')}: ${prefs.t('theme.light')}`, group: 'Preferences', icon: 'sun', run: close(() => prefs.setTheme('light')) },
      { id: 'theme-dark', label: `${prefs.t('action.theme')}: ${prefs.t('theme.dark')}`, group: 'Preferences', icon: 'moon', run: close(() => prefs.setTheme('dark')) },
      { id: 'theme-contrast', label: `${prefs.t('action.theme')}: ${prefs.t('theme.contrast')}`, group: 'Preferences', icon: 'sliders', run: close(() => prefs.setTheme('contrast')) },
      { id: 'density-comfortable', label: `Density: ${prefs.t('density.comfortable')}`, group: 'Preferences', icon: 'sliders', run: close(() => prefs.setDensity('comfortable')) },
      { id: 'density-compact', label: `Density: ${prefs.t('density.compact')}`, group: 'Preferences', icon: 'sliders', run: close(() => prefs.setDensity('compact')) },
      { id: 'lang-en', label: 'Language: English', group: 'Preferences', icon: 'book', run: close(() => prefs.setLanguage('en')) },
      { id: 'lang-de', label: 'Sprache: Deutsch', group: 'Preferences', icon: 'book', run: close(() => prefs.setLanguage('de')) },
    ]
    const scenarios: Command[] = (app.index?.scenarios ?? []).map((entry) => ({
      id: `scenario-${entry.id}`,
      label: `Scenario: ${entry.title}`,
      group: 'Scenarios',
      icon: 'radar',
      run: close(() => app.selectScenario(entry.id)),
    }))
    const sites: Command[] = (app.scenario?.sites ?? []).slice(0, 12).map((site) => ({
      id: `site-${site.id}`,
      label: `${site.id} · ${site.name}`,
      group: 'Sites',
      icon: 'pin',
      hint: site.accessStatus,
      run: close(() => {
        app.setMode('stage')
        app.selectSite(site.id)
      }),
    }))
    const alerts: Command[] = (proactive?.alerts ?? []).slice(0, 10).map((alert) => ({
      id: `alert-${alert.id}`,
      label: `${alert.severity.toUpperCase()} · ${alert.title}`,
      group: 'Watch alerts',
      icon: 'radar',
      hint: alert.status,
      run: close(() => app.openWatchAlert(alert.id)),
    }))
    return [...nav, ...actions, ...theme, ...scenarios, ...sites, ...alerts]
  }, [app, prefs, proactive, ui])

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return commands
    return commands.filter((command) => `${command.label} ${command.group} ${command.hint ?? ''}`.toLowerCase().includes(q))
  }, [commands, query])

  const grouped = useMemo(() => {
    const groups = new Map<string, Command[]>()
    for (const command of filtered) {
      groups.set(command.group, [...(groups.get(command.group) ?? []), command])
    }
    return Array.from(groups.entries())
  }, [filtered])

  useEffect(() => {
    setActive(0)
  }, [query])

  if (!ui.paletteOpen) return null

  const run = (command: Command) => command.run()

  return (
    <div className="palette-backdrop" onMouseDown={ui.closePalette}>
      <div className="palette" role="dialog" aria-modal="true" aria-label="Command palette" onMouseDown={(event) => event.stopPropagation()}>
        <div className="palette-input-row">
          <Icon name="search" size={18} />
          <input
            ref={input}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'ArrowDown') {
                event.preventDefault()
                setActive((value) => Math.min(filtered.length - 1, value + 1))
              } else if (event.key === 'ArrowUp') {
                event.preventDefault()
                setActive((value) => Math.max(0, value - 1))
              } else if (event.key === 'Enter' && filtered[active]) {
                event.preventDefault()
                run(filtered[active])
              } else if (event.key === 'Escape') {
                ui.closePalette()
              }
            }}
            placeholder="Search actions, scopes, sites and alerts…"
            aria-label="Search commands"
          />
          <Kbd>Esc</Kbd>
        </div>
        <div className="palette-list" role="listbox" aria-label="Commands">
          {grouped.map(([group, items]) => (
            <div className="palette-group" key={group}>
              <span className="palette-group-label">{group}</span>
              {items.map((command) => {
                const index = filtered.indexOf(command)
                return (
                  <button
                    key={command.id}
                    className={`palette-item ${index === active ? 'active' : ''}`}
                    onMouseEnter={() => setActive(index)}
                    onClick={() => run(command)}
                    role="option"
                    aria-selected={index === active}
                  >
                    <span className="palette-icon"><Icon name={command.icon} size={15} /></span>
                    <span>{command.label}</span>
                    {command.hint && <small>{command.hint}</small>}
                    <span className="palette-enter">↵</span>
                  </button>
                )
              })}
            </div>
          ))}
          {!filtered.length && <div className="palette-empty">No command matches “{query}”. Try “light mode”, “Watch” or “design system”.</div>}
        </div>
        <footer className="palette-foot">
          <span><Kbd>↑</Kbd><Kbd>↓</Kbd> navigate</span>
          <span><Kbd>↵</Kbd> run</span>
          <span><Kbd>Esc</Kbd> close</span>
          <span className="palette-ai"><Icon name="spark" size={12} /> ask anything with ⌘K → Ask</span>
        </footer>
      </div>
    </div>
  )
}
