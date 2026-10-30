import { useEffect, useState } from 'react'
import { useUi } from '../ui-context'
import { Button, Kbd } from './ds'
import { Icon } from './ui'

const STEPS = [
  {
    icon: 'map',
    title: 'The map is the workspace',
    body: 'The stage is map-first. Drag to pan, scroll or use +/− to zoom, and open the table button for a keyboard-friendly list of every site.',
  },
  {
    icon: 'command',
    title: 'Everything is one keystroke away',
    body: 'Press Ctrl or ⌘ + K to jump to any view, alert, scenario or saved view. The same palette saves your current view.',
  },
  {
    icon: 'spark',
    title: 'The agent proposes, you decide',
    body: 'Ask for a briefing or a next action. Tool calls are shown, writes are proposals, and every proposal needs your approval.',
  },
  {
    icon: 'radar',
    title: 'Watch is the proactive inbox',
    body: 'Scopes are sensed on a schedule. Watch shows coverage, blind spots, SLA clocks and the alerts that need a human.',
  },
] as const

export default function Onboarding() {
  const ui = useUi()
  const [step, setStep] = useState(0)

  useEffect(() => {
    if (ui.tourOpen) setStep(0)
  }, [ui.tourOpen])

  const finish = () => ui.closeTour()

  if (!ui.tourOpen) return null
  const current = STEPS[step]
  const last = step === STEPS.length - 1

  return (
    <div className="onboarding" role="dialog" aria-modal="true" aria-label="Welcome to GeoResponse">
      <div className="onboarding-card">
        <div className="onboarding-progress" aria-hidden>
          {STEPS.map((item, index) => (
            <span key={item.title} className={index <= step ? 'done' : ''} />
          ))}
        </div>
        <div className="onboarding-icon"><Icon name={current.icon} size={22} /></div>
        <span className="eyebrow">Step {step + 1} of {STEPS.length}</span>
        <h2>{current.title}</h2>
        <p>{current.body}</p>
        <div className="onboarding-actions">
          <Button variant="ghost" onClick={finish}>Skip</Button>
          <div className="onboarding-next">
            {step > 0 && <Button onClick={() => setStep((value) => value - 1)}>Back</Button>}
            <Button variant="primary" onClick={() => (last ? finish() : setStep((value) => value + 1))}>
              {last ? 'Start' : 'Next'}
            </Button>
          </div>
        </div>
        <p className="card-note">You can reopen this from <Kbd>Ctrl/⌘ K</Kbd> → “Show welcome tour”.</p>
      </div>
    </div>
  )
}
