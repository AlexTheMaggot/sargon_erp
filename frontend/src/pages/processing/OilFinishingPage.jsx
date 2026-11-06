import { useRef, useState } from 'react'
import { DashboardShell } from '../../components/Layout/DashboardShell'
import { oilFinishingForms } from '../../constants/oilFinishing'
import { emptyOilFinishingForm } from '../../constants/forms'
import { useOilFinishing } from '../../hooks/useOilFinishing'
import { formatNumber, getLocale, t } from '../../i18n/core'
import './OilFinishingPage.css'

function volume(value) {
  return `${formatNumber(value, { maximumFractionDigits: 3 })} ${t('л')}`
}

export function OilFinishingPage({ onLogout, step, token, user }) {
  const config = oilFinishingForms[step]
  const [form, setForm] = useState(emptyOilFinishingForm)
  const [page, setPage] = useState(1)
  const [success, setSuccess] = useState(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const pending = useRef(false)
  const requestKey = useRef(null)
  const { sources, destinations, history, error, submit } = useOilFinishing(token, step, page)
  const canCreate = user?.is_admin || user?.access?.[step]?.includes('create')
  const source = sources.find((item) => String(item.id) === form.source_id)
  const availableSources = sources.filter((item) => item.is_active && Number(item.current_volume_liters) > 0)
  const availableDestinations = destinations.filter((item) => item.is_active && item.can_receive && (
    !source?.oil_product || !item.oil_product || source.oil_product === item.oil_product
  ))
  const destination = availableDestinations.find((item) => String(item.id) === form.destination_id)
  const amount = Number(form.volume_liters)
  const exceedsSource = source && amount > Number(source.current_volume_liters)
  const exceedsDestination = destination && amount > Number(destination.free_volume_liters)
  const otherProductOnLine = step === 'sorption-loading' && source?.oil_product && history.line_product && source.oil_product !== history.line_product
  const canSubmit = source?.is_active && destination && Number.isFinite(amount) && amount > 0 && !exceedsSource && !exceedsDestination && !otherProductOnLine

  function updateForm(field, value) {
    requestKey.current = null
    setSuccess(null)
    setForm((current) => ({ ...current, [field]: value, ...(field === 'source_id' ? { destination_id: '' } : {}) }))
  }

  async function handleSubmit(event) {
    event.preventDefault()
    if (pending.current || !canSubmit) return
    pending.current = true
    setIsSubmitting(true)
    requestKey.current ||= globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}`
    try {
      const result = await submit({ ...form, idempotency_key: requestKey.current })
      if (result) {
        setSuccess(result)
        setForm(emptyOilFinishingForm)
        requestKey.current = null
      }
    } finally {
      pending.current = false
      setIsSubmitting(false)
    }
  }

  return <DashboardShell title={t(config.title)} onLogout={onLogout} user={user}>
    <section className="page-title access-page-title">
      <p className="auth-eyebrow">{t('Переработка отработанного масла')}</p>
      <h1>{t(config.title)}</h1>
      <p>{t('Движение по общей линии очистки. Солярка и веретенка проходят её по очереди, без смешивания.')}</p>
    </section>
    {error && <p className="access-error" role="alert">{t(error)}</p>}
    {canCreate && <section className="boiler-loading-layout">
      <article className="access-card">
        <h3>{t('Новое движение')}</h3>
        <form className="crud-form" onSubmit={handleSubmit}>
          <fieldset className="oil-finishing-fields" disabled={isSubmitting}>
            <label><span>{t('Источник')}</span><select required value={form.source_id} onChange={(event) => updateForm('source_id', event.target.value)}>
              <option value="">{t('Выберите источник')}</option>
              {availableSources.map((item) => <option key={item.id} value={item.id}>{t(item.name)} · {volume(item.current_volume_liters)}</option>)}
            </select></label>
            <label><span>{t('Получатель')}</span><select required value={form.destination_id} onChange={(event) => updateForm('destination_id', event.target.value)}>
              <option value="">{t('Выберите получателя')}</option>
              {availableDestinations.map((item) => <option key={item.id} value={item.id}>{t(item.name)} · {t('Свободно: ')}{volume(item.free_volume_liters)}</option>)}
            </select></label>
            <label><span>{t('Объём движения, л')}</span><input required min="0.001" step="0.001" type="number" value={form.volume_liters} onChange={(event) => updateForm('volume_liters', event.target.value)} /></label>
            {exceedsSource && <p className="access-error">{t('В источнике недостаточно продукта.')}</p>}
            {exceedsDestination && <p className="access-error">{t('Объём превышает свободную вместимость получателя.')}</p>}
            {otherProductOnLine && <p className="access-error">{t('Общая линия занята другим продуктом. Сначала полностью освободите линию.')}</p>}
            {!availableSources.length && <p className="empty-state">{t('Нет активных источников с доступным продуктом.')}</p>}
            {!availableDestinations.length && <p className="empty-state">{t('Нет подходящих активных получателей со свободным местом.')}</p>}
            <div className="form-actions"><button disabled={!canSubmit} type="submit">{isSubmitting ? t('Выполняется...') : t('Подтвердить движение')}</button></div>
          </fieldset>
        </form>
      </article>
      <aside className="boiler-loading-summary"><article className="access-card">
        <h3>{t('Предварительный баланс')}</h3>
        <p>{t('Продукт')}: {t(source?.oil_product === 'diesel' ? 'Солярка' : source?.oil_product === 'spindle' ? 'Веретенка' : 'Не выбран')}</p>
        <p>{t('Останется в источнике')}: {source && canSubmit ? volume(Number(source.current_volume_liters) - amount) : '—'}</p>
        <p>{t('Будет у получателя')}: {destination && canSubmit ? volume(Number(destination.current_volume_liters) + amount) : '—'}</p>
      </article></aside>
    </section>}
    {success && <section className="access-grid"><article className="access-card movement-success-card" role="status">
      <h3>{t('Движение выполнено')}: {success.movement_number}</h3>
      <span>{t(success.source)} → {t(success.destination)} · {t(success.product_name)} · {volume(success.volume_liters)}</span>
    </article></section>}
    <section className="access-grid"><article className="access-card">
      <h3>{t('История движений')}</h3>
      <div className="entity-list">{history.items.map((item) => <div className="entity-row" key={item.id}><div>
        <strong>{item.movement_number}</strong>
        <span>{t(item.source)} → {t(item.destination)}</span>
        <span>{t(item.product_name)} · {volume(item.volume_liters)} · {new Date(item.moved_at).toLocaleString(getLocale())} · {item.created_by}</span>
        {item.is_compensated && <span>{t('Компенсировано')}</span>}
      </div></div>)}{!history.items.length && <p className="empty-state">{t('Записи не найдены.')}</p>}</div>
      <div className="list-pagination journal-pagination"><span>{history.total}{t(' записей')}</span><div className="pagination-actions">
        <button type="button" className="secondary-button" disabled={history.page <= 1} onClick={() => setPage(history.page - 1)}>{t('Назад')}</button>
        <strong>{history.page} / {history.page_count}</strong>
        <button type="button" className="secondary-button" disabled={history.page >= history.page_count} onClick={() => setPage(history.page + 1)}>{t('Вперёд')}</button>
      </div></div>
    </article></section>
  </DashboardShell>
}
