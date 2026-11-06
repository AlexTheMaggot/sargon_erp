import { useRef, useState } from 'react'
import { DashboardShell } from '../../components/Layout/DashboardShell'
import { ListControls } from '../../components/ListControls/ListControls'
import { Modal } from '../../components/Modal/Modal'
import { emptySorbentCycleForm } from '../../constants/forms'
import { useListControls } from '../../hooks/useListControls'
import { useSorbentCycle } from '../../hooks/useSorbentCycle'
import { formatNumber, getLocale, t } from '../../i18n/core'
import './OilFinishingPage.css'
import './SorbentCyclePage.css'

const steps = {
  tank_to_system: 'Подача сорбента из бака',
  system_to_regeneration: 'Передача сорбента на прогрев и очистку',
  regeneration_to_tank: 'Возврат очищенного сорбента в бак',
}

const requestId = () => globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}`
const kilograms = (value) => value == null ? '—' : `${formatNumber(value, { maximumFractionDigits: 2 })} ${t('кг')}`

export function SorbentCyclePage({ onLogout, token, user }) {
  const { data, error, isSubmitting, submit, reverse } = useSorbentCycle(token)
  const [form, setForm] = useState(emptySorbentCycleForm)
  const [success, setSuccess] = useState('')
  const [cancelTarget, setCancelTarget] = useState(null)
  const [reason, setReason] = useState('')
  const requestKey = useRef(null)
  const reversalKey = useRef(null)
  const canCreate = user?.is_admin || user?.access?.['sorbent-cycle']?.includes('create')
  const systems = (data?.systems || []).filter((item) => form.movement_type !== 'tank_to_system' || item.is_active)
  const available = (source) => {
    if (form.movement_type === 'tank_to_system') return Number(source.tank_quantity)
    const balance = source.systems.find((item) => item.id === Number(form.system_id))
    return Number(balance?.[form.movement_type === 'system_to_regeneration' ? 'system_quantity' : 'regeneration_quantity'] || 0)
  }
  const sources = (data?.sources || []).filter((source) => available(source) > 0)
  const selectedSource = sources.find((source) => source.id === Number(form.source_movement_id))
  const controls = useListControls(data?.items || [], (item) => [item.number, t(item.movement_label), item.item_name, t(item.system_name), item.loading_number, item.note, item.created_by].join(' '))

  function update(field, value) {
    requestKey.current = null
    setSuccess('')
    setForm((current) => ({ ...current, [field]: value,
      ...(['movement_type', 'system_id'].includes(field) ? { source_movement_id: '', quantity: '' } : {}),
    }))
  }

  async function handleSubmit(event) {
    event.preventDefault()
    requestKey.current ||= requestId()
    const result = await submit({ ...form, source_movement_id: Number(form.source_movement_id), system_id: Number(form.system_id), idempotency_key: requestKey.current })
    if (result) {
      setSuccess('Движение сорбента сохранено. Складской остаток не изменился.')
      setForm((current) => ({ ...emptySorbentCycleForm, movement_type: current.movement_type, system_id: current.system_id }))
      requestKey.current = null
    }
  }

  return <DashboardShell title={t('Циркуляция сорбента')} onLogout={onLogout} user={user}>
    <section className="page-title access-page-title">
      <p className="auth-eyebrow">{t('Переработка')}</p><h1>{t('Циркуляция сорбента')}</h1>
      <p>{t('Бак → сорбент-система → прогрев и очистка → бак. Новый сорбент поступает из складской загрузки; внутренние движения не списывают склад повторно.')}</p>
    </section>
    {error && <p className="access-error" role="alert">{t(error)}</p>}
    {success && <p className="oil-manufacturing-success sorbent-cycle-success" role="status">{t(success)}</p>}
    <section className="warehouse-summary-grid sorbent-summary-grid">
      {[[t('В баке сорбента'), 'tank_kg'], [t('В сорбент-системах'), 'in_system_kg'], [t('На прогреве и очистке'), 'regeneration_kg'], [t('Всего в контуре'), 'total_kg']].map(([label, field]) => <article key={field}><span>{label}</span><strong>{kilograms(data?.summary?.[field])}</strong></article>)}
    </section>
    {canCreate && <section className="access-grid"><article className="access-card">
      <h3>{t('Новое движение сорбента')}</h3>
      <form className="crud-form" onSubmit={handleSubmit}><fieldset className="oil-finishing-fields" disabled={isSubmitting || !data}>
        <label><span>{t('Этап движения')}</span><select value={form.movement_type} onChange={(event) => update('movement_type', event.target.value)}>
          {Object.entries(steps).map(([code, label]) => <option key={code} value={code}>{t(label)}</option>)}
        </select></label>
        <label><span>{t('Сорбент-система')}</span><select required value={form.system_id} onChange={(event) => update('system_id', event.target.value)}>
          <option value="">{t('Выберите значение')}</option>
          {systems.map((item) => <option key={item.id} value={item.id}>{t(item.name)}</option>)}
        </select></label>
        <label><span>{t('Источник сорбента')}</span><select required value={form.source_movement_id} onChange={(event) => update('source_movement_id', event.target.value)}>
          <option value="">{t('Выберите значение')}</option>
          {sources.map((source) => <option key={source.id} value={source.id}>{source.item_name} · {source.loading_number} · {kilograms(available(source))}</option>)}
        </select></label>
        {selectedSource && <p>{t('Доступно: ')}{kilograms(available(selectedSource))}</p>}
        {data && !sources.length && <p className="empty-state">{t('Нет доступного сорбента для выбранного этапа. Проверьте систему и предыдущие движения.')}</p>}
        <label><span>{t('Количество сорбента, кг')}</span><input required type="number" value={form.quantity} min={10 ** -(selectedSource?.decimal_places ?? 2)} step={10 ** -(selectedSource?.decimal_places ?? 2)} max={selectedSource ? available(selectedSource) : undefined} onChange={(event) => update('quantity', event.target.value)} /></label>
        <label><span>{t('Комментарий')}</span><textarea maxLength={1000} value={form.note} onChange={(event) => update('note', event.target.value)} /></label>
        <div className="form-actions"><button type="submit" disabled={isSubmitting || !selectedSource}>{t('Сохранить движение')}</button></div>
      </fieldset></form>
    </article></section>}
    <section className="access-grid"><article className="access-card">
      <h3>{t('История циркуляции')}</h3>
      <ListControls {...controls} onPageChange={controls.setCurrentPage} onSearchChange={controls.setSearchQuery} />
      <div className="entity-list">
        {controls.paginatedItems.map((item) => <div className="entity-row" key={item.id}><div>
          <strong>{item.number} · {t(item.movement_label)}</strong>
          <span>{item.item_name} · {kilograms(item.quantity)} · {t(item.system_name)}</span>
          <span>{t('Складская загрузка')}: {item.loading_number}</span>
          <span>{new Date(item.created_at).toLocaleString(getLocale())} · {item.created_by}</span>
          {item.note && <span>{item.note}</span>}
          {item.is_reversed && <span className="status-pill rejected">{t('Компенсировано')}</span>}
        </div>{user?.is_admin && !item.is_reversed && !item.reversal_of_id && <button className="danger-button" type="button" disabled={isSubmitting} onClick={() => { setCancelTarget(item); setReason(''); reversalKey.current = null }}>{t('Компенсировать')}</button>}</div>)}
        {!controls.filteredCount && <p className="empty-state">{t('Движений сорбента пока нет.')}</p>}
      </div>
    </article></section>
    {cancelTarget && <Modal title={t('Компенсировать движение сорбента')} onClose={() => { if (!isSubmitting) setCancelTarget(null) }}>
      {error && <p className="access-error" role="alert">{t(error)}</p>}
      <p>{cancelTarget.number} · {kilograms(cancelTarget.quantity)}</p>
      <p>{t('Будет создано обратное движение внутри контура. Складской остаток не изменится.')}</p>
      <form className="crud-form" onSubmit={async (event) => {
        event.preventDefault()
        reversalKey.current ||= requestId()
        if (await reverse(cancelTarget.id, { reason, idempotency_key: reversalKey.current })) setCancelTarget(null)
      }}><label><span>{t('Причина отмены')}</span><textarea required maxLength={1000} disabled={isSubmitting} value={reason} onChange={(event) => { setReason(event.target.value); reversalKey.current = null }} /></label>
        <div className="form-actions"><button className="danger-button" type="submit" disabled={isSubmitting || !reason.trim()}>{t('Подтвердить отмену')}</button></div>
      </form>
    </Modal>}
  </DashboardShell>
}
