import { useUi } from '../ui-context'
import { usePrefs } from '../prefs'
import { useApp } from '../store'
import { Modal, Icon } from './ui'
import { Button, Field, Segmented, TextInput } from './ds'

export default function SettingsPanel() {
  const ui = useUi()
  const prefs = usePrefs()
  const app = useApp()
  const t = prefs.t

  return (
    <Modal open={ui.settingsOpen} onClose={ui.closeSettings} className="settings-modal" label={t('settings.title')}>
      <div className="eyebrow"><span className="dot" /> {t('settings.eyebrow')}</div>
      <h2>{t('settings.heading')}</h2>
      <p className="audit-sub">{t('settings.sub')}</p>

      <div className="settings-modal-grid">
        <Field label={t('settings.theme')} hint={t('settings.themeHint')}>
          <Segmented
            value={prefs.theme}
            label={t('settings.theme')}
            onChange={prefs.setTheme}
            options={[
              { value: 'system', label: t('theme.system') },
              { value: 'light', label: t('theme.light') },
              { value: 'dark', label: t('theme.dark') },
              { value: 'contrast', label: t('theme.contrast') },
            ]}
          />
        </Field>
        <Field label={t('settings.density')}>
          <Segmented
            value={prefs.density}
            label={t('settings.density')}
            onChange={prefs.setDensity}
            options={[
              { value: 'comfortable', label: t('density.comfortable') },
              { value: 'compact', label: t('density.compact') },
            ]}
          />
        </Field>
        <Field label={t('settings.motion')}>
          <Segmented
            value={prefs.motion ? 'on' : 'off'}
            label={t('settings.motion')}
            onChange={(value) => prefs.setMotion(value === 'on')}
            options={[
              { value: 'on', label: t('settings.motion.on') },
              { value: 'off', label: t('settings.motion.off') },
            ]}
          />
        </Field>
        <Field label={t('settings.language')}>
          <Segmented
            value={prefs.language}
            label={t('settings.language')}
            onChange={prefs.setLanguage}
            options={[
              { value: 'en', label: 'English' },
              { value: 'de', label: 'Deutsch' },
            ]}
          />
        </Field>
        <Field label={t('settings.dataMode')} hint={t('settings.dataModeHint')}>
          <Segmented
            value={prefs.dataMode}
            label={t('settings.dataMode')}
            onChange={(value) => {
              prefs.setDataMode(value)
              app.setMode(value === 'workspace' ? 'workspace' : 'stage')
            }}
            options={[
              { value: 'demo', label: t('dataMode.demo') },
              { value: 'workspace', label: t('dataMode.workspace') },
            ]}
          />
        </Field>
        <Field label={t('settings.role')} hint={t('settings.roleHint')}>
          <Segmented
            value={prefs.role}
            label={t('settings.role')}
            onChange={prefs.setRole}
            options={[
              { value: 'all', label: t('role.all') },
              { value: 'presenter', label: t('role.presenter') },
              { value: 'analyst', label: t('role.analyst') },
              { value: 'watch', label: t('role.watch') },
              { value: 'claims', label: t('role.claims') },
              { value: 'field', label: t('role.field') },
              { value: 'admin', label: t('role.admin') },
            ]}
          />
        </Field>
        <Field label={t('settings.profile')} hint={t('settings.profileHint')}>
          <TextInput defaultValue="A. Weber" />
        </Field>
        <Field label={t('settings.email')} hint={t('settings.emailHint')}>
          <TextInput defaultValue="ops@example.com" />
        </Field>
      </div>

      <div className="settings-modal-actions">
        <Button variant="primary" onClick={() => { ui.openStyleGuide(); ui.closeSettings() }}>
          <Icon name="grid" size={14} /> {t('settings.openDesign')}
        </Button>
        <Button variant="ghost" onClick={ui.closeSettings}>{t('settings.close')}</Button>
      </div>
      <p className="card-note">
        {t('settings.note')}{' '}
        <a href="https://github.com/jiuwendemos/georesponse/blob/main/docs/ACCESSIBILITY.md" target="_blank" rel="noreferrer">
          Accessibility statement &amp; feedback
        </a>
        .
      </p>
    </Modal>
  )
}
