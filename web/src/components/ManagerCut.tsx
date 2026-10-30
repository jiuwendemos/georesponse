import { useCallback, useEffect, useState } from 'react'
import { useApp } from '../store'
import { useUi } from '../ui-context'
import { Button, IconButton } from './ds'
import { Icon } from './ui'

interface CutStep {
  title: string
  body: string
  run: () => void
}

export default function ManagerCut() {
  const app = useApp()
  const ui = useUi()
  const [index, setIndex] = useState(0)

  const steps: CutStep[] = [
    {
      title: 'The event',
      body: 'Reset to 12:00. The flood edge is not at the care campus yet. Point at the clock; the question is where the three teams go.',
      run: () => { app.reset(); app.setMode('stage') },
    },
    {
      title: 'The decision',
      body: 'Scrub to 18:00. The #1 site flips. Open it and read the one-sentence reason before any map detail.',
      run: () => {
        app.setMode('stage')
        const top = app.ranked[0]?.site
        if (top) app.selectSite(top.id)
      },
    },
    {
      title: 'The human correction',
      body: 'Open the false positive. The model is confident; the analyst is right. Reject it and watch the rank change.',
      run: () => {
        app.setMode('stage')
        const fp = app.scenario?.falsePositive?.siteId
        if (fp) app.selectSite(fp)
      },
    },
    {
      title: 'The room decides',
      body: 'Open the audience choice. The room moves a team; coverage and response time change in the same scene.',
      run: () => { app.setMode('stage'); app.setPhase(4) },
    },
    {
      title: 'The consequence',
      body: 'Print the field order. It must match the screen: site, team, access, evidence and the human signature.',
      run: () => app.openFieldOrder(true),
    },
    {
      title: 'The recurring product',
      body: 'Switch to Watch. Show scopes, coverage, SLA, and “what changed since you last looked”. This is the subscription, not the event.',
      run: () => app.setMode('watch'),
    },
    {
      title: 'The proof',
      body: 'Open the manager proof. One page: time, sites, teams, the false positive and analyst hours saved. Label the estimates.',
      run: () => { app.setMode('dashboard'); ui.openProof() },
    },
  ]

  const go = useCallback((next: number) => {
    const bounded = Math.max(0, Math.min(steps.length - 1, next))
    setIndex(bounded)
    steps[bounded].run()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [app, ui])

  useEffect(() => {
    if (ui.cutOpen) {
      setIndex(0)
      steps[0].run()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ui.cutOpen])

  if (!ui.cutOpen) return null
  const step = steps[index]
  const last = index === steps.length - 1

  return (
    <aside className="cut-rail" role="region" aria-label="Manager demo">
      <div className="cut-rail-head">
        <span className="eyebrow"><span className="dot" /> Manager cut · {index + 1}/{steps.length}</span>
        <IconButton label="Exit manager demo" onClick={ui.closeCut}><Icon name="close" size={14} /></IconButton>
      </div>
      <b>{step.title}</b>
      <p>{step.body}</p>
      <div className="cut-rail-actions">
        <Button size="sm" variant="ghost" onClick={() => go(index - 1)} disabled={index === 0}>Back</Button>
        {last ? (
          <Button size="sm" variant="primary" onClick={ui.closeCut}>Finish</Button>
        ) : (
          <Button size="sm" variant="primary" onClick={() => go(index + 1)}>Next <Icon name="arrow" size={12} /></Button>
        )}
      </div>
      {index === 0 && <small className="cut-rail-note">Reset is under five seconds and works offline.</small>}
    </aside>
  )
}
