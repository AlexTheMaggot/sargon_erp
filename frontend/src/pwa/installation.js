const listeners = new Set()
const standaloneQuery = typeof window !== 'undefined' ? window.matchMedia('(display-mode: standalone)') : null
let installationPrompt = null
let isInstalled = false

export function getInstallationState() {
  if (isInstalled || standaloneQuery?.matches || (typeof window !== 'undefined' && window.navigator.standalone === true)) return 'installed'
  return installationPrompt ? 'available' : 'manual'
}

export function subscribeInstallation(listener) {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

function notify() {
  listeners.forEach((listener) => listener())
}

function handleInstallPrompt(event) {
  event.preventDefault()
  installationPrompt = event
  notify()
}

function handleInstalled() {
  isInstalled = true
  installationPrompt = null
  notify()
}

export async function promptInstallation() {
  const prompt = installationPrompt
  if (!prompt) return 'unavailable'
  installationPrompt = null
  notify()
  await prompt.prompt()
  return (await prompt.userChoice).outcome
}

if (typeof window !== 'undefined') {
  window.addEventListener('beforeinstallprompt', handleInstallPrompt)
  window.addEventListener('appinstalled', handleInstalled)
  standaloneQuery.addEventListener('change', notify)

  if (import.meta.hot) {
    import.meta.hot.dispose(() => {
      window.removeEventListener('beforeinstallprompt', handleInstallPrompt)
      window.removeEventListener('appinstalled', handleInstalled)
      standaloneQuery.removeEventListener('change', notify)
    })
  }
}
