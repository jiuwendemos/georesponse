import { useEffect, useState } from 'react'
import { useApp } from '../store'
import { useUi } from '../ui-context'
import { dataPath, loadJson } from '../lib/data'
import type { PilotData } from '../types'
import { Button, Card } from './ds'
import { Icon, Modal } from './ui'

export default function ManagerProof() {
  const app = useApp()
  const ui = useUi()
  const [pilot, setPilot] = useState<PilotData | null>(null)

  useEffect(() => {
    if (!ui.proofOpen) return
    loadJson<PilotData>(dataPath('pilot.json')).then(setPilot).catch(() => undefined)
  }, [ui.proofOpen])

  const summary = pilot?.summary
  const sites = app.scenario?.sites.length ?? 18
  const teams = app.scenario?.meta.teams ?? 3
  const minutes = summary?.avgAssessmentMinutes ?? 42
  const baseline = summary?.baselineMinutes ?? 2880
  const falsePositives = summary?.falsePositives ?? 1
  const hours = summary?.analystHoursSaved ?? 6.5

  return (
    <Modal open={ui.proofOpen} onClose={ui.closeProof} className="proof-card" label="Manager proof">
      <div className="eyebrow"><span className="dot" /> Manager proof · one page</div>
      <h2>{minutes} minutes, {teams} teams, one signed assessment.</h2>
      <p className="audit-sub">
        The room sees a decision, the evidence behind it, a human correction and a visible consequence.
        Numbers are pilot-design estimates until the first customer baseline replaces them.
      </p>

      <div className="proof-metrics">
        <div><span>Decision time</span><b>{minutes} min</b><em>vs {Math.round(baseline / 60)} h manual baseline</em></div>
        <div><span>Sites ranked</span><b>{sites}</b><em>{teams} teams, one plan</em></div>
        <div><span>False positives</span><b>{falsePositives}</b><em>caught by a human</em></div>
        <div><span>Analyst hours</span><b>{hours} h</b><em>saved per event</em></div>
        <div><span>Precision</span><b>{summary ? `${Math.round(summary.precision * 100)}%` : '—'}</b><em>confirmed / closed</em></div>
        <div><span>Recall</span><b>{summary ? `${Math.round(summary.recall * 100)}%` : '—'}</b><em>on the pilot set</em></div>
      </div>

      <Card eyebrow="What changed" title="The loop is the product">
        <ol className="pattern-list">
          <li><b>Sense</b><span>Sentinel-2 before/after, time-stamped and attributed.</span></li>
          <li><b>Rank</b><span>Access, people, value and confidence produce one order.</span></li>
          <li><b>Correct</b><span>The analyst rejects the confident false positive and the rank changes.</span></li>
          <li><b>Decide</b><span>The room moves one team; coverage and response time change on screen.</span></li>
          <li><b>Hand off</b><span>A printable field order carries the evidence and the signature.</span></li>
          <li><b>Recur</b><span>Watch keeps scopes, cadence, SLA and “what changed” after the event.</span></li>
        </ol>
      </Card>

      <p className="card-note">
        {pilot?.disclaimer ?? 'Pilot-design estimates. Replace with measured baseline after the first pilot.'}
      </p>

      <div className="modal-actions">
        <Button variant="primary" onClick={() => window.print()}><Icon name="print" size={14} /> Print this page</Button>
        <Button variant="ghost" onClick={ui.closeProof}>Close</Button>
      </div>
    </Modal>
  )
}
