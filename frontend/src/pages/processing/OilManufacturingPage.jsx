import { useRef, useState } from 'react'
import { DashboardShell } from '../../components/Layout/DashboardShell'
import { ListControls } from '../../components/ListControls/ListControls'
import { Modal } from '../../components/Modal/Modal'
import { emptyOilManufacturingForms } from '../../constants/forms'
import { oilManufacturingConfig } from '../../constants/oilManufacturing'
import { useListControls } from '../../hooks/useListControls'
import { useOilManufacturing } from '../../hooks/useOilManufacturing'
import { formatNumber, getLocale, t } from '../../i18n/core'
import './OilFinishingPage.css'

function liters(value) {
  return `${formatNumber(value, { maximumFractionDigits: 3 })} ${t('л')}`
}

function Selection({ label, value, onChange, items, disabled = false }) {
  return <label><span>{t(label)}</span><select required disabled={disabled} value={value} onChange={(event) => onChange(event.target.value)}>
    <option value="">{t('Выберите значение')}</option>
    {items.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}
  </select></label>
}

export function OilManufacturingPage({ onLogout, step, token, user }) {
  const config = oilManufacturingConfig[step]
  const [form, setForm] = useState(emptyOilManufacturingForms[step])
  const [success, setSuccess] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [actionTarget, setActionTarget] = useState(null)
  const [reason, setReason] = useState('')
  const requestKey = useRef(null)
  const pending = useRef(false)
  const { data, error, submit, complete, cancel } = useOilManufacturing(token, step)
  const canCreate = user?.is_admin || user?.access?.[step]?.includes('create')
  const controls = useListControls(data.items, (item) => [item.number, item.movement_number, t(item.equipment_name), item.grade_name, t(item.status_label), t(item.source), t(item.destination), item.created_by].join(' '))
  const selectedMaterial = data.materials?.find((item) => String(item.id) === form.item_id && String(item.warehouse_id) === form.warehouse_id)
  const selectedBatch = data.blender_batches?.find((item) => String(item.id) === form.batch_id)
  const tanks = (data.tanks || []).filter((item) => step !== 'oil-filling' || Number(item.current_volume_liters) > 0)
    .filter((item) => !selectedBatch || item.oil_grade_id === selectedBatch.oil_grade_id)
  const selectedTank = tanks.find((item) => String(item.id) === form.tank_id)

  function update(field, value) {
    requestKey.current = null
    setSuccess('')
    setForm((current) => ({ ...current, [field]: value,
      ...(field === 'warehouse_id' ? { item_id: '' } : {}),
      ...(field === 'batch_id' ? { tank_id: '' } : {}),
    }))
  }

  async function handleSubmit(event) {
    event.preventDefault()
    if (pending.current) return
    pending.current = true
    setIsSubmitting(true)
    requestKey.current ||= globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}`
    try {
      const payload = Object.fromEntries(Object.entries(form).map(([field, value]) => [field, field.endsWith('_id') ? Number(value) : value]))
      const result = await submit({ ...payload, idempotency_key: requestKey.current })
      if (result) {
        setSuccess(`${t('Операция сохранена')}: ${result.number || result.movement_number}`)
        setForm(emptyOilManufacturingForms[step])
        requestKey.current = null
      }
    } finally {
      pending.current = false
      setIsSubmitting(false)
    }
  }

  async function handleAction(event) {
    event.preventDefault()
    if (pending.current) return
    pending.current = true
    setIsSubmitting(true)
    try {
      const result = actionTarget.action === 'complete' ? await complete(actionTarget.item.id) : await cancel(actionTarget.item.id, reason)
      if (result) setActionTarget(null)
    } finally {
      pending.current = false
      setIsSubmitting(false)
    }
  }

  return <DashboardShell title={t(config.title)} user={user} onLogout={onLogout}>
    <section className="page-title access-page-title"><p className="auth-eyebrow">{t('Производство масел')}</p><h1>{t(config.title)}</h1>
      <p>{t('Загрузки учитываются отдельно. Фактический выход фиксируется при переливе, без сложения килограммов и литров.')}</p>
    </section>
    {error && <p className="access-error" role="alert">{t(error)}</p>}
    {success && <p className="oil-manufacturing-success" role="status">{success}</p>}
    {canCreate && <section className="access-grid"><article className="access-card">
      <h3>{t('Новая операция')}</h3>
      <form className="crud-form" onSubmit={handleSubmit}><fieldset disabled={isSubmitting} className="oil-finishing-fields">
        {config.batch && <>
          <Selection label="Оборудование" value={form.equipment_id} onChange={(value) => update('equipment_id', value)} items={(data.equipment || []).map((item) => ({ id: item.id, label: `${t(item.name)} · ${liters(item.capacity_liters)}` }))} />
          {!data.equipment?.length && <p className="empty-state">{t('Нет свободного активного оборудования. Создайте оборудование или завершите предыдущую партию.')}</p>}
          <Selection label="Бак готовой веретенки" value={form.source_tank_id} onChange={(value) => update('source_tank_id', value)} items={(data.base_tanks || []).filter((item) => Number(item.current_volume_liters) > 0).map((item) => ({ id: item.id, label: `${t(item.name)} · ${liters(item.current_volume_liters)}` }))} />
          <label><span>{t('Веретенка, л')}</span><input required type="number" min="0.001" step="0.001" max={data.base_tanks?.find((item) => String(item.id) === form.source_tank_id)?.current_volume_liters} value={form.base_liters} onChange={(event) => update('base_liters', event.target.value)} /></label>
        </>}
        {step === 'concentrate-loading' && <>
          <Selection label="Склад полипропилена" value={form.warehouse_id} onChange={(value) => update('warehouse_id', value)} items={(data.warehouses || []).map((item) => ({ id: item.id, label: item.name }))} />
          <Selection label="Полипропилен" value={form.item_id} onChange={(value) => update('item_id', value)} items={(data.materials || []).filter((item) => String(item.warehouse_id) === form.warehouse_id).map((item) => ({ id: item.id, label: `${item.name} · ${formatNumber(item.quantity)} ${t('кг')}` }))} />
          <label><span>{t('Полипропилен, кг')}</span><input required type="number" min={selectedMaterial ? 10 ** -selectedMaterial.decimal_places : 0.01} step={selectedMaterial ? 10 ** -selectedMaterial.decimal_places : 0.01} max={selectedMaterial?.quantity} value={form.polypropylene_quantity} onChange={(event) => update('polypropylene_quantity', event.target.value)} /></label>
          <p>{t('Полипропилен списывается со склада одновременно с загрузкой веретенки в реактор.')}</p>
        </>}
        {step === 'oil-blending' && <>
          <Selection label="Марка масла" value={form.oil_grade_id} onChange={(value) => update('oil_grade_id', value)} items={(data.grades || []).map((item) => ({ id: item.id, label: item.name }))} />
          <Selection label="Партия концентрата" value={form.concentrate_batch_id} onChange={(value) => update('concentrate_batch_id', value)} items={(data.concentrate_batches || []).map((item) => ({ id: item.id, label: `${item.number} · ${t(item.equipment_name)}` }))} />
          <label><span>{t('Фактически перелито концентрата, л')}</span><input required type="number" min="0.001" step="0.001" value={form.concentrate_liters} onChange={(event) => update('concentrate_liters', event.target.value)} /></label>
          <p>{t('Присадки пока не учитываются и не списываются со склада.')}</p>
        </>}
        {step === 'oil-tank-loading' && <Selection label="Партия масла в смесителе" value={form.batch_id} onChange={(value) => update('batch_id', value)} items={(data.blender_batches || []).map((item) => ({ id: item.id, label: `${item.number} · ${t(item.equipment_name)} · ${item.grade_name}` }))} />}
        {!config.batch && <>
          <Selection label="Продуктовый бак" value={form.tank_id} onChange={(value) => update('tank_id', value)} items={tanks.map((item) => ({ id: item.id, label: `${t(item.name)} · ${item.grade_name} · ${liters(item.current_volume_liters)}` }))} />
          <label><span>{t(step === 'oil-filling' ? 'Объём розлива, л' : 'Фактически перелито масла, л')}</span><input required type="number" min="0.001" step="0.001" max={selectedTank ? step === 'oil-filling' ? selectedTank.current_volume_liters : selectedTank.free_volume_liters : undefined} value={form.volume_liters} onChange={(event) => update('volume_liters', event.target.value)} /></label>
          {step === 'oil-filling' && <p>{t('Масло списывается из бака. Тара и складской приход фасованной продукции не учитываются.')}</p>}
        </>}
        <div className="form-actions"><button type="submit">{isSubmitting ? t('Выполняется...') : t('Подтвердить операцию')}</button><button className="secondary-button" type="button" onClick={() => { setForm(emptyOilManufacturingForms[step]); requestKey.current = null }}>{t('Очистить форму')}</button></div>
      </fieldset></form>
    </article></section>}
    <section className="access-grid"><article className="access-card"><h3>{t(config.batch ? 'Производственные партии' : 'История движений')}</h3>
      <ListControls {...controls} onPageChange={controls.setCurrentPage} onSearchChange={controls.setSearchQuery} />
      <div className="entity-list">{controls.paginatedItems.map((item) => <div className="entity-row" key={item.id}><div>
        <strong>{item.number || item.movement_number}</strong>
        {config.batch ? <>
          <span>{t(item.equipment_name)} · {item.grade_name || t('Концентрат')} · {t(item.status_label)}</span>
          <span>{t('Загружено жидких компонентов')}: {liters(item.input_liters)} · {t('Перелито по замеру')}: {liters(item.output_liters)}</span>
          {step === 'concentrate-loading' && <span>{t('Полипропилен')}: {formatNumber(item.polypropylene_quantity)} {t('кг')}</span>}
        </> : <span>{t(item.source)} → {t(item.destination)} · {item.product_name} · {liters(item.volume_liters)}</span>}
        <span>{new Date(item.created_at).toLocaleString(getLocale())} · {item.created_by}</span>
        {item.completed_at && <span>{t('Закрыта')}: {new Date(item.completed_at).toLocaleString(getLocale())}</span>}
        {item.is_compensated && <span>{t('Компенсировано')}</span>}
      </div><div className="row-actions">{config.batch && item.status === 'open' && <>
        {canCreate && Number(item.output_liters) > 0 && <button disabled={isSubmitting} type="button" onClick={() => setActionTarget({ action: 'complete', item })}>{t('Завершить партию')}</button>}
        {user?.is_admin && Number(item.output_liters) === 0 && <button disabled={isSubmitting} type="button" className="danger-button" onClick={() => { setReason(''); setActionTarget({ action: 'cancel', item }) }}>{t('Отменить партию')}</button>}
      </>}</div></div>)}{!controls.filteredCount && <p className="empty-state">{t('Записи не найдены.')}</p>}</div>
    </article></section>
    {actionTarget && <Modal title={t(actionTarget.action === 'complete' ? 'Завершить партию' : 'Отменить партию')} onClose={() => !isSubmitting && setActionTarget(null)}><form className="crud-form" onSubmit={handleAction}>
      {actionTarget.action === 'complete' ? <label className="checkbox-row"><input required type="checkbox" />{t('Оборудование полностью опорожнено. Все фактические переливы зарегистрированы.')}</label> : <label><span>{t('Причина')}</span><textarea required maxLength={1000} value={reason} onChange={(event) => setReason(event.target.value)} /></label>}
      <p>{actionTarget.item.number}</p>
      <div className="form-actions"><button type="submit" disabled={isSubmitting}>{t('Подтвердить')}</button><button type="button" className="secondary-button" disabled={isSubmitting} onClick={() => setActionTarget(null)}>{t('Отмена')}</button></div>
    </form></Modal>}
  </DashboardShell>
}
