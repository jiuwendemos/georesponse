import { usePrefs } from '../prefs'

/**
 * Layout-matched loading placeholder. The map and the context rail occupy the
 * same grid as the real workspace, so the page does not jump when data lands.
 * Motion is a slow opacity pulse and is removed by reduced motion.
 */
export default function PageSkeleton() {
  const prefs = usePrefs()
  return (
    <div className="page-skeleton" aria-busy="true" aria-label="Loading workspace" data-motion={prefs.motion ? 'on' : 'off'}>
      <div className="skel skel-map" />
      <div className="skel-col">
        <div className="skel skel-panel" />
        <div className="skel skel-panel short" />
        <div className="skel skel-panel tall" />
      </div>
      <span className="sr-only">Loading workspace…</span>
    </div>
  )
}
