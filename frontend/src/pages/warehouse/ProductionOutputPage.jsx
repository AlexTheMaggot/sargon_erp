import { useRef, useState } from 'react'
import { DashboardShell } from '../../components/Layout/DashboardShell'
import { ListControls } from '../../components/ListControls/ListControls'
import { Modal } from '../../components/Modal/Modal'
import { emptyProductionOutputForm } from '../../constants/forms'
import { outputDispositionOptions, productionOutputConfig } from '../../constants/productionLoading'
import { useListControls } from '../../hooks/useListControls'
import { useProductionLoading } from '../../hooks/useProductionLoading'
import { formatNumber, getLocale, t } from '../../i18n/core'
import { ProductionBalances } from './ProductionBalances'
import './ProductionLoadingPage.css'

function newForm() {
  return {
    ...emptyProductionOutputForm,
    lines: emptyProductionOutputForm.lines.map((line) => ({ ...line })),
    material_usages: emptyProductionOutputForm.material_usages.map((usage) => ({ ...usage })),
  }
}

export function ProductionOutputPage({ onLogout, target, token, user }) {
  const config = productionOutputConfig[target]
  const { products, production_sources: sources, production_balances: balances, documents, error, isSubmitting, submit, cancel } = useProductionLoading(token, target, 'outputs')
  const [form, setForm] = useState(newForm)
  const [success, setSuccess] = useState('')
  const [cancelTarget, setCancelTarget] = useState(null)
  const requestKey = useRef(null)
  const submitting = useRef(false)
  const canCreate = user?.is_admin || user?.access?.[config.moduleCode]?.includes('create')
  const dispositions = outputDispositionOptions.filter((option) => target === 'canisters' || option.code !== 'deviation')
  const controls = useListControls(documents, (output) => [output.number, output.note, output.created_by, ...output.lines.map((line) => `${line.item.name} ${t(line.disposition_label)}`)].join(' '))

  function updateRow(collection, index, field, value) {
    setForm((current) => ({ ...current, [collection]: current[collection].map((row, position) => position === index ? { ...row, [field]: value } : row) }))
  }

  async function handleSubmit(event) {
    event.preventDefault()
    if (submitting.current) return
    requestKey.current ||= globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}`
    submitting.current = true
    setSuccess('')
    try {
      const result = await submit({
        ...form, idempotency_key: requestKey.current,
        lines: form.lines.map((line) => ({ ...line, item_id: Number(line.item_id), quantity: Number(line.quantity) })),
        material_usages: form.material_usages.map((usage) => ({ ...usage, source_movement_id: Number(usage.source_movement_id) })),
      })
      if (result) {
        setForm(newForm())
        requestKey.current = null
        setSuccess('Выпуск зарегистрирован. Остатки сырья в производстве обновлены.')
      }
    } finally { submitting.current = false }
  }

  return <DashboardShell title={t(config.title)} onLogout={onLogout} user={user}>
    <section className="page-title access-page-title">
      <p className="auth-eyebrow">{t('Производственный учёт')}</p><h1>{t(config.title)}</h1>
      <p>{t('Укажите выпуск в штуках и фактический расход уже загруженного сырья в килограммах. Повторного списания со склада нет.')}</p>
    </section>
    <p className="production-output-note">{t('Оприходование изделий на склад и распределение себестоимости по изделиям пока не выполняются.')}</p>
    {error && <p className="access-error" role="alert">{t(error)}</p>}
    {success && <p className="production-loading-success" role="status">{t(success)}</p>}
    <ProductionBalances balances={balances} />
    {canCreate && <section className="access-grid"><article className="access-card">
      <h3>{t('Зарегистрировать выпуск')}</h3>
      {!products.length && <p className="empty-state">{t('Создайте в номенклатуре изделия нужной линии с целой единицей измерения в штуках.')}</p>}
      {!sources.length && <p className="empty-state">{t('Для выпуска сначала загрузите сырьё в производство.')}</p>}
      <form className="crud-form" onSubmit={handleSubmit}>
        <fieldset className="production-loading-fields" disabled={isSubmitting || !products.length || !sources.length}>
          <h4>{t('Результаты выпуска')}</h4>
          {form.lines.map((line, index) => <div className="production-output-line" key={index}>
            <label><span>{t('Изделие')}</span><select required value={line.item_id} onChange={(event) => updateRow('lines', index, 'item_id', event.target.value)}><option value="">{t('Выберите изделие')}</option>{products.map((product) => <option key={product.id} value={product.id}>{product.name}</option>)}</select></label>
            <label><span>{t('Результат')}</span><select required value={line.disposition} onChange={(event) => updateRow('lines', index, 'disposition', event.target.value)}>{dispositions.map((option) => <option key={option.code} value={option.code}>{t(option.label)}</option>)}</select></label>
            <label><span>{t('Количество, шт.')}</span><input required type="number" min="1" max="2147483647" step="1" value={line.quantity} onChange={(event) => updateRow('lines', index, 'quantity', event.target.value)} /></label>
            <button type="button" className="secondary-button" disabled={form.lines.length === 1} onClick={() => setForm({ ...form, lines: form.lines.filter((_, position) => position !== index) })}>{t('Убрать строку')}</button>
          </div>)}
          <button type="button" className="secondary-button" disabled={form.lines.length >= 100} onClick={() => setForm({ ...form, lines: [...form.lines, { item_id: '', disposition: 'good', quantity: '' }] })}>{t('Добавить результат')}</button>
          <h4>{t('Фактический расход сырья')}</h4>
          {form.material_usages.map((usage, index) => {
            const source = sources.find((item) => item.id === Number(usage.source_movement_id))
            return <div className="production-loading-line" key={index}>
              <label><span>{t('Загрузка сырья')}</span><select required value={usage.source_movement_id} onChange={(event) => updateRow('material_usages', index, 'source_movement_id', event.target.value)}><option value="">{t('Выберите загрузку')}</option>{sources.filter((item) => item.id === Number(usage.source_movement_id) || !form.material_usages.some((row) => Number(row.source_movement_id) === item.id)).map((item) => <option key={item.id} value={item.id}>{item.item.name} · {item.loading_number} · {item.warehouse.name}</option>)}</select>{source && <small>{t('Доступно: ')}{formatNumber(source.available_quantity)} {t('кг')}</small>}</label>
              <label><span>{t('Расход, кг')}</span><input required type="number" min={source ? 10 ** -source.item.unit.decimal_places : '0.01'} step={source ? 10 ** -source.item.unit.decimal_places : '0.01'} max={source?.available_quantity} value={usage.quantity} onChange={(event) => updateRow('material_usages', index, 'quantity', event.target.value)} /></label>
              <button className="secondary-button" type="button" disabled={form.material_usages.length === 1} onClick={() => setForm({ ...form, material_usages: form.material_usages.filter((_, position) => position !== index) })}>{t('Убрать строку')}</button>
            </div>
          })}
          <button className="secondary-button" type="button" disabled={form.material_usages.length >= Math.min(sources.length, 100)} onClick={() => setForm({ ...form, material_usages: [...form.material_usages, { source_movement_id: '', quantity: '' }] })}>{t('Добавить расход')}</button>
          <label><span>{t('Комментарий')}</span><textarea maxLength={1000} value={form.note} onChange={(event) => setForm({ ...form, note: event.target.value })} /></label>
          <div className="form-actions"><button type="submit">{isSubmitting ? t('Проведение…') : t('Зарегистрировать выпуск')}</button><button className="secondary-button" type="button" onClick={() => { setForm(newForm()); requestKey.current = null; setSuccess('') }}>{t('Очистить форму')}</button></div>
        </fieldset>
      </form>
    </article></section>}
    <section className="access-grid"><article className="access-card">
      <h3>{t('История выпуска')}</h3>
      <ListControls {...controls} onPageChange={controls.setCurrentPage} onSearchChange={controls.setSearchQuery} />
      <div className="entity-list">{controls.paginatedItems.map((output) => <div className="entity-row" key={output.id}>
        <div><strong>{output.number}</strong><span>{new Date(output.created_at).toLocaleString(getLocale())} · {output.created_by}</span>
          {output.lines.map((line) => <span key={line.id}>{line.item.name} · {t(line.disposition_label)}: {formatNumber(line.quantity)} {t('шт.')}</span>)}
          {output.material_usages.map((usage) => <span key={usage.id}>{usage.item.name} · {usage.loading_number}: {formatNumber(usage.quantity)} {t('кг')}</span>)}
          <span>{t('Стоимость использованного сырья: ')}{formatNumber(output.material_cost, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} {t('сум')}</span>
          <span className={`status-pill ${output.is_cancelled ? 'rejected' : 'approved'}`}>{t(output.is_cancelled ? 'Отменён' : 'Зарегистрирован')}</span>
          {output.cancelled_at && <span>{t('Отменено: ')}{new Date(output.cancelled_at).toLocaleString(getLocale())} · {output.cancelled_by}</span>}
          {output.note && <span>{output.note}</span>}
        </div>
        {user?.is_admin && !output.is_cancelled && <button type="button" className="danger-button" disabled={isSubmitting} onClick={() => setCancelTarget(output)}>{t('Отменить')}</button>}
      </div>)}{!controls.filteredCount && <p className="empty-state">{t('Выпусков пока нет.')}</p>}</div>
    </article></section>
    {cancelTarget && <Modal title={t('Отменить выпуск')} onClose={() => setCancelTarget(null)}>
      {error && <p className="access-error">{t(error)}</p>}
      <p>{t('Расход будет отменён внутри производства. Материалы не вернутся на склад автоматически.')}</p><p>{cancelTarget.number}</p>
      <div className="form-actions"><button className="danger-button" type="button" disabled={isSubmitting} onClick={async () => { if (await cancel(cancelTarget.id)) setCancelTarget(null) }}>{t('Подтвердить отмену')}</button><button className="secondary-button" type="button" disabled={isSubmitting} onClick={() => setCancelTarget(null)}>{t('Закрыть')}</button></div>
    </Modal>}
  </DashboardShell>
}
