import { Component, useEffect, useState, type ErrorInfo, type ReactNode } from 'react'
import { Button, Card } from './ds'
import { Icon } from './ui'

interface BoundaryState {
  error: Error | null
  id: string | null
}

/**
 * Route-level error boundary. Keeps the shell alive, gives the user a retry and
 * a short diagnostic id that support can match to the console.
 */
export class ErrorBoundary extends Component<{ children: ReactNode }, BoundaryState> {
  state: BoundaryState = { error: null, id: null }

  static getDerivedStateFromError(error: Error): BoundaryState {
    return { error, id: `gr-${Date.now().toString(36)}` }
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    // The console is the only sink in a static deployment; no personal data.
    console.error('GeoResponse view error', this.state.id, error, info.componentStack)
  }

  render(): ReactNode {
    if (!this.state.error) return this.props.children
    return (
      <div className="page-state resilience-state" role="alert">
        <Card eyebrow="Recoverable" title="This view could not render">
          <p>{this.state.error.message || 'An unexpected error interrupted the view.'}</p>
          <p className="card-note">Diagnostic id <code>{this.state.id}</code>. The rest of the app is still available.</p>
          <div className="component-row">
            <Button variant="primary" onClick={() => this.setState({ error: null, id: null })}>Retry</Button>
            <Button variant="ghost" onClick={() => window.location.reload()}>Reload</Button>
          </div>
        </Card>
      </div>
    )
  }
}

/** Offline/online banner. The cached shell and pack keep working offline. */
export function OfflineBanner() {
  const [online, setOnline] = useState(() => (typeof navigator === 'undefined' ? true : navigator.onLine))
  const [dismissed, setDismissed] = useState(false)

  useEffect(() => {
    const up = () => { setOnline(true); setDismissed(false) }
    const down = () => { setOnline(false); setDismissed(false) }
    window.addEventListener('online', up)
    window.addEventListener('offline', down)
    return () => {
      window.removeEventListener('online', up)
      window.removeEventListener('offline', down)
    }
  }, [])

  if (online || dismissed) return null
  return (
    <div className="offline-banner" role="status" aria-live="polite">
      <Icon name="download" size={14} />
      <span><b>Offline.</b> Cached imagery and the last pack are still available. Live agent and integrations will retry when the connection returns.</span>
      <Button size="sm" variant="ghost" onClick={() => setDismissed(true)} aria-label="Dismiss offline notice">Dismiss</Button>
    </div>
  )
}
