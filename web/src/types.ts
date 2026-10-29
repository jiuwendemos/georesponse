import type { FeatureCollection, Geometry, Polygon } from 'geojson'

export type Severity = 'red' | 'orange' | 'yellow'
export type ReviewStatus = 'pending' | 'approved' | 'flagged' | 'rejected'
export type Mode = 'stage' | 'analyst' | 'dashboard' | 'method' | 'booth'

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
