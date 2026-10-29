/* GeoResponse offline shell. Cache-first for the app, network-first for data. */
const CACHE = 'georesponse-v4'
const SHELL = ['./', './index.html', './favicon.svg', './manifest.webmanifest']

async function precacheShell() {
  const cache = await caches.open(CACHE)
  await cache.addAll(SHELL).catch(() => undefined)
  try {
    const response = await fetch('./')
    const html = await response.text()
    await cache.put('./index.html', new Response(html, { headers: { 'Content-Type': 'text/html' } }))
    const urls = []
    const pattern = /(?:src|href)="([^"]+)"/g
    let match = pattern.exec(html)
    while (match) {
      const url = new URL(match[1], self.location.href)
      if (url.origin === self.location.origin && /\.(js|css|svg|webmanifest)$/.test(url.pathname)) {
        urls.push(url.href)
      }
      match = pattern.exec(html)
    }
    await Promise.all(urls.map((url) => cache.add(url).catch(() => undefined)))
  } catch (error) {
    // offline install is best-effort; the next online visit completes it
  }
}

self.addEventListener('install', (event) => {
  event.waitUntil(precacheShell())
  self.skipWaiting()
})

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      const stale = keys.filter((key) => key !== CACHE)
      return Promise.all(stale.map((key) => caches.delete(key)))
    }),
  )
  self.clients.claim()
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
