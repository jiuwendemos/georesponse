import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react'

interface UiContextValue {
  paletteOpen: boolean
  agentOpen: boolean
  styleGuideOpen: boolean
  settingsOpen: boolean
  openPalette: () => void
  closePalette: () => void
  openAgent: (seed?: string) => void
  closeAgent: () => void
  openStyleGuide: () => void
  closeStyleGuide: () => void
  openSettings: () => void
  closeSettings: () => void
  agentSeed: string
}

const UiContext = createContext<UiContextValue | null>(null)

export function UiProvider({ children }: { children: ReactNode }) {
  const [paletteOpen, setPaletteOpen] = useState(false)
  const [agentOpen, setAgentOpen] = useState(false)
  const [agentSeed, setAgentSeed] = useState('')
  const [styleGuideOpen, setStyleGuideOpen] = useState(false)
  const [settingsOpen, setSettingsOpen] = useState(false)

  const openAgent = useCallback((seed = '') => {
    setAgentSeed(seed)
    setAgentOpen(true)
  }, [])

  const value = useMemo<UiContextValue>(
    () => ({
      paletteOpen,
      agentOpen,
      styleGuideOpen,
      settingsOpen,
      openPalette: () => setPaletteOpen(true),
      closePalette: () => setPaletteOpen(false),
      openAgent,
      closeAgent: () => setAgentOpen(false),
      openStyleGuide: () => setStyleGuideOpen(true),
      closeStyleGuide: () => setStyleGuideOpen(false),
      openSettings: () => setSettingsOpen(true),
      closeSettings: () => setSettingsOpen(false),
      agentSeed,
    }),
    [paletteOpen, agentOpen, styleGuideOpen, settingsOpen, agentSeed, openAgent],
  )

  return <UiContext.Provider value={value}>{children}</UiContext.Provider>
}

export function useUi(): UiContextValue {
  const value = useContext(UiContext)
  if (!value) throw new Error('useUi must be used inside UiProvider')
  return value
}
