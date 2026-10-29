import type { ReactNode } from 'react'
import { useApp } from '../store'
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
  const tabs = [
    { id: 'stage', label: 'Stage', icon: 'play' },
    { id: 'watch', label: 'Watch', icon: 'radar' },
    { id: 'analyst', label: 'Analyst', icon: 'map' },
    { id: 'dashboard', label: 'Pilot', icon: 'chart' },
    { id: 'method', label: 'Method', icon: 'book' },
  ] as const
  return (
    <header className="topbar">
      <button className="brand" onClick={() => setMode('stage')} title="GeoResponse">
        <span className="brand-mark">
          <Icon name="radar" size={18} />
        </span>
        <span className="brand-text">
          <strong>GeoResponse</strong>
          <small>imagery → decision</small>
        </span>
      </button>

      <nav className="nav" aria-label="Primary">
        {tabs.map((tab) => (
          <button key={tab.id} className={cx('nav-tab', mode === tab.id && 'active')} onClick={() => setMode(tab.id)}>
            <Icon name={tab.icon} size={14} />
            <span>{tab.label}</span>
          </button>
        ))}
        <button className={cx('nav-tab', mode === 'booth' && 'active')} onClick={() => setMode('booth')}>
          <Icon name="vote" size={14} />
          <span>Booth</span>
        </button>
      </nav>

      <div className="topbar-right">
        <div className="scenario-select">
          <span className="live-dot" />
          <select
            value={scenario?.meta.id ?? ''}
            onChange={(event) => selectScenario(event.target.value)}
            aria-label="Scenario"
          >
            {index?.scenarios.map((entry) => (
              <option key={entry.id} value={entry.id}>
                {entry.title}
              </option>
            ))}
          </select>
        </div>
        <a className="icon-btn" href="https://github.com/jiuwendemos/georesponse" target="_blank" rel="noreferrer" title="GitHub">
          <Icon name="github" size={16} />
        </a>
      </div>
    </header>
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
  if (!open) return null
  return (
    <div className="modal" role="dialog" aria-modal="true" aria-label={label ?? 'Dialog'} onClick={onClose}>
      <div className={cx('modal-card', className)} onClick={(event) => event.stopPropagation()}>
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
