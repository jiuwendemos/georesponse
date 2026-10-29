import type { FeatureCollection, Geometry, Polygon } from 'geojson'

export type Severity = 'red' | 'orange' | 'yellow'
export type ReviewStatus = 'pending' | 'approved' | 'flagged' | 'rejected'
export type Mode = 'stage' | 'analyst' | 'watch' | 'dashboard' | 'method' | 'booth'

export interface WhyItem {
  label: string
  value: string
  detail: string
  icon: 'access' | 'power' | 'people'
}

export interface Policy {
  id: string
  holder: string
  propertyType: string
  valueEur: number
}

export interface Evidence {
  before: string
  after: string
  caption: string
}

export interface Site {
  id: string
  name: string
  kind: string
  kindLabel: string
  lon: number
  lat: number
  valueEur: number
  population: number
  confidence: number
  changeExtentM2: number
  accessStatus: string
  severity: Severity
  falsePositive?: boolean
  falsePositiveReason?: string
  why: WhyItem[]
  responseMinutes: number
  coverage: Polygon
  policy: Policy
  evidence: Evidence
  rank: number
  rankScore: number
  rankContributions: Record<string, number>
  detectedAt: string
  riskAt: number
  flooded: boolean
  assets?: { id: string; name: string; kind: string; valueEur: number; critical: boolean }[]
}

export interface Frame {
  t: number
  label: string
  areaKm2: number
  geometry: Geometry
}

export interface Timeline {
  mode: 'time' | 'period'
  start: number
  end: number
  step: number
  caption: string
  frames: Frame[]
}

export interface ScenarioMeta {
  id: string
  title: string
  subtitle: string
  hazard: 'flood' | 'wildfire' | 'construction'
  region: string
  eventDate: string
  eventTime: string
  center: [number, number]
  zoom: number
  bbox: [number, number, number, number]
  areaKm2: number
  teams: number
  accent: string
  baselineMinutes: number
  assessmentMinutes: number
  imagery: { source: string; attribution: string; resolution: string; simulated: boolean; acquired: string }
  model: string
  weights: Record<string, number>
  disclaimer: string
  sites: number
  timeline: { mode: string; start: number; end: number; step: number }
  basemap: { file: string; width: number; height: number; bounds: number[] }
}

export interface AssessmentFinding {
  id: string
  name: string
  rank: number
  score: number
  severity: Severity
  confidence: number
  confidenceLabel: string
  changeExtentM2: number
  valueEur: number
  population: number
  access: string
  review: string
  reviewReason?: string
  imagery: Evidence
  modelVersion: string
}

export interface Assessment {
  title: string
  generatedAt: string
  analyst: string
  modelVersion: string
  summary: string
  headline: string
  teams: number
  metrics: Record<string, number>
  findings: AssessmentFinding[]
  limitations: string[]
  claim: Record<string, unknown>
  disclosure: string
  trace: { step: number; tool: string; detail: string }[]
}

export interface AudienceCandidate {
  id: string
  name: string
  severity: Severity
  confidence: number
  valueEur: number
  population: number
  access: string
  responseMinutes: number
  coverage: Polygon
  kindLabel: string
  why: WhyItem[]
  consequence: string
}

export interface FieldOrderAssignment {
  team: string
  siteId: string
  siteName: string
  severity: Severity
  access: string
  responseMinutes: number
}

export interface FieldOrder {
  issuedAt: string
  incident: string
  region: string
  summary: string
  assignments: FieldOrderAssignment[]
  unassigned: string[]
  assessmentMinutes: number
  baselineMinutes: number
  signature: string
  modelVersion: string
  imagery: string
  quote: string
}

export interface Scenario {
  meta: ScenarioMeta
  sites: Site[]
  timeline: Timeline
  imageryPair: { before: string; after: string; caption: string }
  map: {
    basemap: { file: string; width: number; height: number; bounds: number[] }
    roads: FeatureCollection
    buildings: FeatureCollection
    landuse: FeatureCollection
    power: FeatureCollection
    water: FeatureCollection
    boundaries: FeatureCollection
    population: { lon: number; lat: number; people: number }[]
  }
  context: Record<string, number>
  ranking: RankedDisclosure[]
  rankingAfterReview: RankedDisclosure[]
  coveragePlan: { team: string; siteId: string; siteName: string; score: number }[]
  warnings: string[]
  falsePositive: null | {
    siteId: string
    title: string
    agentConfidence: number
    analystReason: string
    correction: string
    lesson: string
    narrative: string
  }
  audience: {
    prompt: string
    a: AudienceCandidate | null
    b: AudienceCandidate | null
    tradeoff: string
  }
  assessment: Assessment
  assessmentAfterReview: Assessment
  fieldOrder: FieldOrder
  reviewPolicy: { batchThreshold: number; slaHours: number; actions: string[]; humanInTheLoop: boolean }
  provenance: {
    imagery: { source: string; attribution: string; resolution: string; simulated: boolean; notes: string }
    model: string
    weights: Record<string, number>
    generatedAt: string
    disclaimer: string
    dataRights: string[]
  }
  hero: {
    areaKm2: number
    sites: number
    teams: number
    minutes: number
    baselineMinutes: number
    quote: string
    depot: [number, number]
  }
}

export interface RankedDisclosure {
  id: string
  rank: number
  score: number
  confidence: number
  severity: Severity
  why: Record<string, unknown>
  contributions: Record<string, number>
}

export interface ScenarioIndexEntry {
  id: string
  title: string
  subtitle: string
  hazard: string
  region: string
  date: string
  center: [number, number]
  zoom: number
  teams: number
  sites: number
  accent: string
  thumb: string
  quote: string
}

export interface ScenarioIndex {
  generatedAt: string
  default: string
  scenarios: ScenarioIndexEntry[]
  model: string
}

export interface AuditEvent {
  at: string
  action: string
  siteId?: string | null
  analyst?: string | null
  modelVersion?: string
  detail?: Record<string, unknown>
  prev: string
  hash: string
}

export interface PilotData {
  generatedAt: string
  disclaimer: string
  summary: {
    events: number
    claims: number
    detected: number
    confirmed: number
    falsePositives: number
    precision: number
    recall: number
    analystHoursSaved: number
    areaCoveredKm2: number
    avgAssessmentMinutes: number
    baselineMinutes: number
    accuracyTrend: { date: string; precision: number; recall: number; falsePositives: number }[]
  }
  history: {
    id: string
    region: string
    date: string
    claims: number
    detected: number
    confirmed: number
    falsePositives: number
    assessmentMinutes: number
    baselineMinutes: number
    analyst: string
    modelVersion: string
  }[]
  falsePositiveLog: { id: string; reason: string; category: string; confidence: number; review: string; location: string; modelVersion: string }[]
  byReason: { category: string; count: number }[]
  timeToAssessment: { manualMinutes: number; georesponseMinutes: number; savedMinutes: number; savedPct: number }
  cost: { analystHourlyEur: number; savedEur: number }
}

export interface RegionalEvents {
  generatedAt: string
  center: [number, number]
  bbox: number[]
  events: { id: string; name: string; lon: number; lat: number; severity: Severity; sites: number; approved: number; date: string }[]
  summary: { events: number; sites: number; approved: number }
}

export interface MonitoringData {
  generatedAt: string
  regions: { id: string; name: string; observedChange: number; history: number[] }[]
  alerts: {
    regionId: string
    observedChange: number
    baseline: { mean: number; std: number; n: number }
    zScore: number
    thresholdSigma: number
    minChange: number
    alert: boolean
    severity: string
    evaluatedAt: string
  }[]
  summary: { regions: number; alerts: number; red: number }
}

export interface PrivacyData {
  policy: string
  items: { id: string; requirement: string; status: string }[]
  open: number
  done: number
  note: string
}


// ---------------------------------------------------------------- proactive

export interface ProactiveScope {
  id: string
  tenant: string
  name: string
  kind: string
  region: string
  center: [number, number]
  bbox: [number, number, number, number]
  asset_class: string
  change_types: string[]
  cadence: string
  priority: number
  subscription_tier: string
  status: string
  freshness_slo_hours: number
  recipients: string[]
  tags: string[]
  created_at: string
  metadata: Record<string, unknown>
}

export interface ProactivePlan {
  scope_id: string
  cadence: string
  sources: string[]
  cloud_policy: string
  threshold_sigma: number
  min_change: number
  recipients: string[]
  sla_hours: number
  quiet_hours: [number, number] | null
  digest: string
  escalation: Record<string, unknown>[]
  budget_eur_per_month: number
  paused: boolean
  kill_switch: boolean
  coverage_mode: string
  retention_days: number
  first_n_alerts_require_analyst: number
  language: string
  channels: string[]
  updated_at: string
}

export interface ProactiveAlert {
  id: string
  tenant: string
  scope_id: string
  title: string
  summary: string
  severity: Severity
  urgency: number
  confidence: number
  change_type: string
  observed: number
  baseline: number
  lon: number
  lat: number
  incident_id: string | null
  status: string
  assignee: string | null
  sla_due: string | null
  created_at: string
  updated_at: string
  acknowledged_at: string | null
  resolved_at: string | null
  dismissed_reason: string | null
  dismissal_note: string | null
  asset: string | null
  value_eur: number
  population: number
  access: string
  source: string
  model_version: string
  evidence: { before?: string; after?: string; observation?: string }
  why: Record<string, unknown>
  provenance: Record<string, unknown>
  dedupe_key: string
  schema_version: string
  validated_by: string | null
  validation_count: number
  tags: string[]
}

export interface ProactiveIncident {
  id: string
  tenant: string
  scope_id: string
  title: string
  severity: Severity
  status: string
  alert_ids: string[]
  assignee: string | null
  opened_at: string
  closed_at: string | null
  summary: string
  timeline: { at: string; event: string; alertId?: string; actor?: string; note?: string }[]
  metadata: Record<string, unknown>
}

export interface ProactiveForecast {
  id: string
  region: string
  issued_at: string
  valid_from: string
  valid_to: string
  hazard: string
  probability: number
  rainfall_mm: number
  wind_kmh: number
  river_level_m: number
  uncertainty: number
  source: string
  confidence: number
  metadata: Record<string, unknown>
}

export interface ProactiveAcquisition {
  id: string
  scope_id: string
  source: string
  scheduled_for: string
  status: string
  cloud_forecast: number
  cost_eur: number
  priority: number
  attempts: number
  next_attempt_at: string | null
  idempotency_key: string
  bbox: [number, number, number, number] | null
  resolution_m: number
  scene_id: string | null
  received_at: string | null
  readiness: number
  blind_spot_reason: string | null
  provenance: Record<string, unknown>
  created_at: string
}

export interface ProactiveBaseline {
  scope_id: string
  metric: string
  values: number[]
  season: string
  mean: number
  std: number
  minimum: number
  maximum: number
  trend: string
  updated_at: string
  model_version: string
  confirmed_at: string | null
  metadata: Record<string, unknown>
}

export interface WatchlistEntry {
  scopeId: string
  name: string
  region: string
  hazard: string
  probability: number
  interval: [number, number]
  uncertainty: number
  leadTimeHours: number
  score: number
  urgency: number
  exposure: { valueEur: number; population: number; criticalAssets: number; assets: number }
  validTo: string
  forecastId: string
  recommendation: { teams: number; note: string; prioritySites: number; reason: string }
  taskingTrigger: boolean
  status: string
  computedAt: string
}

export interface CoverageEntry {
  scopeId: string
  name: string
  kind: string
  region: string
  bbox: [number, number, number, number]
  center: [number, number]
  areaKm2: number
  cadence: string
  status: string
  lastAcquisition: string | null
  nextExpected: string | null
  freshnessHours: number | null
  readiness: number
  coverageStatus: string
  blindSpot: boolean
  mode: string
  source: string | null
}

export interface ProactiveDashboard {
  tenant: string
  alerts: number
  open: number
  highRisk: number
  precision: number
  actionConversion: number
  slaBreaches: number
  scopes: number
  activeScopes: number
  monitoredKm2: number
  costPerKm2: number
  fatigue: { periodHours: number; alerts: number; analysts: number; perAnalyst: number; budgetPerAnalyst: number; overBudget: boolean; advice: string }
  freshness: { scopes: number; breached: number; breaches: { scopeId: string; freshnessHours: number | null }[]; status: string }
  blindSpots: { scopeId: string; name: string; region: string; status: string; freshnessHours: number | null; sloBreached: boolean; mode: string; reason: string }[]
  onCall: { primary: string; secondary: string; window: string }
  notifications: { id: string; alertId: string; channel: string; status: string; attempts: number }[]
  models: Record<string, unknown>[]
  governance: Record<string, unknown>
}

export interface ProactivePilot {
  tenant: string
  dashboard: ProactiveDashboard
  leadTimeHours: number | null
  gates: Record<string, boolean>
  launchReady: boolean
  criteria: Record<string, number>
  generatedAt: string
}

export interface ProactiveDigest {
  tenant: string
  periodHours: number
  generatedAt: string
  alerts?: number
  open?: number
  headline: string
  sections: { new: ProactiveAlert[]; inProgress: ProactiveAlert[]; resolved: ProactiveAlert[]; noAction: ProactiveAlert[] }
  fatigue: ProactiveDashboard['fatigue']
}

export interface ProactivePreferences {
  channels: string[]
  quietHours: [number, number] | null
  digest: string
  language: string
  alertBudgetPerDay: number
  escalationMinutes: number
  paused: boolean
  killSwitch: boolean
  recipients: { name?: string; email?: string; phone?: string; channels?: string[] }[]
}

export interface ProactiveModel {
  name: string
  version: string
  status: string
  metrics: Record<string, number>
  deployed_at: string
  rollback_to: string | null
  notes: string
}

export interface ProactiveData {
  generatedAt: string
  tenant: string
  mode: string
  disclaimer: string
  shadowMode: boolean
  scopes: ProactiveScope[]
  plans: ProactivePlan[]
  alerts: ProactiveAlert[]
  incidents: ProactiveIncident[]
  forecasts: ProactiveForecast[]
  acquisitions: ProactiveAcquisition[]
  baselines: ProactiveBaseline[]
  preferences: ProactivePreferences
  models: ProactiveModel[]
  dashboard: ProactiveDashboard
  watch: { watchlist: WatchlistEntry[]; heatmap: unknown[]; tasking: Record<string, unknown>; coverage: CoverageEntry[]; blindSpots: ProactiveDashboard['blindSpots']; freshness: ProactiveDashboard['freshness'] }
  pilot: ProactivePilot
  digest: ProactiveDigest
  quality: Record<string, unknown>
  governance: Record<string, unknown>
  coverage: CoverageEntry[]
  calendar: Record<string, { id: string; scheduledFor: string; status: string; source: string; cloudForecast: number; readiness: number; costEur: number; blindSpotReason: string | null }[]>
  notifications: { id: string; alertId: string; channel: string; recipient: string; status: string; attempts: number; nextAttemptAt: string | null; error: string | null }[]
  costs: { summary: { totalEur: number; byKind: Record<string, number>; byScope: Record<string, number>; entries: number }; byScope: { scopeId: string; name: string; totalEur: number }[] }
  blindSpots: ProactiveDashboard['blindSpots']
  freshness: ProactiveDashboard['freshness']
  killSwitch: boolean
}
