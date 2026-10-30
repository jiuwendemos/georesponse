import { useUi } from '../ui-context'
import { usePrefs } from '../prefs'
import { Modal, Icon } from './ui'
import { Button, Field, Segmented, TextInput } from './ds'

export default function SettingsPanel() {
  const ui = useUi()
  const prefs = usePrefs()

  return (
    <Modal open={ui.settingsOpen} onClose={ui.closeSettings} className="settings-modal" label="Settings">
      <div className="eyebrow"><span className="dot" /> Preferences</div>
      <h2>Make the product yours.</h2>
      <p className="audit-sub">Stored locally. Density changes space, never the minimum legible type size.</p>

      <div className="settings-modal-grid">
        <Field label="Theme" hint="System follows your OS. Contrast is for bright rooms and low vision.">
          <Segmented value={prefs.theme} label="Theme" onChange={prefs.setTheme} options={[{ value: 'system', label: 'System' }, { value: 'light', label: 'Light' }, { value: 'dark', label: 'Dark' }, { value: 'contrast', label: 'Contrast' }]} />
        </Field>
        <Field label="Density">
          <Segmented value={prefs.density} label="Density" onChange={prefs.setDensity} options={[{ value: 'comfortable', label: 'Comfortable' }, { value: 'compact', label: 'Compact' }]} />
        </Field>
        <Field label="Motion">
          <Segmented value={prefs.motion ? 'on' : 'off'} label="Motion" onChange={(value) => prefs.setMotion(value === 'on')} options={[{ value: 'on', label: 'On' }, { value: 'off', label: 'Reduced' }]} />
        </Field>
        <Field label="Language">
          <Segmented value={prefs.language} label="Language" onChange={prefs.setLanguage} options={[{ value: 'en', label: 'English' }, { value: 'de', label: 'Deutsch' }]} />
        </Field>
        <Field label="Profile name" hint="Demo only; no account is created.">
          <TextInput defaultValue="A. Weber" />
        </Field>
        <Field label="Email digest" hint="Instant for red alerts; digest for the rest.">
          <TextInput defaultValue="ops@example.com" />
        </Field>
      </div>

      <div className="settings-modal-actions">
        <Button variant="primary" onClick={() => { ui.openStyleGuide(); ui.closeSettings() }}>
          <Icon name="grid" size={14} /> Open design system
        </Button>
        <Button variant="ghost" onClick={ui.closeSettings}>Close</Button>
      </div>
      <p className="card-note">Keyboard: <b>⌘K</b> palette · <b>Tab</b> through every control · <b>Esc</b> closes. No preference leaves this browser.</p>
    </Modal>
  )
}
