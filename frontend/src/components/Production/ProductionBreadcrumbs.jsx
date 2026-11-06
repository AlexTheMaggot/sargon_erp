import { Link } from 'react-router'
import { t } from '../../i18n/core'
import { ProductionIcon } from './ProductionIcon'
import './ProductionBreadcrumbs.css'

export function ProductionBreadcrumbs({ section, title }) {
  return <nav className="production-breadcrumbs" aria-label={t('Навигация производства')}>
    <Link to="/production"><ProductionIcon name="grid" />{t('Все направления')}</Link>
    {section && <><span aria-hidden="true">/</span><Link to={`/production/${section.id}`}>{t(section.title)}</Link></>}
    <span aria-hidden="true">/</span><span aria-current="page">{title}</span>
  </nav>
}
