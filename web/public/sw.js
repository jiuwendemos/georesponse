/* GeoResponse offline shell. Cache-first for the app, network-first for data. */
const CACHE = 'georesponse-v3'
const SHELL = ['./', './index.html', './favicon.svg', './manifest.webmanifest']

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches
      .open(CACHE)
      .then((cache) => cache.addAll(SHELL))
      .catch(() => undefined),
  )
  self.skipWaiting()
})

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      const stale = keys.filter((key) => key !== CACHE)
      return Promise.all(stale.map((key) => caches.delete(key)))
    }),
  )
})

async function networkFirst(request, isNavigation) {
  try {
    const response = await fetch(request)
    if (response.ok) {
      const copy = response.clone()
      caches
        .open(CACHE)
        .then((cache) => cache.put(request, copy))
        .catch(() => undefined)
    }
    return response
  } catch (error) {
    const cached = await caches.match(request)
    if (cached) return cached
    if (isNavigation) {
      const shell = await caches.match('./index.html')
      if (shell) return shell
    }
    return Response.error()
  }
}

async function cacheFirst(request) {
  const cached = await caches.match(request)
  if (cached) return cached
  const response = await fetch(request)
  if (response.ok) {
    const copy = response.clone()
    caches
      .open(CACHE)
      .then((cache) => cache.put(request, copy))
      .catch(() => undefined)
  }
  return response
}

self.addEventListener('fetch', (event) => {
  const request = event.request
  if (request.method !== 'GET') return
  const url = new URL(request.url)
  if (url.origin !== self.location.origin) return

  const isData = url.pathname.includes('/data/')
  const isNavigation = request.mode === 'navigate'

  if (isData || isNavigation) {
    event.respondWith(networkFirst(request, isNavigation))
    return
  }

  event.respondWith(cacheFirst(request))
})
