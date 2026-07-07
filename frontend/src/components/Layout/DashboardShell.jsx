import { useState } from 'react'
import { NavLink } from 'react-router'
import sargonLogo from '../../assets/SARGON.svg'
import { navItems } from '../../constants/navigation'

function canViewModule(user, moduleCode) {
  if (!moduleCode) {
    return true
  }
  return Boolean(user?.access?.[moduleCode]?.includes('view'))
}

function filterNavItems(items, user) {
  return items
    .map((item) => {
      if (!item.children) {
        return canViewModule(user, item.moduleCode) ? item : null
      }

      const children = item.children.filter((child) => canViewModule(user, child.moduleCode))
      if (!children.length) {
        return null
      }
      return { ...item, children }
    })
    .filter(Boolean)
}

export function DashboardShell({ children, title, onLogout, user }) {
  const [isMenuOpen, setIsMenuOpen] = useState(false)
  const visibleNavItems = filterNavItems(navItems, user)

  function handleLogoutClick() {
    setIsMenuOpen(false)
    onLogout()
  }

  return (
    <main className="dashboard-page">
      <header className="app-topbar">
        <button
          className="burger-button"
          type="button"
          aria-label="Открыть меню"
          aria-expanded={isMenuOpen}
          onClick={() => setIsMenuOpen(true)}
        >
          <span />
          <span />
          <span />
        </button>
        <div className="app-nav-brand">
          <img src={sargonLogo} alt="Sargon ERP" />
          <span>{title}</span>
        </div>
      </header>

      <div
        className={`sidebar-overlay ${isMenuOpen ? 'open' : ''}`}
        role="presentation"
        onClick={() => setIsMenuOpen(false)}
      />

      <nav className={`side-nav ${isMenuOpen ? 'open' : ''}`} aria-label="Основная навигация">
        <div className="side-nav-header">
          <img src={sargonLogo} alt="Sargon ERP" />
          <button className="side-nav-close" type="button" aria-label="Закрыть меню" onClick={() => setIsMenuOpen(false)}>
            ×
          </button>
        </div>
        <div className="app-nav-links">
          {visibleNavItems.map((item) => (
            item.children ? (
              <div className="nav-section" key={item.label}>
                <span className="nav-section-title">{item.label}</span>
                <div className="nav-sub-links">
                  {item.children.map((child) => (
                    <NavLink key={child.path} to={child.path} onClick={() => setIsMenuOpen(false)}>
                      {child.label}
                    </NavLink>
                  ))}
                </div>
              </div>
            ) : (
              <NavLink key={item.path} to={item.path} onClick={() => setIsMenuOpen(false)}>
                {item.label}
              </NavLink>
            )
          ))}
        </div>
        <button className="secondary-button" type="button" onClick={handleLogoutClick}>
          Выйти
        </button>
      </nav>

      {children}
    </main>
  )
}
