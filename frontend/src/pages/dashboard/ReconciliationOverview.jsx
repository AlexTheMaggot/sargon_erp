import { reconciliationDifference, reconciliationLiters, reconciliationPercent } from '../../constants/containerReconciliation'
import { getLocale, t } from '../../i18n/core'
import './ReconciliationOverview.css'

function dateTime(value) {
  return new Date(value).toLocaleString(getLocale(), { dateStyle: 'short', timeStyle: 'short' })
}

export function ReconciliationDeviation({ row, absolute = false }) {
  if (!row) return t('Нет замера')

  const liters = absolute ? row.absolute_difference_liters : row.difference_liters
  const tone = Number(liters) === 0 ? 'zero' : 'nonzero'
  return <span className={`reconciliation-deviation--${tone}`}>
    {absolute
      ? <>{row.absolute_deviation_percent != null && `${reconciliationPercent(row.absolute_deviation_percent)} · `}{reconciliationLiters(liters)}</>
      : reconciliationDifference(row)}
  </span>
}

export function RecyclingReconciliationSummary({ summary }) {
  return <section className="recycling-reconciliation" aria-label={t('Последняя сверка переработки')}>
    <div>
      <h2>{t('Последняя сверка переработки')}</h2>
      {summary ? <span>{dateTime(summary.created_at)} · {t`Сверено ${summary.measured_count} из ${summary.eligible_count} ёмкостей`}</span>
        : <span>{t('Сверок ещё не было.')}</span>}
    </div>
    {summary?.comparable_count > 0 && <>
      <div><span>{t('Балансовое отклонение')}</span><strong><ReconciliationDeviation row={summary} /></strong></div>
      <div><span>{t('Суммарное расхождение')}</span><strong><ReconciliationDeviation row={summary} absolute /></strong></div>
    </>}
  </section>
}

export function ReconciliationNodeDetails({ stage }) {
  if (!stage) return null
  const { summary } = stage
  return <section className="reconciliation-node-details">
    <h3>{t('Сверка остатков')}</h3>
    {summary && <p>
      {t('Отклонение этапа')}: <strong><ReconciliationDeviation row={summary} /></strong>
      {' · '}{dateTime(summary.measured_at)}{' · '}{t`Сверено ${summary.measured_count} из ${summary.eligible_count} ёмкостей`}
    </p>}
    {stage.containers.length > 0 && <ul>
      {stage.containers.map((container) => {
        const row = container.measurement
        return <li key={container.id}>
          <strong>{t(container.name)}</strong>
          <span>{row && `${dateTime(row.measured_at)} · `}<ReconciliationDeviation row={row} /></span>
          {row && <small>{t('По учёту')}: {reconciliationLiters(row.expected_liters)} · {t('Фактически')}: {reconciliationLiters(row.actual_liters)}</small>}
        </li>
      })}
    </ul>}
  </section>
}
