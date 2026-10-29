import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)

if ('serviceWorker' in navigator && !new URLSearchParams(location.search).has('nosw')) {
  window.addEventListener('load', () => {
    window.setTimeout(() => {
      navigator.serviceWorker
        .register(new URL('sw.js', document.baseURI).toString())
        .catch(() => undefined)
    }, 2500)
  })
}
