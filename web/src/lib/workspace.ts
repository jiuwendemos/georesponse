export type WorkspaceSeverity = 'red' | 'orange' | 'yellow'

export interface WorkspaceSite {
  id: string
  name: string
  lat: number
  lon: number
  severity: WorkspaceSeverity
  confidence: number
  valueEur: number
  population: number
  access: string
  notes: string
}

export interface ParseResult {
  sites: WorkspaceSite[]
  errors: string[]
}

const KEY = 'georesponse.workspace.sites.v1'
const TEMPLATE = `id,name,lat,lon,severity,confidence,value_eur,population,access,notes
S-1,North warehouse,50.5450,7.1000,red,0.86,4200000,120,clear,Loading bay on the north side
S-2,River pump station,50.5520,7.1150,orange,0.72,1800000,0,restricted,Access via the service road
`

export function loadSites(): WorkspaceSite[] {
  try {
    const parsed = JSON.parse(localStorage.getItem(KEY) ?? '[]') as WorkspaceSite[]
    return Array.isArray(parsed) ? parsed.filter(isSite) : []
  } catch {
    return []
  }
}

export function saveSites(sites: WorkspaceSite[]): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(sites))
  } catch {
    // private mode: keep in memory for this session
  }
}

export function templateCsv(): string {
  return TEMPLATE
}

export function isSite(value: unknown): value is WorkspaceSite {
  if (!value || typeof value !== 'object') return false
  const site = value as Partial<WorkspaceSite>
  return typeof site.id === 'string' && typeof site.name === 'string' && Number.isFinite(site.lat) && Number.isFinite(site.lon)
}

function splitCsvLine(line: string): string[] {
  const cells: string[] = []
  let current = ''
  let quoted = false
  for (let index = 0; index < line.length; index += 1) {
    const char = line[index]
    if (char === '"') {
      if (quoted && line[index + 1] === '"') {
        current += '"'
        index += 1
      } else {
        quoted = !quoted
      }
    } else if (char === ',' && !quoted) {
      cells.push(current.trim())
      current = ''
    } else {
      current += char
    }
  }
  cells.push(current.trim())
  return cells
}

function normalizeSeverity(value: string): WorkspaceSeverity {
  const lower = value.trim().toLowerCase()
  if (lower === 'red' || lower === 'high' || lower === 'high risk') return 'red'
  if (lower === 'yellow' || lower === 'low' || lower === 'monitor') return 'yellow'
  return 'orange'
}

function rowToSite(row: Record<string, string>, index: number): { site?: WorkspaceSite; error?: string } {
  const lat = Number(row.lat ?? row.latitude ?? row.y)
  const lon = Number(row.lon ?? row.lng ?? row.longitude ?? row.x)
  if (!row.name && !row.id) return { error: `row ${index + 1}: missing name` }
  if (!Number.isFinite(lat) || lat < -90 || lat > 90) return { error: `row ${index + 1}: lat must be between -90 and 90` }
  if (!Number.isFinite(lon) || lon < -180 || lon > 180) return { error: `row ${index + 1}: lon must be between -180 and 180` }
  const confidence = Number(row.confidence ?? row.conf ?? 0.7)
  const value = Number(String(row.value_eur ?? row.value ?? row.valueEur ?? 0).replace(/[^0-9.-]/g, ''))
  const population = Number(row.population ?? row.people ?? 0)
  return {
    site: {
      id: row.id || `S-${index + 1}`,
      name: row.name || row.id,
      lat,
      lon,
      severity: normalizeSeverity(row.severity ?? row.risk ?? 'orange'),
      confidence: Number.isFinite(confidence) ? Math.min(1, Math.max(0, confidence > 1 ? confidence / 100 : confidence)) : 0.7,
      valueEur: Number.isFinite(value) ? value : 0,
      population: Number.isFinite(population) ? population : 0,
      access: row.access || 'clear',
      notes: row.notes || row.note || '',
    },
  }
}

export function parseCsv(text: string): ParseResult {
  const lines = text.split(/\r?\n/).filter((line) => line.trim())
  if (lines.length < 2) return { sites: [], errors: ['CSV needs a header row and at least one data row'] }
  const header = splitCsvLine(lines[0]).map((cell) => cell.toLowerCase().replace(/\s+/g, '_'))
  const sites: WorkspaceSite[] = []
  const errors: string[] = []
  for (let index = 1; index < lines.length; index += 1) {
    const cells = splitCsvLine(lines[index])
    const row: Record<string, string> = {}
    header.forEach((key, column) => { row[key] = cells[column] ?? '' })
    const result = rowToSite(row, index)
    if (result.site) sites.push(result.site)
    else if (result.error) errors.push(result.error)
  }
  return { sites, errors }
}

export function parseGeoJson(text: string): ParseResult {
  let payload: unknown
  try {
    payload = JSON.parse(text)
  } catch {
    return { sites: [], errors: ['GeoJSON is not valid JSON'] }
  }
  const features: unknown[] = Array.isArray((payload as { features?: unknown[] }).features)
    ? ((payload as { features: unknown[] }).features)
    : []
  if (!features.length) return { sites: [], errors: ['GeoJSON needs a FeatureCollection with at least one feature'] }
  const sites: WorkspaceSite[] = []
  const errors: string[] = []
  features.forEach((raw, index) => {
    const feature = raw as { geometry?: { type?: string; coordinates?: number[] }; properties?: Record<string, unknown>; id?: string }
    const coords = feature.geometry?.coordinates
    if (feature.geometry?.type !== 'Point' || !Array.isArray(coords) || coords.length < 2) {
      errors.push(`feature ${index + 1}: only Point geometries are supported`)
      return
    }
    const properties = feature.properties ?? {}
    const row: Record<string, string> = {}
    for (const [key, value] of Object.entries(properties)) row[key.toLowerCase()] = String(value ?? '')
    row.lon = String(coords[0])
    row.lat = String(coords[1])
    row.id = row.id || String(feature.id ?? `S-${index + 1}`)
    const result = rowToSite(row, index)
    if (result.site) sites.push(result.site)
    else if (result.error) errors.push(result.error)
  })
  return { sites, errors }
}

export function parseAny(text: string): ParseResult {
  const trimmed = text.trim()
  return trimmed.startsWith('{') || trimmed.startsWith('[') ? parseGeoJson(trimmed) : parseCsv(trimmed)
}

export function toGeoJson(sites: WorkspaceSite[]): string {
  return JSON.stringify({
    type: 'FeatureCollection',
    features: sites.map((site) => ({
      type: 'Feature',
      id: site.id,
      geometry: { type: 'Point', coordinates: [site.lon, site.lat] },
      properties: {
        name: site.name,
        severity: site.severity,
        confidence: site.confidence,
        value_eur: site.valueEur,
        population: site.population,
        access: site.access,
        notes: site.notes,
      },
    })),
  }, null, 2)
}

export function toCsv(sites: WorkspaceSite[]): string {
  const header = 'id,name,lat,lon,severity,confidence,value_eur,population,access,notes'
  const rows = sites.map((site) => [
    site.id, site.name, site.lat, site.lon, site.severity, site.confidence, site.valueEur, site.population, site.access, site.notes,
  ].map((value) => `"${String(value).replaceAll('"', '""')}"`).join(','))
  return [header, ...rows].join('\n')
}
