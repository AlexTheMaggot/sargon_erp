const LOGIN_HISTORY_KEY = 'shenoll_login_history'
const MAX_SAVED_LOGINS = 10

function normalizeLogins(logins) {
  if (!Array.isArray(logins)) return []
  return [...new Set(logins
    .filter((login) => typeof login === 'string')
    .map((login) => login.trim())
    .filter((login) => login.length > 0 && login.length <= 150))].slice(0, MAX_SAVED_LOGINS)
}

export function readLoginHistory() {
  try {
    return normalizeLogins(JSON.parse(localStorage.getItem(LOGIN_HISTORY_KEY)))
  } catch {
    return []
  }
}

export function rememberLogin(username) {
  const logins = normalizeLogins([username, ...readLoginHistory()])
  try {
    localStorage.setItem(LOGIN_HISTORY_KEY, JSON.stringify(logins))
  } catch {
    return
  }
}
