import { useState } from 'react'
import { useUi } from '../ui-context'
import { usePrefs } from '../prefs'
import { Modal, Icon } from './ui'
import { Badge, Button, Card, EmptyState, Field, Segmented, TextInput, Kbd } from './ds'

const TABS = ['Foundations', 'Components', 'Patterns'] as const

const SWATCHES = [
  ['Canvas', '--bg'],
  ['Surface', '--panel'],
  ['Ink', '--ink'],
  ['Muted', '--muted'],
  ['Accent', '--cyan'],
  ['High risk', '--red'],
  ['Watch', '--amber'],
  ['Assigned', '--green'],
]

export default function StyleGuide() {
  const ui = useUi()
  const prefs = usePrefs()
  const [tab, setTab] = useState<(typeof TABS)[number]>('Foundations')
  const [email, setEmail] = useState('')
  const [notes, setNotes] = useState('')

  return (
    <Modal open={ui.styleGuideOpen} onClose={ui.closeStyleGuide} className="styleguide-card" label="Design system">
      <div className="eyebrow"><span className="dot" /> Living design system · 2026</div>
      <h2>One language, every surface.</h2>
      <p className="audit-sub">Tokens, themes, type and components are rendered from the running product. This page is the contract.</p>

      <div className="styleguide-theme-row">
        <div><span>Theme</span><Segmented value={prefs.theme} label="Theme" onChange={prefs.setTheme} options={[{ value: 'system', label: 'System' }, { value: 'light', label: 'Light' }, { value: 'dark', label: 'Dark' }, { value: 'contrast', label: 'Contrast' }]} /></div>
        <div><span>Density</span><Segmented value={prefs.density} label="Density" onChange={prefs.setDensity} options={[{ value: 'comfortable', label: 'Comfortable' }, { value: 'compact', label: 'Compact' }]} /></div>
        <div><span>Language</span><Segmented value={prefs.language} label="Language" onChange={prefs.setLanguage} options={[{ value: 'en', label: 'English' }, { value: 'de', label: 'Deutsch' }]} /></div>
        <div><span>Motion</span><Segmented value={prefs.motion ? 'on' : 'off'} label="Motion" onChange={(value) => prefs.setMotion(value === 'on')} options={[{ value: 'on', label: 'On' }, { value: 'off', label: 'Reduced' }]} /></div>
      </div>

      <div className="styleguide-tabs" role="tablist" aria-label="Design system sections">
        {TABS.map((item) => (
          <button key={item} role="tab" aria-selected={tab === item} className={`filter-chip ${tab === item ? 'active' : ''}`} onClick={() => setTab(item)}>{item}</button>
        ))}
      </div>

      {tab === 'Foundations' && (
        <div className="styleguide-grid">
          <Card eyebrow="Colour" title="Semantic tokens">
            <div className="swatch-grid">
              {SWATCHES.map(([label, token]) => (
                <div className="swatch-card" key={token}>
                  <span className="swatch-large" style={{ background: `var(${token})` }} />
                  <b>{label}</b>
                  <small>{token}</small>
                </div>
              ))}
            </div>
            <p className="card-note">One accent. Red, amber and green are meaning, not decoration.</p>
          </Card>
          <Card eyebrow="Type" title="Scale & numerals">
            <div className="type-scale">
              <div><span>Display</span><b className="type-display">Decide faster.</b></div>
              <div><span>Heading</span><b className="type-heading">Portfolio watch</b></div>
              <div><span>Body</span><p>Body copy is 14–15 px with 1.5 line height. Numbers use tabular figures for scanning.</p></div>
              <div><span>Label</span><b className="type-label">HIGH RISK · 91%</b></div>
              <div><span>Mono</span><code>ALT-1001 · €6.2m · 50.5480</code></div>
            </div>
          </Card>
          <Card eyebrow="Space" title="4-point grid">
            <div className="space-scale">
              {[4, 8, 12, 16, 24, 32, 48].map((size) => (
                <div key={size}><span style={{ width: size * 3 }} /><b>{size}</b></div>
              ))}
            </div>
            <p className="card-note">Density changes space, never the minimum legible type size.</p>
          </Card>
          <Card eyebrow="Motion" title="Purposeful, interruptible">
            <div className="motion-demo"><span className="motion-bar" /></div>
            <p className="card-note">Fast 120 ms, normal 220 ms, slow 360 ms. Reduced motion removes all non-essential movement. <Kbd>prefers-reduced-motion</Kbd> respected.</p>
          </Card>
        </div>
      )}

      {tab === 'Components' && (
        <div className="styleguide-grid">
          <Card eyebrow="Buttons" title="One hierarchy">
            <div className="component-row">
              <Button variant="primary">Primary</Button>
              <Button>Secondary</Button>
              <Button variant="ghost">Ghost</Button>
              <Button variant="danger">Destructive</Button>
              <Button loading>Loading</Button>
            </div>
            <div className="component-row">
              <Button size="sm">Small</Button><Button size="md">Medium</Button><Button size="lg">Large</Button>
            </div>
            <div className="component-row"><Badge>Neutral</Badge><Badge tone="info">Info</Badge><Badge tone="success">Passed</Badge><Badge tone="warn">Watch</Badge><Badge tone="danger">High risk</Badge></div>
          </Card>
          <Card eyebrow="Fields" title="Labels, help and errors">
            <Field label="Recipient" hint="Only this person receives the alert." id="sg-email"><TextInput id="sg-email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="ops@example.com" /></Field>
            <Field label="Note" error="A dismissal needs a visible reason." id="sg-note"><TextInput id="sg-note" value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Roof edge intact; water reflection." /></Field>
            <div className="component-row"><Button>Save</Button><Button variant="ghost">Cancel</Button></div>
          </Card>
          <Card eyebrow="States" title="Never leave the user at a dead end">
            <EmptyState icon={<Icon name="radar" size={22} />} title="No alerts in this filter" body="Try “all”, or draw a new scope to start watching." action={<Button size="sm">Draw scope</Button>} />
            <div className="state-row"><span className="state-dot online" /> healthy <span className="state-dot degraded" /> degraded <span className="state-dot blind" /> blind spot</div>
          </Card>
          <Card eyebrow="Keyboard" title="Everything reachable">
            <div className="shortcut-list">
              <span><Kbd>⌘K</Kbd> command palette</span>
              <span><Kbd>G</Kbd> then <Kbd>W</Kbd> go to Watch</span>
              <span><Kbd>R</Kbd> reset stage</span>
              <span><Kbd>Space</Kbd> play timeline</span>
              <span><Kbd>Esc</Kbd> close a surface</span>
            </div>
          </Card>
        </div>
      )}

      {tab === 'Patterns' && (
        <div className="styleguide-grid">
          <Card eyebrow="Decision" title="Summary → evidence → action">
            <ol className="pattern-list">
              <li><b>Summary</b><span>One sentence: what changed, where, why it matters.</span></li>
              <li><b>Evidence</b><span>Before/after, confidence, provenance and the baseline.</span></li>
              <li><b>Action</b><span>Approve, assign, hand off or dismiss with a reason.</span></li>
            </ol>
          </Card>
          <Card eyebrow="AI" title="Preview, approve, undo">
            <p>Every agent write is a proposal: what will change, for whom, and how to reverse it. No hidden tool calls, no auto-approval.</p>
            <div className="agent-action" style={{ marginTop: 8 }}>
              <div><span>Action preview</span><b>Assign Team 2 to Bad Neuenahr</b><small>Requires your approval. Reversible.</small></div>
              <Button size="sm" variant="primary">Apply</Button>
            </div>
          </Card>
          <Card eyebrow="Trust" title="Human signature">
            <p>Assessments always show the analyst, model version, imagery source and limitations. Confidence is not truth.</p>
            <div className="trust-strip"><Badge tone="info">grounded</Badge><span>local tools</span><Badge tone="success">human review</Badge></div>
          </Card>
          <Card eyebrow="Errors" title="Say what to do next">
            <p><b>The map could not load the 14:32 pack.</b> The cached pack is still available. Retry, or open the offline pack.</p>
            <div className="component-row"><Button size="sm">Retry</Button><Button size="sm" variant="ghost">Open offline pack</Button></div>
          </Card>
        </div>
      )}
    </Modal>
  )
}
