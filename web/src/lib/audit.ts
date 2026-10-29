import type { AuditEvent, Scenario } from '../types'

const GENESIS = '0'.repeat(64)

const canonical = (payload: Record<string, unknown>): string => {
  const keys = Object.keys(payload).sort()
  return JSON.stringify(payload, keys)
}

async function sha256(text: string): Promise<string> {
  const data = new TextEncoder().encode(text)
  const digest = await crypto.subtle.digest('SHA-256', data)
  return Array.from(new Uint8Array(digest))
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('')
}

export function auditKey(scenarioId: string): string {
  return `georesponse.audit.${scenarioId}`
}

export function readAudit(scenarioId: string): AuditEvent[] {
  try {
    return JSON.parse(localStorage.getItem(auditKey(scenarioId)) ?? '[]') as AuditEvent[]
  } catch {
    return []
  }
}

export async function appendAudit(
  scenario: Scenario,
  action: string,
  options: { siteId?: string; analyst?: string; detail?: Record<string, unknown> } = {},
): Promise<AuditEvent[]> {
  const events = readAudit(scenario.meta.id)
  const prev = events.length ? events[events.length - 1].hash : GENESIS
  const record: Omit<AuditEvent, 'hash'> = {
    at: new Date().toISOString(),
    action,
    siteId: options.siteId ?? null,
    analyst: options.analyst ?? 'A. Weber',
    modelVersion: scenario.meta.model,
    detail: options.detail ?? {},
    prev,
  }
  const hash = await sha256(canonical(record as unknown as Record<string, unknown>))
  const next = [...events, { ...record, hash }]
  localStorage.setItem(auditKey(scenario.meta.id), JSON.stringify(next))
  return next
}

export async function verifyAudit(scenarioId: string): Promise<{ ok: boolean; message: string; events: AuditEvent[] }> {
  const events = readAudit(scenarioId)
  let prev = GENESIS
  for (let index = 0; index < events.length; index += 1) {
    const event = events[index]
    if (event.prev !== prev) return { ok: false, message: `Event ${index + 1}: broken link`, events }
    const { hash, ...rest } = event
    const expected = await sha256(canonical(rest as unknown as Record<string, unknown>))
    if (expected !== hash) return { ok: false, message: `Event ${index + 1}: hash mismatch`, events }
    prev = hash
  }
  return { ok: true, message: `${events.length} events, chain intact`, events }
}
