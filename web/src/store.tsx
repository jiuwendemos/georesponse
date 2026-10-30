import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react'
import type { AuditEvent, Mode, ReviewStatus, Scenario, ScenarioIndex } from './types'
import { loadJson, dataPath, scenarioPath } from './lib/data'
import { rankSites, type RankedSite } from './lib/ranking'
import { appendAudit, readAudit } from './lib/audit'

export type TeamMap = Record<string, string> // siteId -> team

interface LayerState {
  flood: boolean
  roads: boolean
  power: boolean
  buildings: boolean
  landuse: boolean
}

interface Toast {
  id: number
  message: string
  tone: 'info' | 'warn' | 'success'
}

interface WorkState {
  reviews: Record<string, ReviewStatus>
  notes: Record<string, string>
  assignments: TeamMap
  vote: 'a' | 'b' | null
}

interface AppContextValue {
  mode: Mode
  setMode: (mode: Mode) => void
  index: ScenarioIndex | null
  scenario: Scenario | null
  loading: boolean
  error: string | null
  time: number
  setTime: React.Dispatch<React.SetStateAction<number>>
  selectedId: string | null
  selectSite: (id: string | null) => void
  previewId: string | null
  previewSite: (id: string | null) => void
  reviews: Record<string, ReviewStatus>
  notes: Record<string, string>
  assignments: TeamMap
  vote: 'a' | 'b' | null
  phase: number
  setPhase: (phase: number) => void
  layers: LayerState
  toggleLayer: (key: keyof LayerState) => void
  audit: AuditEvent[]
  toast: Toast | null
  notify: (message: string, tone?: Toast['tone']) => void
  ranked: RankedSite[]
  activeSites: RankedSite[]
  teamsAssigned: number
  workCount: number
  reportOpen: boolean
  fieldOrderOpen: boolean
  provenanceOpen: boolean
  openReport: (open: boolean) => void
  openFieldOrder: (open: boolean) => void
  openProvenance: (open: boolean) => void
  fitSignal: number
  reveal: () => void
  selectScenario: (id: string) => void
  review: (siteId: string, status: ReviewStatus, reason?: string) => void
  setNote: (siteId: string, note: string) => void
  batchApprove: (threshold: number) => void
  assign: (siteId: string, team: string) => void
  unassign: (siteId: string) => void
  autoAssign: () => void
  voteAudience: (choice: 'a' | 'b') => void
  reset: () => void
  watchTarget: { alertId?: string; scopeId?: string } | null
  openWatchAlert: (alertId: string) => void
  openWatchScope: (scopeId: string) => void
  clearWatchTarget: () => void
  mapRef: React.MutableRefObject<any>
  registerMap: (map: any) => void
  captureMap: () => Promise<string | null>
  saveOffline: () => Promise<void>
}

const AppContext = createContext<AppContextValue | null>(null)

const emptyWork: WorkState = { reviews: {}, notes: {}, assignments: {}, vote: null }

function readWork(id: string): WorkState {
  try {
    const raw = localStorage.getItem(`georesponse.work.${id}`)
    if (!raw) return { ...emptyWork }
    const parsed = JSON.parse(raw) as WorkState
    return {
      reviews: parsed.reviews ?? {},
      notes: parsed.notes ?? {},
      assignments: parsed.assignments ?? {},
      vote: parsed.vote ?? null,
    }
  } catch {
    return { ...emptyWork }
  }
}

export function AppProvider({ children }: { children: ReactNode }) {
  const [mode, setModeState] = useState<Mode>('stage')
  const [index, setIndex] = useState<ScenarioIndex | null>(null)
  const [scenario, setScenario] = useState<Scenario | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [time, setTime] = useState(12)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [previewId, setPreviewId] = useState<string | null>(null)
  const [reviews, setReviews] = useState<Record<string, ReviewStatus>>({})
  const [notes, setNotes] = useState<Record<string, string>>({})
  const [assignments, setAssignments] = useState<TeamMap>({})
  const [vote, setVote] = useState<'a' | 'b' | null>(null)
  const [phase, setPhase] = useState(0)
  const [layers, setLayers] = useState<LayerState>({ flood: true, roads: true, power: true, buildings: true, landuse: true })
  const [audit, setAudit] = useState<AuditEvent[]>([])
  const [toast, setToast] = useState<Toast | null>(null)
  const [reportOpen, setReportOpen] = useState(false)
  const [fieldOrderOpen, setFieldOrderOpen] = useState(false)
  const [provenanceOpen, setProvenanceOpen] = useState(false)
  const [fitSignal, setFitSignal] = useState(0)
  const [watchTarget, setWatchTarget] = useState<{ alertId?: string; scopeId?: string } | null>(null)
  const toastTimer = useRef<number | null>(null)
  const hydratedFor = useRef<string | null>(null)
  const mapRef = useRef<any>(null)

  const notify = useCallback((message: string, tone: Toast['tone'] = 'info') => {
    if (toastTimer.current) window.clearTimeout(toastTimer.current)
    setToast({ id: Date.now(), message, tone })
    toastTimer.current = window.setTimeout(() => setToast(null), 4200)
  }, [])

  const loadScenario = useCallback(async (id: string) => {
    setLoading(true)
    setError(null)
    try {
      const data = await loadJson<Scenario>(scenarioPath(id))
      setScenario(data)
      setTime(data.timeline.start)
      setSelectedId(null)
      setPreviewId(null)
      setPhase(0)
      setReportOpen(false)
      setFieldOrderOpen(false)
      setProvenanceOpen(false)
      setAudit(readAudit(id))
      setLoading(false)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not load scenario')
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const data = await loadJson<ScenarioIndex>(dataPath('index.json'))
        if (cancelled) return
        setIndex(data)
        await loadScenario(data.default)
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Could not load the demo pack')
          setLoading(false)
        }
      }
    })()
    return () => {
      cancelled = true
    }
  }, [loadScenario])

  // Restore analyst work when a scenario is loaded.
  useEffect(() => {
    if (!scenario) return
    const work = readWork(scenario.meta.id)
    setReviews(work.reviews)
    setNotes(work.notes)
    setAssignments(work.assignments)
    setVote(work.vote)
    hydratedFor.current = scenario.meta.id
  }, [scenario])

  // Persist analyst work.
  useEffect(() => {
    if (!scenario || hydratedFor.current !== scenario.meta.id) return
    try {
      localStorage.setItem(
        `georesponse.work.${scenario.meta.id}`,
        JSON.stringify({ reviews, notes, assignments, vote } satisfies WorkState),
      )
    } catch {
      // storage may be unavailable (private mode); the app still works in memory
    }
  }, [scenario, reviews, notes, assignments, vote])

  const ranked = useMemo(() => (scenario ? rankSites(scenario, reviews) : []), [scenario, reviews])
  const activeSites = useMemo(() => ranked, [ranked])
  const teamsAssigned = useMemo(() => new Set(Object.values(assignments)).size, [assignments])
  const workCount = useMemo(
    () => Object.values(reviews).filter((status) => status !== 'pending').length,
    [reviews],
  )

  const setMode = useCallback((next: Mode) => {
    setModeState(next)
    setReportOpen(false)
    setFieldOrderOpen(false)
    setProvenanceOpen(false)
    setPreviewId(null)
  }, [])

  const selectSite = useCallback((id: string | null) => {
    setSelectedId(id)
    if (id) setPreviewId(null)
  }, [])

  const previewSite = useCallback((id: string | null) => setPreviewId(id), [])

  const toggleLayer = useCallback((key: keyof LayerState) => {
    setLayers((current) => ({ ...current, [key]: !current[key] }))
  }, [])

  const record = useCallback(
    async (action: string, siteId?: string, detail?: Record<string, unknown>) => {
      if (!scenario) return
      try {
        const events = await appendAudit(scenario, action, { siteId, detail })
        setAudit(events)
      } catch {
        // non-fatal: the assessment remains usable
      }
    },
    [scenario],
  )

  const review = useCallback(
    (siteId: string, status: ReviewStatus, reason?: string) => {
      setReviews((current) => ({ ...current, [siteId]: status }))
      if (status === 'rejected') {
        setAssignments((current) => {
          const next = { ...current }
          delete next[siteId]
          return next
        })
        const site = scenario?.sites.find((s) => s.id === siteId)
        const isFalsePositive = scenario?.falsePositive?.siteId === siteId
        notify(
          isFalsePositive
            ? scenario?.falsePositive?.lesson ?? 'Finding rejected. Ranking re-ordered.'
            : `Finding ${siteId} rejected. It is removed from the ranking.`,
          'warn',
        )
        if (site && isFalsePositive) {
          void record('review.rejected', siteId, { reason: reason ?? scenario?.falsePositive?.analystReason })
          setPhase((p) => Math.max(p, 3))
        } else {
          void record('review.rejected', siteId, { reason: reason ?? 'analyst rejection' })
        }
      } else if (status === 'approved') {
        notify(`${siteId} approved. The audit trail records the decision.`, 'success')
        void record('review.approved', siteId)
      } else if (status === 'flagged') {
        notify(`${siteId} flagged for an adjuster.`, 'info')
        void record('review.flagged', siteId)
      }
    },
    [notify, record, scenario],
  )

  const setNote = useCallback(
    (siteId: string, note: string) => {
      setNotes((current) => ({ ...current, [siteId]: note }))
    },
    [],
  )

  const batchApprove = useCallback(
    (threshold: number) => {
      const eligible = ranked.filter(
        (item) => item.site.confidence >= threshold && (reviews[item.site.id] ?? 'pending') === 'pending',
      )
      if (!eligible.length) {
        notify('Nothing to approve above that confidence threshold.', 'warn')
        return
      }
      setReviews((current) => {
        const next = { ...current }
        for (const item of eligible) next[item.site.id] = 'approved'
        return next
      })
      notify(`${eligible.length} site(s) approved above ${Math.round(threshold * 100)}% confidence.`, 'success')
      void record('review.batch-approved', undefined, { count: eligible.length, threshold })
    },
    [notify, ranked, record, reviews],
  )

  const assign = useCallback(
    (siteId: string, team: string) => {
      setAssignments((current) => {
        const next: TeamMap = {}
        for (const [id, assignedTeam] of Object.entries(current)) {
          if (id !== siteId && assignedTeam !== team) next[id] = assignedTeam
        }
        next[siteId] = team
        return next
      })
      const site = scenario?.sites.find((s) => s.id === siteId)
      notify(`${team} → ${site?.name ?? siteId}.`, 'success')
      void record('team.assigned', siteId, { team })
    },
    [notify, record, scenario],
  )

  const unassign = useCallback(
    (siteId: string) => {
      setAssignments((current) => {
        const next = { ...current }
        delete next[siteId]
        return next
      })
      void record('team.unassigned', siteId)
    },
    [record],
  )

  const autoAssign = useCallback(() => {
    if (!scenario) return
    const teamCount = scenario.meta.teams
    const voteSiteId = vote ? scenario.audience[vote]?.id : null
    const plan: TeamMap = {}
    const slots = teamCount - (voteSiteId ? 1 : 0)
    let teamIndex = 1
    for (const item of ranked) {
      if (teamIndex > slots) break
      if (voteSiteId && item.site.id === voteSiteId) continue
      plan[item.site.id] = `Team ${teamIndex}`
      teamIndex += 1
    }
    if (voteSiteId) plan[voteSiteId] = `Team ${teamCount}`
    if (!Object.keys(plan).length) {
      notify('No active sites to assign.', 'warn')
      return
    }
    setAssignments(plan)
    notify(`${new Set(Object.values(plan)).size} teams assigned by rank and review status.`, 'success')
    void record('team.plan', undefined, { assignments: plan })
  }, [notify, ranked, record, scenario, vote])

  const voteAudience = useCallback(
    (choice: 'a' | 'b') => {
      if (!scenario) return
      const candidate = scenario.audience[choice]
      if (!candidate) return
      const teamCount = scenario.meta.teams
      const used = new Set(Object.values(assignments))
      let team = `Team ${teamCount}`
      for (let i = 1; i <= teamCount; i += 1) {
        if (!used.has(`Team ${i}`)) {
          team = `Team ${i}`
          break
        }
      }
      setVote(choice)
      setAssignments((current) => {
        const next: TeamMap = {}
        for (const [id, assignedTeam] of Object.entries(current)) {
          if (assignedTeam !== team && id !== candidate.id) next[id] = assignedTeam
        }
        next[candidate.id] = team
        return next
      })
      setSelectedId(candidate.id)
      notify(`${team} → ${candidate.name}. Trade-off: ${candidate.consequence}`, 'success')
      void record('audience.vote', candidate.id, { choice, team, consequence: candidate.consequence })
      setPhase((p) => Math.max(p, 4))
    },
    [assignments, notify, record, scenario],
  )

  const reset = useCallback(() => {
    if (!scenario) return
    setTime(scenario.timeline.start)
    setSelectedId(null)
    setPreviewId(null)
    setReviews({})
    setNotes({})
    setAssignments({})
    setVote(null)
    setPhase(0)
    setReportOpen(false)
    setFieldOrderOpen(false)
    setProvenanceOpen(false)
    try {
      localStorage.removeItem(`georesponse.work.${scenario.meta.id}`)
    } catch {
      // ignore
    }
    notify('Reset. Back to the cold open in under five seconds.', 'info')
    void record('session.reset', undefined, { time: scenario.timeline.start })
  }, [notify, record, scenario])

  const reveal = useCallback(() => {
    setPhase(5)
    setFitSignal((n) => n + 1)
    setReportOpen(true)
    void record('assessment.reveal')
  }, [record])

  const selectScenario = useCallback(
    (id: string) => {
      if (!scenario || id !== scenario.meta.id) void loadScenario(id)
    },
    [loadScenario, scenario],
  )

  const registerMap = useCallback((map: any) => {
    mapRef.current = map
    ;(window as unknown as { __georesponseMap?: any }).__georesponseMap = map
  }, [])

  const captureMap = useCallback(async (): Promise<string | null> => {
    try {
      const map = mapRef.current
      if (!map) return null
      if (typeof map.toDataURL === 'function') return (await map.toDataURL()) as string | null
      return null
    } catch {
      return null
    }
  }, [])

  const saveOffline = useCallback(async () => {
    if (!scenario || !('caches' in window)) {
      notify('This browser does not expose the Cache API.', 'warn')
      return
    }
    const cache = await caches.open('georesponse-v1')
    const shellAssets = Array.from(document.querySelectorAll('script[src], link[rel="stylesheet"][href]')).map((element) =>
      element instanceof HTMLScriptElement ? element.src : (element as HTMLLinkElement).href,
    )
    const urls = [
      document.baseURI,
      new URL('index.html', document.baseURI).toString(),
      new URL('manifest.webmanifest', document.baseURI).toString(),
      new URL('favicon.svg', document.baseURI).toString(),
      ...shellAssets,
      new URL('data/index.json', document.baseURI).toString(),
      new URL('data/proactive.json', document.baseURI).toString(),
      new URL(`data/scenarios/${scenario.meta.id}.json`, document.baseURI).toString(),
      new URL(scenario.imageryPair.before, document.baseURI).toString(),
      new URL(scenario.imageryPair.after, document.baseURI).toString(),
      ...scenario.sites.flatMap((site) => [
        new URL(site.evidence.before, document.baseURI).toString(),
        new URL(site.evidence.after, document.baseURI).toString(),
      ]),
      new URL(scenario.map.basemap.file, document.baseURI).toString(),
    ]
    await Promise.all(urls.map((url) => cache.add(url).catch(() => undefined)))
    notify(`Offline pack saved: ${urls.length} files cached.`, 'success')
    void record('offline.pack-saved', undefined, { files: urls.length })
  }, [notify, record, scenario])

  const value: AppContextValue = {
    mode,
    setMode,
    index,
    scenario,
    loading,
    error,
    time,
    setTime,
    selectedId,
    selectSite,
    previewId,
    previewSite,
    reviews,
    notes,
    assignments,
    vote,
    phase,
    setPhase,
    layers,
    toggleLayer,
    audit,
    toast,
    notify,
    ranked,
    activeSites,
    teamsAssigned,
    workCount,
    reportOpen,
    fieldOrderOpen,
    provenanceOpen,
    openReport: setReportOpen,
    openFieldOrder: setFieldOrderOpen,
    openProvenance: setProvenanceOpen,
    fitSignal,
    watchTarget,
    openWatchAlert: (alertId: string) => {
      setWatchTarget({ alertId })
      setModeState('watch')
    },
    openWatchScope: (scopeId: string) => {
      setWatchTarget({ scopeId })
      setModeState('watch')
    },
    clearWatchTarget: () => setWatchTarget(null),
    reveal,
    selectScenario,
    review,
    setNote,
    batchApprove,
    assign,
    unassign,
    autoAssign,
    voteAudience,
    reset,
    mapRef,
    registerMap,
    captureMap,
    saveOffline,
  }

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>
}

export function useApp(): AppContextValue {
  const value = useContext(AppContext)
  if (!value) throw new Error('useApp must be used inside AppProvider')
  return value
}
