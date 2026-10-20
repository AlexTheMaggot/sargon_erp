import { t } from '../../i18n/core'
import { lazy, Suspense, useEffect, useState } from 'react'
import { BrowserRouter, Navigate, Route, Routes, useNavigate } from 'react-router'
import shenollLogo from '../../assets/SHENOLL.svg?no-inline'
import { LanguageSwitcher } from '../LanguageSwitcher/LanguageSwitcher'
import { InstallAppButton } from '../InstallAppButton/InstallAppButton'
import { useLanguage } from '../../i18n/useLanguage'
import { useLoginOptions } from '../../hooks/useLoginOptions'
import { AccessGroupsPage, AccessModulesPage, AccessPermissionsPage, AccessUsersPage } from '../../pages/access/AccessPages'
import { OverviewPage } from '../../pages/dashboard/OverviewPage'
import { CitiesPage, SuppliersPage } from '../../pages/directories/DirectoryPages'
import { LaboratoryAnalysesPage, RawMaterialReceiptsPage } from '../../pages/operations/OperationsPages'
import { BoilerLoadingPage, ChemicalMixerLoadingPage, ChemicalMixersPage, PreheatingBoilersPage, ProcessingJournalPage, ProcessingWorkshopsPage, RawDieselTankLoadingPage, RawDieselTanksPage, RawSpindleTankLoadingPage, RawSpindleTanksPage, ReceivingTanksPage, SeparatorLoadingPage, SeparatorOutputPage, SeparatorsPage, WorkshopLoadingPage } from '../../pages/processing/ProcessingPages'
import { WarehouseCategoriesPage, WarehouseInventoryPage, WarehouseIssuesPage, WarehouseItemsPage, WarehouseOverviewPage, WarehouseReceiptsPage, WarehousesPage, WarehouseTransfersPage, WarehouseUnitsPage } from '../../pages/warehouse/WarehousePages'
import './App.css'

const TOKEN_STORAGE_KEY = 'sargon_access_token'
const KnowledgePage = lazy(() => import('../../pages/knowledge/KnowledgePage').then((module) => ({ default: module.KnowledgePage })))

function getUserStartPath(user) {
  return user?.start_path || '/welcome'
}

function hasModuleAccess(user, moduleCode) {
  if (!moduleCode) {
    return true
  }
  return Boolean(user?.is_admin || user?.access?.[moduleCode]?.includes('view'))
}

function LoginPage({ onLogin }) {
  const navigate = useNavigate()
  const [username, setUsername] = useState('')
  const { logins, error: loginOptionsError } = useLoginOptions()
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [isLoading, setIsLoading] = useState(false)

  async function handleSubmit(event) {
    event.preventDefault()
    setError('')
    setIsLoading(true)

    try {
      const response = await fetch('/api/auth/login/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ username, password }),
      })
      const data = await response.json()

      if (!response.ok) {
        throw new Error(data.detail || t('Не удалось войти'))
      }

      const startPath = onLogin(data.access, data.user)
      navigate(startPath, { replace: true })
    } catch (loginError) {
      setError(loginError.message)
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <main className="auth-page">
      <section className="auth-card" aria-labelledby="login-title">
        <LanguageSwitcher />
        <div className="brand-block">
          <img className="brand-logo" src={shenollLogo} alt="Shenoll ERP" />
          <h1 id="login-title">{t('Вход в систему')}</h1>
        </div>

        <form className="auth-form" onSubmit={handleSubmit}>
          <label>{t('Логин')}<input
              autoComplete="username"
              list="login-options"
              name="username"
              onChange={(event) => setUsername(event.target.value)}
              type="text"
              value={username}
            />
          </label>
          <datalist id="login-options">
            {logins.map((login) => <option key={login} value={login} />)}
          </datalist>
          {loginOptionsError && <p className="login-options-hint" role="status">{t(loginOptionsError)}</p>}

          <label>{t('Пароль')}<input
              autoComplete="current-password"
              name="password"
              onChange={(event) => setPassword(event.target.value)}
              type="password"
              value={password}
            />
          </label>

          {error && <p className="auth-error">{t(error)}</p>}

          <button disabled={isLoading} type="submit">
            {isLoading ? t('Входим...') : t('Войти')}
          </button>
        </form>
        <InstallAppButton />
      </section>
    </main>
  )
}

function ProtectedRoute({ adminOnly = false, children, moduleCode, token, user }) {
  if (!token) {
    return <Navigate to="/login" replace />
  }
  if ((moduleCode || adminOnly) && !user) {
    return null
  }
  if (moduleCode && !hasModuleAccess(user, moduleCode)) {
    return <Navigate to="/welcome" replace />
  }
  if (adminOnly && !user?.is_admin) {
    return <Navigate to="/welcome" replace />
  }

  return children
}

function AppRoutes({ onLogin, onLogout, token, user }) {
  const hasToken = Boolean(token)
  const startPath = getUserStartPath(user)

  return (
    <Routes>
      <Route path="/login" element={hasToken ? <Navigate to={startPath} replace /> : <LoginPage onLogin={onLogin} />} />
      <Route path="/welcome" element={<ProtectedRoute token={token} user={user}><OverviewPage onLogout={onLogout} token={token} user={user} /></ProtectedRoute>} />
      <Route path="/knowledge" element={<ProtectedRoute moduleCode="knowledge-base" token={token} user={user}><Suspense fallback={<p className="empty-state">{t('Загрузка…')}</p>}><KnowledgePage onLogout={onLogout} token={token} user={user} /></Suspense></ProtectedRoute>} />
      <Route path="/raw-material/receipts" element={<ProtectedRoute moduleCode="raw-material-receiving" token={token} user={user}><RawMaterialReceiptsPage onLogout={onLogout} token={token} user={user} /></ProtectedRoute>} />
      <Route path="/laboratory/analyses" element={<ProtectedRoute moduleCode="laboratory-analysis" token={token} user={user}><LaboratoryAnalysesPage onLogout={onLogout} token={token} user={user} /></ProtectedRoute>} />
      <Route path="/processing/boiler-loading" element={<ProtectedRoute moduleCode="boiler-loading" token={token} user={user}><BoilerLoadingPage onLogout={onLogout} token={token} user={user} /></ProtectedRoute>} />
      <Route path="/processing/separator-loading" element={<ProtectedRoute moduleCode="separator-loading" token={token} user={user}><SeparatorLoadingPage onLogout={onLogout} token={token} user={user} /></ProtectedRoute>} />
      <Route path="/processing/separator-output" element={<ProtectedRoute moduleCode="separator-output" token={token} user={user}><SeparatorOutputPage onLogout={onLogout} token={token} user={user} /></ProtectedRoute>} />
      <Route path="/processing/chemical-mixer-loading" element={<ProtectedRoute moduleCode="chemical-mixer-loading" token={token} user={user}><ChemicalMixerLoadingPage onLogout={onLogout} token={token} user={user} /></ProtectedRoute>} />
      <Route path="/processing/workshop-loading" element={<ProtectedRoute moduleCode="workshop-loading" token={token} user={user}><WorkshopLoadingPage onLogout={onLogout} token={token} user={user} /></ProtectedRoute>} />
      <Route path="/processing/raw-diesel-tank-loading" element={<ProtectedRoute moduleCode="raw-diesel-tank-loading" token={token} user={user}><RawDieselTankLoadingPage onLogout={onLogout} token={token} user={user} /></ProtectedRoute>} />
      <Route path="/processing/raw-spindle-tank-loading" element={<ProtectedRoute moduleCode="raw-spindle-tank-loading" token={token} user={user}><RawSpindleTankLoadingPage onLogout={onLogout} token={token} user={user} /></ProtectedRoute>} />
      <Route path="/processing/receiving-tanks" element={<ProtectedRoute moduleCode="used-oil-processing" token={token} user={user}><ReceivingTanksPage onLogout={onLogout} token={token} user={user} /></ProtectedRoute>} />
      <Route path="/processing/preheating-boilers" element={<ProtectedRoute moduleCode="used-oil-processing" token={token} user={user}><PreheatingBoilersPage onLogout={onLogout} token={token} user={user} /></ProtectedRoute>} />
      <Route path="/processing/separators" element={<ProtectedRoute moduleCode="used-oil-processing" token={token} user={user}><SeparatorsPage onLogout={onLogout} token={token} user={user} /></ProtectedRoute>} />
      <Route path="/processing/chemical-mixers" element={<ProtectedRoute moduleCode="used-oil-processing" token={token} user={user}><ChemicalMixersPage onLogout={onLogout} token={token} user={user} /></ProtectedRoute>} />
      <Route path="/processing/workshops" element={<ProtectedRoute moduleCode="used-oil-processing" token={token} user={user}><ProcessingWorkshopsPage onLogout={onLogout} token={token} user={user} /></ProtectedRoute>} />
      <Route path="/processing/raw-diesel-tanks" element={<ProtectedRoute moduleCode="used-oil-processing" token={token} user={user}><RawDieselTanksPage onLogout={onLogout} token={token} user={user} /></ProtectedRoute>} />
      <Route path="/processing/raw-spindle-tanks" element={<ProtectedRoute moduleCode="used-oil-processing" token={token} user={user}><RawSpindleTanksPage onLogout={onLogout} token={token} user={user} /></ProtectedRoute>} />
      <Route path="/processing/journal" element={<ProtectedRoute adminOnly token={token} user={user}><ProcessingJournalPage onLogout={onLogout} token={token} user={user} /></ProtectedRoute>} />
      <Route path="/warehouse/overview" element={<ProtectedRoute moduleCode="warehouse-accounting" token={token} user={user}><WarehouseOverviewPage onLogout={onLogout} token={token} user={user} /></ProtectedRoute>} />
      <Route path="/warehouse/receipts" element={<ProtectedRoute moduleCode="warehouse-accounting" token={token} user={user}><WarehouseReceiptsPage onLogout={onLogout} token={token} user={user} /></ProtectedRoute>} />
      <Route path="/warehouse/issues" element={<ProtectedRoute moduleCode="warehouse-accounting" token={token} user={user}><WarehouseIssuesPage onLogout={onLogout} token={token} user={user} /></ProtectedRoute>} />
      <Route path="/warehouse/transfers" element={<ProtectedRoute moduleCode="warehouse-accounting" token={token} user={user}><WarehouseTransfersPage onLogout={onLogout} token={token} user={user} /></ProtectedRoute>} />
      <Route path="/warehouse/inventory" element={<ProtectedRoute moduleCode="warehouse-accounting" token={token} user={user}><WarehouseInventoryPage onLogout={onLogout} token={token} user={user} /></ProtectedRoute>} />
      <Route path="/warehouse/settings/items" element={<ProtectedRoute moduleCode="warehouse-settings" token={token} user={user}><WarehouseItemsPage onLogout={onLogout} token={token} user={user} /></ProtectedRoute>} />
      <Route path="/warehouse/settings/categories" element={<ProtectedRoute moduleCode="warehouse-settings" token={token} user={user}><WarehouseCategoriesPage onLogout={onLogout} token={token} user={user} /></ProtectedRoute>} />
      <Route path="/warehouse/settings/units" element={<ProtectedRoute moduleCode="warehouse-settings" token={token} user={user}><WarehouseUnitsPage onLogout={onLogout} token={token} user={user} /></ProtectedRoute>} />
      <Route path="/warehouse/settings/warehouses" element={<ProtectedRoute moduleCode="warehouse-settings" token={token} user={user}><WarehousesPage onLogout={onLogout} token={token} user={user} /></ProtectedRoute>} />
      <Route path="/directories/cities" element={<ProtectedRoute moduleCode="access" token={token} user={user}><CitiesPage onLogout={onLogout} token={token} user={user} /></ProtectedRoute>} />
      <Route path="/directories/suppliers" element={<ProtectedRoute moduleCode="suppliers" token={token} user={user}><SuppliersPage onLogout={onLogout} token={token} user={user} /></ProtectedRoute>} />
      <Route path="/access" element={<ProtectedRoute moduleCode="access" token={token} user={user}><Navigate to="/access/users" replace /></ProtectedRoute>} />
      <Route path="/access/users" element={<ProtectedRoute moduleCode="access" token={token} user={user}><AccessUsersPage onLogout={onLogout} token={token} user={user} /></ProtectedRoute>} />
      <Route path="/access/groups" element={<ProtectedRoute moduleCode="access" token={token} user={user}><AccessGroupsPage onLogout={onLogout} token={token} user={user} /></ProtectedRoute>} />
      <Route path="/access/modules" element={<ProtectedRoute moduleCode="access" token={token} user={user}><AccessModulesPage onLogout={onLogout} token={token} user={user} /></ProtectedRoute>} />
      <Route path="/access/permissions" element={<ProtectedRoute moduleCode="access" token={token} user={user}><AccessPermissionsPage onLogout={onLogout} token={token} user={user} /></ProtectedRoute>} />
      <Route path="*" element={<Navigate to={hasToken ? startPath : '/login'} replace />} />
    </Routes>
  )
}

function AppContent() {
  useLanguage()
  const navigate = useNavigate()
  const [token, setToken] = useState(() => localStorage.getItem(TOKEN_STORAGE_KEY))
  const [user, setUser] = useState(null)

  useEffect(() => {
    if (!token) {
      return undefined
    }

    let isCancelled = false

    async function validateToken() {
      try {
        const response = await fetch('/api/auth/me/', {
          headers: {
            Authorization: `Bearer ${token}`,
          },
        })

        if (!isCancelled && !response.ok) {
          localStorage.removeItem(TOKEN_STORAGE_KEY)
          setToken(null)
          setUser(null)
          navigate('/login', { replace: true })
          return
        }

        if (!isCancelled) {
          const data = await response.json()
          setUser(data.user)
        }
      } catch {
        // Keep the current token if the network is temporarily unavailable.
      }
    }

    validateToken()

    return () => {
      isCancelled = true
    }
  }, [navigate, token])

  function handleLogin(nextToken, nextUser) {
    localStorage.setItem(TOKEN_STORAGE_KEY, nextToken)
    setToken(nextToken)
    setUser(nextUser)
    return getUserStartPath(nextUser)
  }

  function handleLogout() {
    localStorage.removeItem(TOKEN_STORAGE_KEY)
    setToken(null)
    setUser(null)
    navigate('/login', { replace: true })
  }

  return <AppRoutes onLogin={handleLogin} onLogout={handleLogout} token={token} user={user} />
}

export default function App() {
  return (
    <BrowserRouter>
      <AppContent />
    </BrowserRouter>
  )
}
