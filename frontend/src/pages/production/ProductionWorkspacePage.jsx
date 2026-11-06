import { Link } from 'react-router'
import { DashboardShell } from '../../components/Layout/DashboardShell'
import { ProductionBreadcrumbs } from '../../components/Production/ProductionBreadcrumbs'
import { ProductionIcon } from '../../components/Production/ProductionIcon'
import { canViewProductionOperation, productionSections } from '../../constants/productionWorkspace'
import { t } from '../../i18n/core'
import './ProductionWorkspacePage.css'

export function ProductionWorkspacePage({ onLogout, sectionId, user }) {
  const sections = productionSections.map((section) => ({ ...section, operations: section.operations.filter((operation) => canViewProductionOperation(user, operation)) }))
  const section = sections.find((item) => item.id === sectionId)
  const title = t(section?.title || 'Производственные операции')

  return <DashboardShell title={title} onLogout={onLogout} user={user}>
    <div className="production-workspace">
      {sectionId && <ProductionBreadcrumbs title={title} />}
      <header className={`production-workspace-hero ${section ? `production-workspace-hero--${section.tone}` : ''}`}>
        <div><p className="production-workspace-eyebrow">{t('Рабочее место производства')}</p>
          <h1>{section ? t(section.title) : t('С чего начнём?')}</h1>
          <p>{section ? t('Выберите нужную операцию. Каждая карточка открывает отдельную форму.') : t('Выберите направление — все нужные формы собраны внутри.')}</p>
        </div>
        <ProductionIcon name={section?.icon || 'factory'} className="production-workspace-hero-icon" />
      </header>
      {!sectionId ? <div className="production-direction-grid">
        {sections.filter((item) => item.operations.length).map((item) => <Link className={`production-direction production-direction--${item.tone}`} to={`/production/${item.id}`} key={item.id}>
          <span className="production-direction-top"><span className="production-direction-icon"><ProductionIcon name={item.icon} /></span><span className="production-direction-count">{t('Операций')}: {item.operations.length}</span></span>
          <h2>{t(item.title)}</h2><p>{t(item.description)}</p>
          <span className="production-direction-action">{t('Открыть раздел')}<ProductionIcon name="arrow" /></span>
        </Link>)}
      </div> : section?.groups.map((group) => {
        const operations = section.operations.filter((operation) => operation.group === group.id)
        if (!operations.length) return null
        return <section className="production-operation-section" key={group.id}>
          <div className="production-operation-heading"><h2>{t(group.title)}</h2><span>{t('Операций')}: {operations.length}</span></div>
          <div className="production-operation-grid">{operations.map((operation) => <Link className="production-operation-card" key={operation.path} to={operation.path}>
            <span className="production-operation-icon"><ProductionIcon name={operation.icon} /></span>
            <div><h3>{t(operation.label)}</h3><p>{t(operation.description)}</p></div>
            <ProductionIcon name="arrow" className="production-operation-arrow" />
          </Link>)}</div>
        </section>
      })}
      {((!sectionId && !sections.some((item) => item.operations.length)) || (sectionId && !section?.operations.length)) && <p className="empty-state">{t('Нет доступных производственных операций. Обратитесь к администратору.')}</p>}
    </div>
  </DashboardShell>
}
