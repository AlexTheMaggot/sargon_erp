import { useRef, useState } from 'react'
import { DashboardShell } from '../../components/Layout/DashboardShell'
import { ListControls } from '../../components/ListControls/ListControls'
import { Modal } from '../../components/Modal/Modal'
import { emptyProductionLoadingForm } from '../../constants/forms'
import { productionLoadingConfig } from '../../constants/productionLoading'
import { useListControls } from '../../hooks/useListControls'
import { useProductionLoading } from '../../hooks/useProductionLoading'
import { formatNumber, getLocale, t } from '../../i18n/core'
import './ProductionLoadingPage.css'
import { ProductionBalances } from './ProductionBalances'

function newForm() {
  return { ...emptyProductionLoadingForm, lines: emptyProductionLoadingForm.lines.map((line) => ({ ...line })) }
}

export function ProductionLoadingPage({ onLogout, target, token, user }) {
  const config = productionLoadingConfig[target]
  const { warehouses, materials, production_balances, documents, error, isSubmitting, submit, cancel } = useProductionLoading(token, target)
  const [form, setForm] = useState(newForm)
  const [success, setSuccess] = useState('')
  const [cancelTarget, setCancelTarget] = useState(null)
  const requestKey = useRef(null)
  const submitting = useRef(false)
  const canCreate = user?.is_admin || user?.access?.[config.moduleCode]?.includes('create')
  const available = materials.filter((material) => material.warehouse_id === Number(form.source_warehouse_id))
  const controls = useListControls(documents, (document) => [
    document.number, document.source_warehouse?.name, document.purpose, t(document.status_label),
    ...document.lines.map((line) => line.item.name),
  ].join(' '))

  function updateLine(index, field, value) {
    setForm((current) => ({ ...current, lines: current.lines.map((line, position) => position === index ? { ...line, [field]: value } : line) }))
  }

  async function handleSubmit(event) {
    event.preventDefault()
    if (submitting.current) return
    requestKey.current ||= globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}`
    submitting.current = true
    setSuccess('')
    try {
      const result = await submit({
        ...form, source_warehouse_id: Number(form.source_warehouse_id), idempotency_key: requestKey.current,
        lines: form.lines.map((line) => ({ ...line, item_id: Number(line.item_id) })),
      })
      if (result) {
        setForm(newForm())
        requestKey.current = null
        setSuccess('Материалы переданы в производство. Складские остатки обновлены.')
      }
    } finally {
      submitting.current = false
    }
  }

  return (
    <DashboardShell title={t(config.title)} onLogout={onLogout} user={user}>
      <section className="page-title access-page-title">
        <p className="auth-eyebrow">{t('Материалы в производство')}</p>
        <h1>{t(config.title)}</h1>
        <p>{t(target === 'sorption' ? 'Новый сорбент списывается со склада и поступает в бак замкнутого контура.' : 'При проведении материалы сразу покидают склад. Готовая продукция этой операцией не создаётся.')}</p>
      </section>
      {error && <p className="access-error" role="alert">{t(error)}</p>}
      {success && <p className="production-loading-success" role="status">{t(success)}</p>}
      {canCreate && <section className="access-grid"><article className="access-card">
        <h3>{t('Новая загрузка')}</h3>
        {!warehouses.length && <p className="empty-state">{t('Сначала назначьте материалам производственное назначение и постоянные склады в настройках номенклатуры.')}</p>}
        <form className="crud-form" onSubmit={handleSubmit}>
          <fieldset className="production-loading-fields" disabled={isSubmitting || !warehouses.length}>
            <label><span>{t('Склад-источник')}</span><select required value={form.source_warehouse_id} onChange={(event) => setForm({ ...form, source_warehouse_id: event.target.value, lines: newForm().lines })}>
              <option value="">{t('Выберите склад')}</option>
              {warehouses.map((warehouse) => <option key={warehouse.id} value={warehouse.id}>{warehouse.name}</option>)}
            </select></label>
            {form.lines.map((line, index) => {
              const selected = available.find((material) => material.item.id === Number(line.item_id))
              return <div className="production-loading-line" key={index}>
                <label><span>{t('Материал')}</span><select required value={line.item_id} onChange={(event) => updateLine(index, 'item_id', event.target.value)}>
                  <option value="">{t('Выберите материал')}</option>
                  {available.filter((material) => material.item.id === Number(line.item_id) || !form.lines.some((other) => Number(other.item_id) === material.item.id)).map((material) => <option key={material.item.id} value={material.item.id}>{material.item.name}</option>)}
                </select>{selected && <small>{t('На складе: ')}{formatNumber(selected.quantity)} {t(selected.item.unit.symbol)}</small>}</label>
                <label><span>{t('Количество')}{selected ? `, ${t(selected.item.unit.symbol)}` : ''}</span><input required type="number" min={selected ? 10 ** -selected.item.unit.decimal_places : 0.01} step={selected ? 10 ** -selected.item.unit.decimal_places : 0.01} max={selected ? selected.quantity : undefined} value={line.quantity} onChange={(event) => updateLine(index, 'quantity', event.target.value)} /></label>
                <button type="button" className="secondary-button" disabled={form.lines.length === 1} onClick={() => setForm({ ...form, lines: form.lines.filter((_, position) => position !== index) })}>{t('Убрать строку')}</button>
              </div>
            })}
            <button className="secondary-button" type="button" disabled={!form.source_warehouse_id || form.lines.length >= available.length} onClick={() => setForm({ ...form, lines: [...form.lines, { item_id: '', quantity: '' }] })}>{t('Добавить материал')}</button>
            <label><span>{t('Комментарий')}</span><textarea maxLength={1000} value={form.purpose} onChange={(event) => setForm({ ...form, purpose: event.target.value })} /></label>
            <div className="form-actions">
              <button type="submit">{isSubmitting ? t('Проведение…') : t('Передать в производство')}</button>
              <button className="secondary-button" type="button" onClick={() => { setForm(newForm()); requestKey.current = null; setSuccess('') }}>{t('Очистить форму')}</button>
            </div>
          </fieldset>
        </form>
      </article></section>}
      <ProductionBalances balances={production_balances} target={target} />
      <section className="access-grid"><article className="access-card">
        <h3>{t('История загрузок')}</h3>
        <ListControls {...controls} onPageChange={controls.setCurrentPage} onSearchChange={controls.setSearchQuery} />
        <div className="entity-list">
          {controls.paginatedItems.map((document) => <div className="entity-row" key={document.id}>
            <div><strong>{document.number} · {document.source_warehouse.name}</strong>
              <span>{new Date(document.posted_at).toLocaleString(getLocale())} · {document.posted_by}</span>
              {document.lines.map((line) => <span key={line.id}>{line.item.name}: {formatNumber(line.quantity)} {t(line.item.unit.symbol)} · {formatNumber(line.material_cost, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} {t('сум')}</span>)}
              <span>{t('Стоимость материалов: ')}{formatNumber(document.material_cost, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} {t('сум')}</span>
              <span className={`status-pill ${document.status === 'cancelled' ? 'rejected' : 'approved'}`}>{t(document.status_label)}</span>
              {document.purpose && <span>{document.purpose === document.production_target_label ? t(document.production_target_label) : document.purpose}</span>}
            </div>
            {user?.is_admin && document.status === 'posted' && <button type="button" className="danger-button" disabled={isSubmitting} onClick={() => setCancelTarget(document)}>{t('Отменить')}</button>}
          </div>)}
          {!controls.filteredCount && <p className="empty-state">{t('Загрузок пока нет.')}</p>}
        </div>
      </article></section>
      {cancelTarget && <Modal title={t('Отменить загрузку')} onClose={() => setCancelTarget(null)}>
        {error && <p className="access-error" role="alert">{t(error)}</p>}
        <p>{t('Материалы будут возвращены на склад обратным движением. История загрузки сохранится.')}</p>
        <p>{cancelTarget.number}</p>
        <div className="form-actions"><button type="button" className="danger-button" disabled={isSubmitting} onClick={async () => { if (await cancel(cancelTarget.id)) setCancelTarget(null) }}>{t('Подтвердить отмену')}</button><button type="button" className="secondary-button" disabled={isSubmitting} onClick={() => setCancelTarget(null)}>{t('Закрыть')}</button></div>
      </Modal>}
    </DashboardShell>
  )
}
