import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'

export type ThemePref = 'system' | 'light' | 'dark' | 'contrast'
export type Density = 'comfortable' | 'compact'
export type Language = 'en' | 'de'

interface PrefsState {
  theme: ThemePref
  density: Density
  motion: boolean
  language: Language
}

interface PrefsContextValue extends PrefsState {
  resolvedTheme: 'light' | 'dark' | 'contrast'
  setTheme: (theme: ThemePref) => void
  cycleTheme: () => void
  setDensity: (density: Density) => void
  setMotion: (motion: boolean) => void
  setLanguage: (language: Language) => void
  t: (key: string) => string
}

const KEY = 'georesponse.prefs.v2'

const DEFAULTS: PrefsState = {
  theme: 'system',
  density: 'comfortable',
  motion: true,
  language: 'en',
}

const DICT: Record<Language, Record<string, string>> = {
  en: {
    'nav.stage': 'Stage',
    'nav.watch': 'Watch',
    'nav.analyst': 'Analyst',
    'nav.pilot': 'Pilot',
    'nav.method': 'Method',
    'nav.booth': 'Booth',
    'action.search': 'Search or jump',
    'action.agent': 'Ask',
    'action.theme': 'Theme',
    'action.language': 'Language',
    'theme.system': 'System',
    'theme.light': 'Light',
    'theme.dark': 'Dark',
    'theme.contrast': 'High contrast',
    'density.comfortable': 'Comfortable',
    'density.compact': 'Compact',
    'watch.inbox': 'Inbox',
    'watch.scopes': 'Scopes',
    'watch.coverage': 'Coverage',
    'watch.digest': 'Digest',
    'watch.settings': 'Settings',
  },
  de: {
    'nav.stage': 'Bühne',
    'nav.watch': 'Überwachung',
    'nav.analyst': 'Analyse',
    'nav.pilot': 'Pilot',
    'nav.method': 'Methode',
    'nav.booth': 'Stand',
    'action.search': 'Suchen oder springen',
    'action.agent': 'Fragen',
    'action.theme': 'Design',
    'action.language': 'Sprache',
    'theme.system': 'System',
    'theme.light': 'Hell',
    'theme.dark': 'Dunkel',
    'theme.contrast': 'Hoher Kontrast',
    'density.comfortable': 'Komfortabel',
    'density.compact': 'Kompakt',
    'watch.inbox': 'Posteingang',
    'watch.scopes': 'Bereiche',
    'watch.coverage': 'Abdeckung',
    'watch.digest': 'Übersicht',
    'watch.settings': 'Einstellungen',
  },
}

function loadPrefs(): PrefsState {
  try {
    const parsed = JSON.parse(localStorage.getItem(KEY) ?? '{}') as Partial<PrefsState>
    return {
      theme: parsed.theme === 'light' || parsed.theme === 'dark' || parsed.theme === 'contrast' ? parsed.theme : 'system',
      density: parsed.density === 'compact' ? 'compact' : 'comfortable',
      motion: parsed.motion !== false,
      language: parsed.language === 'de' ? 'de' : 'en',
    }
  } catch {
    return DEFAULTS
  }
}

function systemTheme(): 'light' | 'dark' {
  if (typeof window === 'undefined') return 'dark'
  return window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark'
}

const PrefsContext = createContext<PrefsContextValue | null>(null)

export function PrefsProvider({ children }: { children: ReactNode }) {
  const [prefs, setPrefs] = useState<PrefsState>(loadPrefs)
  const [system, setSystem] = useState<'light' | 'dark'>(systemTheme)

  useEffect(() => {
    const media = window.matchMedia('(prefers-color-scheme: light)')
    const listener = () => setSystem(media.matches ? 'light' : 'dark')
    media.addEventListener?.('change', listener)
    return () => media.removeEventListener?.('change', listener)
  }, [])

  const resolvedTheme = prefs.theme === 'system' ? system : prefs.theme

  useEffect(() => {
    const root = document.documentElement
    root.dataset.theme = resolvedTheme
    root.dataset.density = prefs.density
    root.dataset.motion = prefs.motion ? 'on' : 'off'
    root.dataset.language = prefs.language
    root.style.colorScheme = resolvedTheme === 'light' ? 'light' : 'dark'
    try {
      localStorage.setItem(KEY, JSON.stringify(prefs))
    } catch {
      // private mode
    }
  }, [prefs, resolvedTheme])

  const value = useMemo<PrefsContextValue>(
    () => ({
      ...prefs,
      resolvedTheme,
      setTheme: (theme) => setPrefs((current) => ({ ...current, theme })),
      cycleTheme: () =>
        setPrefs((current) => ({
          ...current,
          theme: current.theme === 'system' ? 'light' : current.theme === 'light' ? 'dark' : current.theme === 'dark' ? 'contrast' : 'system',
        })),
      setDensity: (density) => setPrefs((current) => ({ ...current, density })),
      setMotion: (motion) => setPrefs((current) => ({ ...current, motion })),
      setLanguage: (language) => setPrefs((current) => ({ ...current, language })),
      t: (key) => DICT[prefs.language][key] ?? DICT.en[key] ?? key,
    }),
    [prefs, resolvedTheme],
  )

  return <PrefsContext.Provider value={value}>{children}</PrefsContext.Provider>
}

export function usePrefs(): PrefsContextValue {
  const value = useContext(PrefsContext)
  if (!value) throw new Error('usePrefs must be used inside PrefsProvider')
  return value
}
