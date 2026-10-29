export const euro = (value: number): string =>
  new Intl.NumberFormat('en-IE', { style: 'currency', currency: 'EUR', maximumFractionDigits: 0 }).format(value)

export const compactEuro = (value: number): string => {
  if (value >= 1_000_000) return `€${(value / 1_000_000).toFixed(value >= 10_000_000 ? 0 : 1)}m`
  if (value >= 1_000) return `€${Math.round(value / 1_000)}k`
  return euro(value)
}

export const pct = (value: number): string => `${Math.round(value * 100)}%`

export const number = (value: number): string => new Intl.NumberFormat('en-US').format(value)

export const minutes = (value: number): string => {
  if (value < 60) return `${Math.round(value)} min`
  const hours = Math.floor(value / 60)
  const rest = Math.round(value % 60)
  return rest ? `${hours} h ${rest} min` : `${hours} h`
}

export const timeLabel = (value: number): string => {
  const hour = Math.floor(value)
  const minute = Math.round((value - hour) * 60)
  return `${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}`
}

export const severityLabel = (severity: string): string =>
  ({ red: 'High risk', orange: 'Watch', yellow: 'Monitor' })[severity] ?? severity

export const reviewLabel = (status: string): string =>
  ({ approved: 'Approved', flagged: 'Flagged', rejected: 'Rejected', pending: 'Pending' })[status] ?? status

export const accessLabel = (status: string): string =>
  ({ blocked: 'Blocked', flooded: 'Flooded', restricted: 'Restricted', slow: 'Slow', debris: 'Debris', clear: 'Clear' })[status] ??
  status

export const hazardLabel = (hazard: string): string =>
  ({ flood: 'Flood', wildfire: 'Wildfire', construction: 'Construction' })[hazard] ?? hazard

export const missionClock = (phase: number): string => ['14:32', '14:38', '14:44', '14:51', '15:03', '15:14'][Math.min(phase, 5)]

export const cx = (...values: (string | false | null | undefined)[]): string => values.filter(Boolean).join(' ')

export const escapeHtml = (value: string): string =>
  value.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')

export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

export function downloadJson(payload: unknown, filename: string): void {
  downloadBlob(new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' }), filename)
}

export function downloadText(text: string, filename: string, mime = 'text/plain'): void {
  downloadBlob(new Blob([text], { type: mime }), filename)
}
