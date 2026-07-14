import { useEffect, useState } from 'react'
import { BrowserRouter, Navigate, Route, Routes, useNavigate } from 'react-router'
import sargonLogo from '../../assets/SARGON.svg'
import { DashboardShell } from '../Layout/DashboardShell'
import { AccessGroupsPage, AccessModulesPage, AccessPermissionsPage, AccessUsersPage } from '../../pages/access/AccessPages'
import { CitiesPage, SuppliersPage } from '../../pages/directories/DirectoryPages'
import { LaboratoryAnalysesPage, RawMaterialReceiptsPage } from '../../pages/operations/OperationsPages'
import './App.css'

const TOKEN_STORAGE_KEY = 'sargon_access_token'

function getUserStartPath(user) {
  return user?.start_path || '/welcome'
}

function hasModuleAccess(user, moduleCode) {
  if (!moduleCode) {
    return true
  }
  return Boolean(user?.access?.[moduleCode]?.includes('view'))
}

function LoginPage({ onLogin }) {
  const navigate = useNavigate()
  const [username, setUsername] = useState('')
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
        throw new Error(data.detail || 'Не удалось войти')
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
        <div className="brand-block">
          <img className="brand-logo" src={sargonLogo} alt="Sargon ERP" />
          <p className="auth-eyebrow">Sargon ERP</p>
          <h1 id="login-title">Вход в систему</h1>
        </div>

        <form className="auth-form" onSubmit={handleSubmit}>
          <label>
            Логин
            <input
              autoComplete="username"
              name="username"
              onChange={(event) => setUsername(event.target.value)}
              type="text"
              value={username}
            />
          </label>

          <label>
            Пароль
            <input
              autoComplete="current-password"
              name="password"
              onChange={(event) => setPassword(event.target.value)}
              type="password"
              value={password}
            />
          </label>

          {error && <p className="auth-error">{error}</p>}

          <button disabled={isLoading} type="submit">
            {isLoading ? 'Входим...' : 'Войти'}
          </button>
        </form>
      </section>
    </main>
  )
}

function WelcomePage({ onLogout, token, user }) {
  const [userName, setUserName] = useState('пользователь')
  const [isCheckingAuth, setIsCheckingAuth] = useState(true)

  useEffect(() => {
    if (!token) {
      onLogout()
      return
    }

    async function loadGreeting() {
      const response = await fetch('/api/auth/me/', {
        headers: {
          Authorization: `Bearer ${token}`,
        },
      })
      const data = await response.json()

      if (!response.ok) {
        onLogout()
        return
      }

      setUserName(data.user.username)
      setIsCheckingAuth(false)
    }

    loadGreeting()
  }, [onLogout, token])

  return (
    <DashboardShell title="Операционная панель" onLogout={onLogout} user={user}>
      <section className="dashboard-hero">
        <div>
          <p className="auth-eyebrow">Sargon ERP</p>
          <h2>{isCheckingAuth ? 'Проверяем доступ...' : `Добро пожаловать, ${userName}`}</h2>
          <p>Главная страница очищена и готова для подключения реальных данных.</p>
        </div>
      </section>
    </DashboardShell>
  )
}

function ProtectedRoute({ children, moduleCode, token, user }) {
  if (!token) {
    return <Navigate to="/login" replace />
  }
  if (moduleCode && !user) {
    return null
  }
  if (moduleCode && !hasModuleAccess(user, moduleCode)) {
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
      <Route path="/welcome" element={<ProtectedRoute token={token} user={user}><WelcomePage onLogout={onLogout} token={token} user={user} /></ProtectedRoute>} />
      <Route path="/raw-material/receipts" element={<ProtectedRoute moduleCode="raw-material-receiving" token={token} user={user}><RawMaterialReceiptsPage onLogout={onLogout} token={token} user={user} /></ProtectedRoute>} />
      <Route path="/laboratory/analyses" element={<ProtectedRoute moduleCode="laboratory-analysis" token={token} user={user}><LaboratoryAnalysesPage onLogout={onLogout} token={token} user={user} /></ProtectedRoute>} />
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
