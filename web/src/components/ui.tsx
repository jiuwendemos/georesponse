import { useEffect, useRef, type ReactNode } from 'react'
import { useApp } from '../store'
import { allowedViews, usePrefs } from '../prefs'
import { useUi } from '../ui-context'
import { IconButton, Kbd } from './ds'
import { cx } from '../lib/format'

export function Icon({ name, size = 16 }: { name: string; size?: number }) {
  const common = {
    width: size,
    height: size,
    viewBox: '0 0 24 24',
    fill: 'none',
    stroke: 'currentColor',
    strokeWidth: 1.8,
    strokeLinecap: 'round' as const,
    strokeLinejoin: 'round' as const,
    'aria-hidden': true,
  }
  switch (name) {
    case 'radar':
      return (
        <svg {...common}>
          <circle cx="12" cy="12" r="9" />
          <circle cx="12" cy="12" r="4" />
          <path d="M12 12 19 6" />
          <path d="M12 3v2M21 12h-2M12 21v-2M3 12h2" />
        </svg>
      )
    case 'map':
      return (
        <svg {...common}>
          <path d="m3 6 6-3 6 3 6-3v15l-6 3-6-3-6 3Z" />
          <path d="M9 3v15M15 6v15" />
        </svg>
      )
    case 'chart':
      return (
        <svg {...common}>
          <path d="M4 20V4M4 20h16" />
          <path d="M8 16v-5M12 16V8M16 16v-3M20 16V6" />
        </svg>
      )
    case 'book':
      return (
        <svg {...common}>
          <path d="M4 5a2 2 0 0 1 2-2h13v18H6a2 2 0 0 0-2 2Z" />
          <path d="M4 19a2 2 0 0 1 2-2h13" />
        </svg>
      )
    case 'play':
      return (
        <svg {...common}>
          <path d="m7 4 13 8-13 8Z" />
        </svg>
      )
    case 'pause':
      return (
        <svg {...common}>
          <path d="M8 5v14M16 5v14" />
        </svg>
      )
    case 'reset':
      return (
        <svg {...common}>
          <path d="M3 12a9 9 0 1 0 3-6.7" />
          <path d="M3 4v5h5" />
        </svg>
      )
    case 'close':
      return (
        <svg {...common}>
          <path d="m6 6 12 12M18 6 6 18" />
        </svg>
      )
    case 'check':
      return (
        <svg {...common}>
          <path d="m4 12 5 5L20 6" />
        </svg>
      )
    case 'flag':
      return (
        <svg {...common}>
          <path d="M5 21V4M5 4h11l-1.5 4L16 12H5" />
        </svg>
      )
    case 'x':
      return (
        <svg {...common}>
          <path d="m6 6 12 12M18 6 6 18" />
        </svg>
      )
    case 'bolt':
      return (
        <svg {...common}>
          <path d="M13 2 4 14h6l-1 8 9-12h-6Z" />
        </svg>
      )
    case 'road':
      return (
        <svg {...common}>
          <path d="M6 21 9 3M18 21 15 3M12 5v3M12 11v3M12 17v2" />
        </svg>
      )
    case 'people':
      return (
        <svg {...common}>
          <circle cx="9" cy="8" r="3" />
          <path d="M3 21v-2a6 6 0 0 1 12 0v2" />
          <path d="M16 4.5a3 3 0 0 1 0 7M18 15a6 6 0 0 1 3 5.2V21" />
        </svg>
      )
    case 'download':
      return (
        <svg {...common}>
          <path d="M12 3v12M7 10l5 5 5-5" />
          <path d="M5 21h14" />
        </svg>
      )
    case 'print':
      return (
        <svg {...common}>
          <path d="M6 9V3h12v6M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2" />
          <path d="M6 14h12v7H6Z" />
        </svg>
      )
    case 'shield':
      return (
        <svg {...common}>
          <path d="M12 3 4 6v6c0 5 3.5 8 8 9 4.5-1 8-4 8-9V6Z" />
          <path d="m9 12 2 2 4-4" />
        </svg>
      )
    case 'pin':
      return (
        <svg {...common}>
          <path d="M12 21s7-6.2 7-12a7 7 0 1 0-14 0c0 5.8 7 12 7 12Z" />
          <circle cx="12" cy="9" r="2.5" />
        </svg>
      )
    case 'arrow':
      return (
        <svg {...common}>
          <path d="M5 12h14M13 6l6 6-6 6" />
        </svg>
      )
    case 'vote':
      return (
        <svg {...common}>
          <path d="M4 12v8h16v-8" />
          <path d="m8 10 4-6 4 6" />
          <path d="M12 4v10" />
        </svg>
      )
    case 'search':
      return (
        <svg {...common}>
          <circle cx="11" cy="11" r="7" />
          <path d="m20 20-3.5-3.5" />
        </svg>
      )
    case 'sun':
      return (
        <svg {...common}>
          <circle cx="12" cy="12" r="4" />
          <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
        </svg>
      )
    case 'moon':
      return (
        <svg {...common}>
          <path d="M20 15.5A8.5 8.5 0 0 1 8.5 4 8.5 8.5 0 1 0 20 15.5Z" />
        </svg>
      )
    case 'sliders':
      return (
        <svg {...common}>
          <path d="M4 6h8M16 6h4M4 12h3M11 12h9M4 18h10M18 18h2" />
          <circle cx="14" cy="6" r="2" /><circle cx="9" cy="12" r="2" /><circle cx="16" cy="18" r="2" />
        </svg>
      )
    case 'spark':
      return (
        <svg {...common}>
          <path d="M12 3v4M12 17v4M3 12h4M17 12h4M5.6 5.6l2.8 2.8M15.6 15.6l2.8 2.8M18.4 5.6l-2.8 2.8M8.4 15.6l-2.8 2.8" />
          <circle cx="12" cy="12" r="2.5" />
        </svg>
      )
    case 'command':
      return (
        <svg {...common}>
          <path d="M9 6a3 3 0 1 0-3 3h12a3 3 0 1 0-3-3v12a3 3 0 1 0 3-3H6a3 3 0 1 0 3 3Z" />
        </svg>
      )
    case 'table':
      return (
        <svg {...common}>
          <rect x="3" y="4" width="18" height="16" rx="2" />
          <path d="M3 10h18M9 10v10" />
        </svg>
      )
    case 'grid':
      return (
        <svg {...common}>
          <rect x="3" y="3" width="7" height="7" rx="1" /><rect x="14" y="3" width="7" height="7" rx="1" />
          <rect x="3" y="14" width="7" height="7" rx="1" /><rect x="14" y="14" width="7" height="7" rx="1" />
        </svg>
      )
    case 'github':
      return (
        <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor" aria-hidden>
          <path d="M12 .5A11.5 11.5 0 0 0 .5 12a11.5 11.5 0 0 0 7.9 10.9c.6.1.8-.2.8-.6v-2c-3.2.7-3.9-1.5-3.9-1.5-.5-1.3-1.3-1.7-1.3-1.7-1-.7.1-.7.1-.7 1.1.1 1.7 1.2 1.7 1.2 1 1.8 2.7 1.3 3.3 1 .1-.8.4-1.3.7-1.6-2.6-.3-5.3-1.3-5.3-5.8 0-1.3.5-2.3 1.2-3.2-.1-.3-.5-1.5.1-3.1 0 0 1-.3 3.3 1.2a11.4 11.4 0 0 1 6 0C17.5 4.3 18.5 4.6 18.5 4.6c.6 1.6.2 2.8.1 3.1.8.9 1.2 1.9 1.2 3.2 0 4.5-2.7 5.5-5.3 5.8.4.4.8 1.1.8 2.2v3.3c0 .4.2.7.8.6A11.5 11.5 0 0 0 23.5 12 11.5 11.5 0 0 0 12 .5Z" />
        </svg>
      )
    default:
      return null
  }
}

export function TopBar() {
  const { mode, setMode, scenario, index, selectScenario } = useApp()
  const prefs = usePrefs()
  const ui = useUi()
  const tabs = [
    { id: 'stage', label: 'nav.stage', icon: 'play' },
    { id: 'watch', label: 'nav.watch', icon: 'radar' },
    { id: 'analyst', label: 'nav.analyst', icon: 'map' },
    { id: 'dashboard', label: 'nav.pilot', icon: 'chart' },
    { id: 'method', label: 'nav.method', icon: 'book' },
  ] as const
  const allowed = allowedViews(prefs.role)
  return (
    <header className="topbar">
      <button className="brand" onClick={() => setMode('stage')} title="GeoResponse">
        <span className="brand-mark"><Icon name="radar" size={18} /></span>
        <span className="brand-text"><strong>GeoResponse</strong><small>imagery → decision</small></span>
      </button>
      <span className="mobile-location" aria-label="Current location">
        {prefs.t(`nav.${mode === 'dashboard' ? 'pilot' : mode}`)} · {scenario?.meta.title ?? ''}
      </span>

      <nav className="nav" aria-label="Primary">
        {tabs.filter((tab) => allowed.has(tab.id)).map((tab) => (
          <button key={tab.id} className={cx('nav-tab', mode === tab.id && 'active')} onClick={() => setMode(tab.id)} aria-label={prefs.t(tab.label)}>
            <Icon name={tab.icon} size={14} />
            <span>{prefs.t(tab.label)}</span>
          </button>
        ))}
        {allowed.has('booth') && (
          <button className={cx('nav-tab', mode === 'booth' && 'active')} onClick={() => setMode('booth')} aria-label={prefs.t('nav.booth')}>
            <Icon name="vote" size={14} />
            <span>{prefs.t('nav.booth')}</span>
          </button>
        )}
      </nav>

      <button className="command-trigger" onClick={ui.openPalette}>
        <Icon name="search" size={14} />
        <span>{prefs.t('action.search')}</span>
        <Kbd>⌘K</Kbd>
      </button>

      <div className="topbar-right">
        <div className="scenario-select">
          <span className="live-dot" />
          <select value={scenario?.meta.id ?? ''} onChange={(event) => selectScenario(event.target.value)} aria-label="Scenario">
            {index?.scenarios.map((entry) => <option key={entry.id} value={entry.id}>{entry.title}</option>)}
          </select>
        </div>
        <IconButton label={prefs.t('action.agent')} onClick={() => ui.openAgent()}><Icon name="spark" size={16} /></IconButton>
        <IconButton label={`${prefs.t('action.theme')}: ${prefs.theme}`} onClick={prefs.cycleTheme}>
          <Icon name={prefs.resolvedTheme === 'dark' ? 'moon' : prefs.resolvedTheme === 'light' ? 'sun' : 'sliders'} size={16} />
        </IconButton>
        <IconButton label={prefs.t('action.settings')} onClick={ui.openSettings}><Icon name="sliders" size={16} /></IconButton>
        <a className="icon-btn" href="https://github.com/jiuwendemos/georesponse" target="_blank" rel="noreferrer" title="GitHub"><Icon name="github" size={16} /></a>
      </div>
    </header>
  )
}

export function MobileNav() {
  const { mode, setMode } = useApp()
  const prefs = usePrefs()
  const ui = useUi()
  const items = [
    { id: 'stage', label: 'nav.stage', icon: 'play' },
    { id: 'watch', label: 'nav.watch', icon: 'radar' },
    { id: 'analyst', label: 'nav.analyst', icon: 'map' },
    { id: 'dashboard', label: 'nav.pilot', icon: 'chart' },
  ] as const
  return (
    <nav className="mobile-nav" aria-label="Mobile primary">
      {items.filter((item) => allowedViews(prefs.role).has(item.id)).map((item) => (
        <button key={item.id} className={cx('mobile-nav-item', mode === item.id && 'active')} onClick={() => setMode(item.id)} aria-label={prefs.t(item.label)}>
          <Icon name={item.icon} size={18} />
          <span>{prefs.t(item.label)}</span>
        </button>
      ))}
      <button className="mobile-nav-item" onClick={ui.openPalette}>
        <Icon name="command" size={18} />
        <span>{prefs.t('mobile.more')}</span>
      </button>
    </nav>
  )
}

export function Toast() {
  const { toast } = useApp()
  if (!toast) return null
  return (
    <div className={cx('toast', `toast-${toast.tone}`)} role="status">
      <span className="toast-dot" />
      {toast.message}
    </div>
  )
}

export function Modal({
  open,
  onClose,
  children,
  className,
  label,
}: {
  open: boolean
  onClose: () => void
  children: ReactNode
  className?: string
  label?: string
}) {
  const card = useRef<HTMLDivElement | null>(null)
  const previous = useRef<HTMLElement | null>(null)

  useEffect(() => {
    if (!open) return
    previous.current = document.activeElement as HTMLElement | null
    const element = card.current
    const focusable = element?.querySelector<HTMLElement>('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])')
    window.setTimeout(() => focusable?.focus(), 20)
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault()
        onClose()
        return
      }
      if (event.key !== 'Tab' || !element) return
      const items = Array.from(element.querySelectorAll<HTMLElement>('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])')).filter((item) => !item.hasAttribute('disabled'))
      if (!items.length) return
      const first = items[0]
      const last = items[items.length - 1]
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first.focus()
      }
    }
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('keydown', onKey)
      previous.current?.focus?.()
    }
  }, [open, onClose])

  if (!open) return null
  return (
    <div className="modal" role="dialog" aria-modal="true" aria-label={label ?? 'Dialog'} onClick={onClose}>
      <div ref={card} tabIndex={-1} className={cx('modal-card', className)} onClick={(event) => event.stopPropagation()}>
        <button className="modal-close" onClick={onClose} aria-label="Close">
          <Icon name="close" size={16} />
        </button>
        {children}
      </div>
    </div>
  )
}

export function SeverityChip({ severity, small }: { severity: string; small?: boolean }) {
  const label = severity === 'red' ? 'High' : severity === 'orange' ? 'Watch' : 'Monitor'
  return <span className={cx('chip', `chip-${severity}`, small && 'chip-sm')}>{label}</span>
}

export function ConfidenceBar({ value }: { value: number }) {
  return (
    <div className="confidence" title={`${Math.round(value * 100)}% confidence`}>
      <span style={{ width: `${Math.round(value * 100)}%` }} />
    </div>
  )
}
