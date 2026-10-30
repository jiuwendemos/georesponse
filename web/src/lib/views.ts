export interface SavedView {
  id: string
  name: string
  mode: string
  scenarioId: string
  createdAt: string
}

const KEY = 'georesponse.views.v1'

export function loadViews(): SavedView[] {
  try {
    const parsed = JSON.parse(localStorage.getItem(KEY) ?? '[]') as SavedView[]
    return Array.isArray(parsed) ? parsed.filter((view) => view && view.id && view.mode && view.scenarioId) : []
  } catch {
    return []
  }
}

export function saveView(view: Omit<SavedView, 'id' | 'createdAt'>): SavedView {
  const entry: SavedView = {
    ...view,
    id: `view-${Date.now().toString(36)}`,
    createdAt: new Date().toISOString(),
  }
  const views = [entry, ...loadViews().filter((existing) => !(existing.mode === view.mode && existing.scenarioId === view.scenarioId))].slice(0, 12)
  try {
    localStorage.setItem(KEY, JSON.stringify(views))
  } catch {
    // private mode: the view works for this session only
  }
  return entry
}

export function removeView(id: string): SavedView[] {
  const views = loadViews().filter((view) => view.id !== id)
  try {
    localStorage.setItem(KEY, JSON.stringify(views))
  } catch {
    // ignore
  }
  return views
}
