import { useState } from 'react'
import { NavLink, useLocation } from 'react-router'
import shenollLogo from '../../assets/SHENOLL.svg'
import { navItems } from '../../constants/navigation'

function canViewModule(user, moduleCode) {
  if (!moduleCode) {
    return true
  }
  return Boolean(user?.is_admin || user?.access?.[moduleCode]?.includes('view'))
}

function filterNavItems(items, user) {
  function canViewItem(item) {
    return (!item.adminOnly || user?.is_admin) && canViewModule(user, item.moduleCode)
  }

  return items
    .map((item) => {
      if (!item.children) {
        return canViewItem(item) ? item : null
      }

      const children = item.children.filter(canViewItem)
      if (!children.length) {
        return null
      }
      return { ...item, children }
    })
    .filter(Boolean)
}

export function DashboardShell({ children, title, onLogout, user }) {
  const location = useLocation()
  const [isMenuOpen, setIsMenuOpen] = useState(false)
  const [expandedSections, setExpandedSections] = useState(() => Object.fromEntries(
    navItems
      .filter((item) => item.children)
      .map((item) => [item.label, item.children.some((child) => child.path === location.pathname)]),
  ))
  const visibleNavItems = filterNavItems(navItems, user)

  function handleLogoutClick() {
    setIsMenuOpen(false)
    onLogout()
  }

  function toggleSection(sectionLabel) {
    setExpandedSections((current) => ({
      ...current,
      [sectionLabel]: !current[sectionLabel],
    }))
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
          <img src={shenollLogo} alt="Shenoll ERP" />
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
          <img src={shenollLogo} alt="Shenoll ERP" />
          <button className="side-nav-close" type="button" aria-label="Закрыть меню" onClick={() => setIsMenuOpen(false)}>
            ×
          </button>
        </div>
        <div className="app-nav-links">
          {visibleNavItems.map((item, itemIndex) => (
            item.children ? (
              <div className="nav-section" key={item.label}>
                <button
                  aria-controls={`nav-section-${itemIndex}`}
                  aria-expanded={Boolean(expandedSections[item.label])}
                  className={`nav-section-toggle ${item.children.some((child) => child.path === location.pathname) ? 'active' : ''}`}
                  type="button"
                  onClick={() => toggleSection(item.label)}
                >
                  <span>{item.label}</span>
                  <span aria-hidden="true" className="nav-section-chevron" />
                </button>
                <div
                  aria-hidden={!expandedSections[item.label]}
                  className={`nav-sub-links-shell ${expandedSections[item.label] ? 'open' : ''}`}
                  id={`nav-section-${itemIndex}`}
                >
                  <div className="nav-sub-links">
                    {item.children.map((child) => (
                      <NavLink
                        key={child.path}
                        tabIndex={expandedSections[item.label] ? undefined : -1}
                        to={child.path}
                        onClick={() => setIsMenuOpen(false)}
                      >
                        {child.label}
                      </NavLink>
                    ))}
                  </div>
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
