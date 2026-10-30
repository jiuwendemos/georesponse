export type AgentIntent =
  | { kind: 'navigate'; target: 'stage' | 'watch' | 'analyst' | 'dashboard' | 'method' | 'booth' }
  | { kind: 'theme'; theme: 'light' | 'dark' | 'contrast' | 'system' }
  | { kind: 'density'; density: 'comfortable' | 'compact' }
  | { kind: 'motion'; enabled: boolean }
  | { kind: 'language'; language: 'en' | 'de' }
  | { kind: 'assign'; team: string }
  | { kind: 'scrub'; time: number | null }
  | { kind: 'reject-false-positive' }
  | { kind: 'open-report' }
  | { kind: 'open-field-order' }
  | { kind: 'offline' }
  | { kind: 'explain-alert'; alertId: string }
  | { kind: 'search-alerts'; query: string }
  | { kind: 'briefing' }
  | { kind: 'design-system' }
  | { kind: 'help' }
  | { kind: 'refuse'; reason: string }
  | { kind: 'unknown'; query: string }

const UNSAFE = [
  'approve claim automatically',
  'auto approve',
  'automatic approval',
  'dispatch automatically',
  'auto dispatch',
  'surveil',
  'face recognition',
  'track people',
  'ignore human review',
]

export function parseIntent(raw: string): AgentIntent {
  const query = raw.trim().toLowerCase()
  if (!query) return { kind: 'help' }

  for (const phrase of UNSAFE) {
    if (query.includes(phrase)) {
      return {
        kind: 'refuse',
        reason: 'That is outside the product’s safety boundary. GeoResponse never auto-approves claims, auto-dispatches crews, or monitors people.',
      }
    }
  }

  if (/(high contrast|contrast mode)/.test(query)) return { kind: 'theme', theme: 'contrast' }
  if (/(light mode|light theme|hell)/.test(query)) return { kind: 'theme', theme: 'light' }
  if (/(dark mode|dark theme|dunkel)/.test(query)) return { kind: 'theme', theme: 'dark' }
  if (/system theme|follow system/.test(query)) return { kind: 'theme', theme: 'system' }
  if (/compact/.test(query)) return { kind: 'density', density: 'compact' }
  if (/comfortable/.test(query)) return { kind: 'density', density: 'comfortable' }
  if (/reduce motion|motion off/.test(query)) return { kind: 'motion', enabled: false }
  if (/motion on/.test(query)) return { kind: 'motion', enabled: true }
  if (/\b(german|deutsch)\b/.test(query)) return { kind: 'language', language: 'de' }
  if (/\b(english|englisch)\b/.test(query)) return { kind: 'language', language: 'en' }
  if (/design system|style guide|tokens/.test(query)) return { kind: 'design-system' }
  if (/help|what can you do/.test(query)) return { kind: 'help' }
  if (/brief|what should i do|next step|situation/.test(query)) return { kind: 'briefing' }
  if (/field order/.test(query)) return { kind: 'open-field-order' }
  if (/assessment|report/.test(query)) return { kind: 'open-report' }
  if (/offline|save pack|download pack/.test(query)) return { kind: 'offline' }
  if (/(reject|false positive)/.test(query)) return { kind: 'reject-false-positive' }
  if (/assign team\s*([1-9])/.test(query)) {
    const match = query.match(/assign team\s*([1-9])/)
    return { kind: 'assign', team: `Team ${match?.[1] ?? '1'}` }
  }
  if (/(scrub|time|go to)\s*(?:to\s*)?(12|13|14|15|16|17|18)(:00)?/.test(query)) {
    const match = query.match(/(12|13|14|15|16|17|18)(:00)?/)
    return { kind: 'scrub', time: match ? Number(match[1]) : null }
  }
  if (/\balt-\d{3,}\b/.test(query)) {
    const match = query.match(/alt-\d{3,}/)
    return { kind: 'explain-alert', alertId: (match?.[0] ?? '').toUpperCase() }
  }
  if (/(alert|alerts)/.test(query)) {
    return { kind: 'search-alerts', query: raw }
  }
  for (const [target, pattern] of [
    ['watch', /watch|monitor/],
    ['analyst', /analyst|review/],
    ['dashboard', /pilot|dashboard|metrics/],
    ['method', /method|provenance|privacy/],
    ['booth', /booth|stage kit/],
    ['stage', /stage|map/],
  ] as const) {
    if (pattern.test(query)) return { kind: 'navigate', target }
  }
  return { kind: 'unknown', query: raw }
}

export const SUGGESTIONS = [
  'Brief me on the situation',
  'Show high-confidence flood alerts',
  'Open the Watch inbox',
  'Switch to light mode',
  'Open the design system',
  'Scrub to 18:00',
  'Reject the false positive',
  'Assign Team 2',
  'Explain ALT-1001',
]
