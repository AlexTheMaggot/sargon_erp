import { useRef, useState } from 'react'
import { DashboardShell } from '../../components/Layout/DashboardShell'
import { ListControls } from '../../components/ListControls/ListControls'
import { Modal } from '../../components/Modal/Modal'
import { ProductionDetails } from '../../components/Production/ProductionDetails'
import { emptyProductionLoadingForm } from '../../constants/forms'
import { bentoniteLoadingTarget, chemicalMixerReagents, productionLoadingConfig } from '../../constants/productionLoading'
import { useListControls } from '../../hooks/useListControls'
import { useProductionLoading } from '../../hooks/useProductionLoading'
import { formatNumber, getLocale, t } from '../../i18n/core'
import './ProductionLoadingPage.css'
import { ProductionBalances } from './ProductionBalances'

function newForm() {
  return { ...emptyProductionLoadingForm, lines: emptyProductionLoadingForm.lines.map((line) => ({ ...line })) }
}

export function ChemicalMixerReagentsPage(props) {
  const [target, setTarget] = useState(chemicalMixerReagents.targets[0])
  return <ProductionLoadingPage {...props} key={target} target={target} onTargetChange={setTarget} />
}

export function ProductionLoadingPage({ onLogout, onTargetChange, target, token, user }) {
  const config = productionLoadingConfig[target]
  const mixerMode = Boolean(config.reagent)
  const bentoniteMode = target === bentoniteLoadingTarget
  const equipmentMode = bentoniteMode || mixerMode
  const { warehouses, materials, production_balances, mixers = [], filter_name: filterName, documents, error, isSubmitting, submit, cancel } = useProductionLoading(token, target, 'loadings', { includeHistory: !equipmentMode })
  const materialLabel = config.reagent || (bentoniteMode ? 'Бентонит' : '')
  const materialName = (item) => item.name === materialLabel ? t(materialLabel) : item.name
  const title = t(mixerMode ? chemicalMixerReagents.title : config.title)
  const [form, setForm] = useState(newForm)
  const [success, setSuccess] = useState('')
  const [cancelTarget, setCancelTarget] = useState(null)
  const requestKey = useRef(null)
  const submitting = useRef(false)
  const canCreate = user?.is_admin || user?.access?.[config.moduleCode]?.includes('create')
  const available = materials.filter((material) => material.warehouse_id === Number(form.source_warehouse_id))
  const activeMixer = mixers.find((mixer) => mixer.id === Number(form.mixer_id || (mixers.length === 1 ? mixers[0].id : '')))
  const selectedReagent = mixerMode && available.find((material) => material.item.id === Number(form.lines[0].item_id))
  const noReagentStock = mixerMode && (!selectedReagent || Number(selectedReagent.quantity) <= 0)
  const controls = useListControls(documents, (document) => [
    document.number, document.source_warehouse?.name, document.purpose, t(document.status_label),
    ...document.lines.map((line) => line.item.name),
  ].join(' '))

  function updateLine(index, field, value) {
    setForm((current) => ({ ...current, lines: current.lines.map((line, position) => position === index ? { ...line, [field]: value } : line) }))
  }

  async function handleSubmit(event) {
    event.preventDefault()
    if (!canCreate || submitting.current || (bentoniteMode && !filterName) || (mixerMode && (!activeMixer || noReagentStock))) return
    requestKey.current ||= globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}`
    submitting.current = true
    setSuccess('')
    try {
      const result = await submit({
        source_warehouse_id: Number(form.source_warehouse_id), idempotency_key: requestKey.current,
        ...(mixerMode ? { mixer_id: activeMixer.id } : {}),
        ...(!equipmentMode ? { purpose: form.purpose } : {}),
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
    <DashboardShell title={title} onLogout={onLogout} user={user}>
      <section className="page-title access-page-title">
        {!mixerMode && <p className="auth-eyebrow">{t('Материалы в производство')}</p>}
        <h1>{title}</h1>
        <p>{t(mixerMode ? 'Кислоту и бентонит оформляют отдельно. Загрузка не меняет объём масла в миксере.' : bentoniteMode ? 'Загрузка списывает бентонит со склада. В фильтре остаток не рассчитывается.' : 'При проведении материалы сразу покидают склад. Готовая продукция этой операцией не создаётся.')}</p>
      </section>
      {mixerMode && <div className="access-grid"><div className="production-mode-options" role="group" aria-label={t('Вид реагента')}>
        {chemicalMixerReagents.targets.map((option) => <button key={option} className={option === target ? '' : 'secondary-button'} aria-pressed={option === target} disabled={isSubmitting} type="button" onClick={() => onTargetChange(option)}>{t(productionLoadingConfig[option].reagent)}</button>)}
      </div></div>}
      {error && <p className="access-error" role="alert">{t(error)}</p>}
      {success && <p className="production-loading-success" role="status">{t(success)}</p>}
      {canCreate && <section className="access-grid"><article className="access-card">
        <h3>{t(mixerMode ? config.title : 'Новая загрузка')}</h3>
        {bentoniteMode && (filterName
          ? <p>{t('Оборудование')}: {t(filterName)}</p>
          : <p className="empty-state">{t('Настройте активный финишный фильтр.')}</p>)}
        {!warehouses.length && <p className="empty-state">{t('Сначала назначьте материалам производственное назначение и постоянные склады в настройках номенклатуры.')}</p>}
        <form className="crud-form" onSubmit={handleSubmit}>
          <fieldset className="production-loading-fields" disabled={isSubmitting || !warehouses.length || (bentoniteMode && !filterName) || (mixerMode && !mixers.length)}>
            {mixerMode && <select aria-label={t('Химический миксер')} required value={activeMixer?.id ?? ''} onChange={(event) => setForm({ ...form, mixer_id: event.target.value })}>
              <option value="">{t('Выберите активный химический миксер.')}</option>
              {mixers.map((mixer) => <option key={mixer.id} value={mixer.id}>{t(mixer.name)}</option>)}
            </select>}
            <label>
              {!equipmentMode && <span>{t('Склад-источник')}</span>}
              <select
                aria-label={equipmentMode ? t('Склад-источник') : undefined}
                required value={form.source_warehouse_id}
                onChange={(event) => setForm({ ...form, source_warehouse_id: event.target.value, lines: newForm().lines })}
              >
                <option value="">{t('Выберите склад')}</option>
                {warehouses.map((warehouse) => <option key={warehouse.id} value={warehouse.id}>{warehouse.name}</option>)}
              </select>
            </label>
            {form.lines.map((line, index) => {
              const selected = available.find((material) => material.item.id === Number(line.item_id))
              const quantityUnit = selected?.item.unit.symbol || (bentoniteMode ? 'кг' : '')
              const quantityLabel = quantityUnit ? `${t('Количество')}, ${t(quantityUnit)}` : t('Количество')
              return <div className="production-loading-line" key={index}>
                <label>
                  {!equipmentMode && <span>{t('Материал')}</span>}
                  <select aria-label={equipmentMode ? t(bentoniteMode ? 'Бентонит' : 'Материал') : undefined} required value={line.item_id} onChange={(event) => updateLine(index, 'item_id', event.target.value)}>
                    <option value="">{t(bentoniteMode ? 'Выберите бентонит' : 'Выберите материал')}</option>
                    {available.filter((material) => material.item.id === Number(line.item_id) || !form.lines.some((other) => Number(other.item_id) === material.item.id)).map((material) => <option key={material.item.id} value={material.item.id}>{materialName(material.item)}</option>)}
                  </select>
                  {selected && <small>{t('На складе: ')}{formatNumber(selected.quantity)} {t(selected.item.unit.symbol)}</small>}
                </label>
                <label>
                  {!equipmentMode && <span>{quantityLabel}</span>}
                  <input
                    aria-label={equipmentMode ? quantityLabel : undefined}
                    placeholder={equipmentMode ? quantityLabel : undefined}
                    required type="number"
                    min={selected ? 10 ** -selected.item.unit.decimal_places : 0.01}
                    step={selected ? 10 ** -selected.item.unit.decimal_places : 0.01}
                    max={selected ? selected.quantity : undefined}
                    value={line.quantity} onChange={(event) => updateLine(index, 'quantity', event.target.value)}
                  />
                </label>
                {!equipmentMode && <button type="button" className="secondary-button" disabled={form.lines.length === 1} onClick={() => setForm({ ...form, lines: form.lines.filter((_, position) => position !== index) })}>{t('Убрать строку')}</button>}
              </div>
            })}
            {!equipmentMode && <button className="secondary-button" type="button" disabled={!form.source_warehouse_id || form.lines.length >= available.length} onClick={() => setForm({ ...form, lines: [...form.lines, { item_id: '', quantity: '' }] })}>{t('Добавить материал')}</button>}
            {selectedReagent && noReagentStock && <p className="empty-state">{t('Нет остатка реагента для загрузки.')}</p>}
            {!equipmentMode && <label>
              <span>{t('Комментарий')}</span>
              <textarea maxLength={1000} value={form.purpose} onChange={(event) => setForm({ ...form, purpose: event.target.value })} />
            </label>}
            <div className="form-actions">
              <button disabled={noReagentStock} type="submit">{isSubmitting ? t('Проведение…') : t(equipmentMode ? 'Записать загрузку' : 'Передать в производство')}</button>
              <button className="secondary-button" type="button" onClick={() => { setForm(newForm()); requestKey.current = null; setSuccess('') }}>{t('Очистить форму')}</button>
            </div>
          </fieldset>
        </form>
      </article></section>}
      {!equipmentMode && <ProductionBalances balances={production_balances} />}
      {!equipmentMode && <ProductionDetails title={t('История загрузок')}>
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
      </ProductionDetails>}
      {cancelTarget && <Modal title={t('Отменить загрузку')} onClose={() => setCancelTarget(null)}>
        {error && <p className="access-error" role="alert">{t(error)}</p>}
        <p>{t('Материалы будут возвращены на склад обратным движением. История загрузки сохранится.')}</p>
        <p>{cancelTarget.number}</p>
        <div className="form-actions"><button type="button" className="danger-button" disabled={isSubmitting} onClick={async () => { if (await cancel(cancelTarget.id)) setCancelTarget(null) }}>{t('Подтвердить отмену')}</button><button type="button" className="secondary-button" disabled={isSubmitting} onClick={() => setCancelTarget(null)}>{t('Закрыть')}</button></div>
      </Modal>}
    </DashboardShell>
  )
}
