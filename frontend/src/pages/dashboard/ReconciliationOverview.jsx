import { reconciliationDifference, reconciliationLiters, reconciliationPercent } from '../../constants/containerReconciliation'
import { getLocale, t } from '../../i18n/core'
import './ReconciliationOverview.css'

function dateTime(value) {
  return new Date(value).toLocaleString(getLocale(), { dateStyle: 'short', timeStyle: 'short' })
}

export function RecyclingReconciliationSummary({ summary }) {
  return <section className="recycling-reconciliation" aria-label={t('Последняя сверка переработки')}>
    <div>
      <h2>{t('Последняя сверка переработки')}</h2>
      {summary ? <span>{dateTime(summary.created_at)} · {t`Сверено ${summary.measured_count} из ${summary.eligible_count} ёмкостей`}</span>
        : <span>{t('Сверок ещё не было.')}</span>}
    </div>
    {summary && <>
      <div><span>{t('Балансовое отклонение')}</span><strong>{reconciliationDifference(summary)}</strong></div>
      <div><span>{t('Суммарное расхождение')}</span><strong>
        {summary.absolute_deviation_percent != null && `${reconciliationPercent(summary.absolute_deviation_percent)} · `}
        {reconciliationLiters(summary.absolute_difference_liters)}
      </strong></div>
    </>}
  </section>
}

export function ReconciliationNodeDetails({ stage }) {
  if (!stage) return null
  const { summary } = stage
  return <section className="reconciliation-node-details">
    <h3>{t('Сверка остатков')}</h3>
    {summary && <p>
      {t('Отклонение этапа')}: <strong>{reconciliationDifference(summary)}</strong>
      {' · '}{dateTime(summary.measured_at)}{' · '}{t`Сверено ${summary.measured_count} из ${summary.eligible_count} ёмкостей`}
    </p>}
    {stage.containers.length > 0 && <ul>
      {stage.containers.map((container) => {
        const row = container.measurement
        return <li key={container.id}>
          <strong>{t(container.name)}</strong>
          <span>{row ? `${dateTime(row.measured_at)} · ${reconciliationDifference(row)}` : t('Нет замера')}</span>
          {row && <small>{t('По учёту')}: {reconciliationLiters(row.expected_liters)} · {t('Фактически')}: {reconciliationLiters(row.actual_liters)}</small>}
        </li>
      })}
    </ul>}
  </section>
}
