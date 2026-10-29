const baseHref = (): string => document.baseURI

export function asset(path: string): string {
  return new URL(path.replace(/^\//, ''), baseHref()).toString()
}

export async function loadJson<T>(path: string): Promise<T> {
  const response = await fetch(asset(path), { cache: 'no-cache' })
  if (!response.ok) throw new Error(`${response.status} ${response.statusText} for ${path}`)
  return (await response.json()) as T
}

export const dataPath = (file: string): string => `data/${file}`

export function scenarioPath(id: string): string {
  return `data/scenarios/${id}.json`
}

export function evidencePath(path: string): string {
  return asset(path)
}
