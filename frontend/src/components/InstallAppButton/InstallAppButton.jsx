import { lazy, Suspense, useState, useSyncExternalStore } from 'react'
import { getInstallationState, promptInstallation, subscribeInstallation } from '../../pwa/installation'
import { t } from '../../i18n/core'
import './InstallAppButton.css'

const InstallAppHelp = lazy(() => import('./InstallAppHelp'))

export function InstallAppButton() {
  const installationState = useSyncExternalStore(subscribeInstallation, getInstallationState)
  const [isHelpOpen, setIsHelpOpen] = useState(false)
  const [isInstalling, setIsInstalling] = useState(false)
  const [error, setError] = useState('')

  async function handleInstall() {
    setError('')
    if (installationState !== 'available') {
      setIsHelpOpen(true)
      return
    }
    setIsInstalling(true)
    try {
      if (await promptInstallation() === 'unavailable') setIsHelpOpen(true)
    } catch {
      setError('Не удалось открыть окно установки. Используйте меню браузера.')
      setIsHelpOpen(true)
    } finally {
      setIsInstalling(false)
    }
  }

  if (installationState === 'installed') return null

  return (
    <>
      <button className="secondary-button pwa-install-button" disabled={isInstalling} type="button" onClick={handleInstall}>
        {isInstalling ? t('Открываем установку…') : t('Установить приложение')}
      </button>
      {isHelpOpen && <Suspense fallback={<p role="status">{t('Загрузка…')}</p>}><InstallAppHelp error={error} onClose={() => setIsHelpOpen(false)} /></Suspense>}
    </>
  )
}
