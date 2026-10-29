import type { ReviewStatus, Scenario, Site } from '../types'

export interface RankedSite {
  site: Site
  score: number
  rank: number
  contributions: Record<string, number>
}

const ACCESS_FACTOR: Record<string, number> = {
  blocked: 1,
  flooded: 0.92,
  restricted: 0.72,
  debris: 0.8,
  slow: 0.55,
  clear: 0.18,
}

const normalise = (values: number[]): number[] => {
  if (!values.length) return []
  const low = Math.min(...values)
  const high = Math.max(...values)
  if (high - low < 1e-9) return values.map(() => 0.5)
  return values.map((v) => (v - low) / (high - low))
}

/** Mirrors georesponse.ranking.rank_sites so the browser can re-rank instantly. */
export function rankSites(
  scenario: Scenario,
  reviews: Record<string, ReviewStatus> = {},
  exclude: Set<string> = new Set(),
): RankedSite[] {
  const weights = scenario.meta.weights
  const total = Object.values(weights).reduce((a, b) => a + b, 0)
  const candidates = scenario.sites.filter((s) => reviews[s.id] !== 'rejected' && !exclude.has(s.id))
  if (!candidates.length) return []
  const extents = normalise(candidates.map((s) => s.changeExtentM2))
  const values = normalise(candidates.map((s) => s.valueEur))
  const populations = normalise(candidates.map((s) => s.population))
  return candidates
    .map((site, i) => {
      const contributions = {
        extent: (extents[i] * weights.extent) / total,
        confidence: (site.confidence * weights.confidence) / total,
        value: (values[i] * weights.value) / total,
        access: ((ACCESS_FACTOR[site.accessStatus] ?? 0.5) * weights.access) / total,
        population: (populations[i] * weights.population) / total,
      }
      return {
        site,
        score: Object.values(contributions).reduce((a, b) => a + b, 0),
        rank: 0,
        contributions,
      }
    })
    .sort((a, b) => b.score - a.score || a.site.id.localeCompare(b.site.id))
    .map((item, index) => ({ ...item, rank: index + 1 }))
}

export function nextRank(ranked: RankedSite[], siteId: string): number {
  return ranked.find((r) => r.site.id === siteId)?.rank ?? 0
}
