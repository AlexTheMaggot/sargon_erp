import { useRef, useState } from 'react'
import { DashboardShell } from '../../components/Layout/DashboardShell'
import { reconciliationDifference, reconciliationLiters, reconciliationModule, reconciliationPercent, reconciliationStages } from '../../constants/containerReconciliation'
import { useContainerReconciliation } from '../../hooks/useContainerReconciliation'
import { getLocale, t } from '../../i18n/core'
import './ContainerReconciliationPage.css'

function dateTime(value) {
  return new Date(value).toLocaleString(getLocale(), { dateStyle: 'short', timeStyle: 'short' })
}

function ReconciliationHistory({ detail }) {
  const { summary, latest_revision: latest } = detail
  return <div className="reconciliation-history">
    <p>{t`Сверено ${summary.measured_count} из ${latest.eligible_count} ёмкостей`}</p>
    <p>{t('Балансовое отклонение')}: <strong>{reconciliationDifference(summary)}</strong></p>
    <p>{t('Суммарное расхождение')}: <strong>{reconciliationPercent(summary.absolute_deviation_percent)} · {reconciliationLiters(summary.absolute_difference_liters)}</strong></p>
    {detail.revisions.map((revision) => <details className="reconciliation-revision" key={revision.id}>
      <summary>{t`Версия ${revision.number}`} · {dateTime(revision.created_at)} · {revision.operator}</summary>
      <ul>
        {revision.measurements.map((row) => <li key={row.container_id}>
          <strong>{t(row.name)}</strong>
          <span>{t('По учёту')}: {reconciliationLiters(row.expected_liters)} · {t('Фактически')}: {reconciliationLiters(row.actual_liters)} · {reconciliationDifference(row)}</span>
        </li>)}
      </ul>
    </details>)}
  </div>
}

export function ContainerReconciliationPage({ onLogout, token, user }) {
  const [page, setPage] = useState(1)
  const [references, setReferences] = useState(null)
  const [drafts, setDrafts] = useState({})
  const [editor, setEditor] = useState(null)
  const [detail, setDetail] = useState(null)
  const [busy, setBusy] = useState(false)
  const [saved, setSaved] = useState(false)
  const pending = useRef(false)
  const { listing, error, setError, loadListing, loadDetail, save } = useContainerReconciliation(token, page)
  const access = user?.access?.[reconciliationModule]
  const canCreate = user?.is_admin || access?.includes('create')
  const canUpdate = user?.is_admin || access?.includes('update')
  const canEdit = editor ? canUpdate : canCreate
  const containers = references ?? listing?.containers ?? []
  const previous = new Map(editor?.measurements.map((row) => [row.container_id, row]))
  const enteredCount = containers.filter((container) => drafts[container.id]?.actual_liters?.trim()).length

  async function run(action) {
    if (pending.current) return
    pending.current = true
    setBusy(true)
    setError('')
    setSaved(false)
    try {
      await action()
    } catch (requestError) {
      setError(requestError.message)
    } finally {
      setBusy(false)
      pending.current = false
    }
  }

  function update(container, field, value) {
    setReferences((current) => current ?? containers)
    setDrafts((current) => ({
      ...current, [container.id]: { ...current[container.id], [field]: value },
    }))
    setSaved(false)
  }

  function startEditor(walk) {
    return run(async () => {
      const [result, nextEditor] = await Promise.all([loadListing(), walk ? loadDetail(walk.id) : null])
      setEditor(nextEditor)
      setReferences(result.containers)
      setDrafts({})
      if (nextEditor) {
        setDetail(nextEditor)
        window.scrollTo({ top: 0 })
      }
    })
  }

  function refreshEditor() {
    return run(async () => {
      const [result, nextEditor] = await Promise.all([loadListing(), editor ? loadDetail(editor.id) : null])
      const latestMeasurements = new Map(nextEditor?.measurements.map((row) => [row.container_id, row]))
      const activeIds = new Set(result.containers.map((container) => container.id))
      setDrafts((current) => Object.fromEntries(Object.entries(current).filter(([id]) => (
        activeIds.has(Number(id)) && latestMeasurements.get(Number(id))?.can_correct !== false
      ))))
      setReferences(result.containers)
      setEditor(nextEditor)
      if (nextEditor) setDetail(nextEditor)
    })
  }

  function handleSubmit(event) {
    event.preventDefault()
    if (!canEdit || !enteredCount) return
    return run(async () => {
      const measurements = containers.filter((container) => drafts[container.id]?.actual_liters?.trim()).map((container) => ({
        container_id: container.id, version: container.version, ...drafts[container.id],
      }))
      const result = await save({
        reconciliation_id: editor?.id ?? null,
        base_revision_id: editor?.latest_revision.id ?? null,
        measurements,
      })
      setDetail(result)
      setEditor(null)
      setDrafts({})
      setReferences([])
      setSaved(true)
      const nextListing = await loadListing(1)
      setPage(1)
      setReferences(nextListing.containers)
      document.getElementById('reconciliation-history')?.scrollIntoView()
    })
  }

  return <DashboardShell title={t('Сверка остатков')} onLogout={onLogout} user={user}>
    <section className="page-title access-page-title">
      <p className="auth-eyebrow">{t('Переработка отработанного масла')}</p>
      <h1>{t('Сверка остатков')}</h1>
      <p>{t('Вводите замеры после оформления движений. Пустое поле пропускает ёмкость, ноль обнуляет остаток.')}</p>
      {canEdit && <a className="reconciliation-history-link" href="#reconciliation-history" onClick={(event) => {
        event.preventDefault()
        document.getElementById('reconciliation-history')?.scrollIntoView()
      }}>{t('История сверок')} ↓</a>}
    </section>
    {error && <p className="access-error reconciliation-message" role="alert">{t(error)}</p>}
    {saved && <p className="reconciliation-message reconciliation-success" role="status">{t('Сверка сохранена. Остатки обновлены.')}</p>}
    <div className="reconciliation-page">
      {canEdit && <article className="access-card">
        <div className="reconciliation-heading">
          <div><h2>{editor ? t('Новая версия сверки') : t('Новая сверка')}</h2>
            {editor && <p>{dateTime(editor.created_at)} · {t`Версия ${editor.latest_revision.number + 1}`}</p>}
          </div>
          <button className="secondary-button" disabled={busy} onClick={refreshEditor} type="button">{t('Обновить расчётные остатки')}</button>
        </div>
        <form onSubmit={handleSubmit}>
          <fieldset className="reconciliation-fields" disabled={busy}>
            {reconciliationStages.map(([kind, label]) => {
              const equipment = containers.filter((container) => container.kind === kind)
              if (!equipment.length) return null
              return <section className="reconciliation-stage" key={kind}>
                <h3>{t(label)}</h3>
                {equipment.map((container) => {
                  const draft = drafts[container.id] || {}
                  const last = previous.get(container.id)
                  const canCorrect = !last || last.can_correct
                  const showProduct = container.shared && (!container.oil_product || last?.expected_liters === '0.000') && Number(draft.actual_liters) > 0
                  return <div className="reconciliation-row" key={container.id}>
                    <div>
                      <strong>{t(container.name)}</strong>
                      <small>{t('По учёту')}: {reconciliationLiters(container.current_liters)} · {t('Вместимость')}: {reconciliationLiters(container.capacity_liters)}</small>
                      {last && <small>{t('Сохранённый замер')}: {reconciliationLiters(last.actual_liters)} · {reconciliationDifference(last)}</small>}
                      {!canCorrect && <small>{t('Этот замер уже нельзя исправить. Для нового замера начните новую сверку.')}</small>}
                    </div>
                    <div className="reconciliation-inputs">
                      <label>
                        <span>{t('Фактический остаток, л')}</span>
                        <input aria-label={t`Фактический остаток, л: ${t(container.name)}`} type="number" min="0" max={container.capacity_liters} step="0.001" inputMode="decimal" placeholder="—" disabled={!canCorrect} value={draft.actual_liters ?? ''} onChange={(event) => update(container, 'actual_liters', event.target.value)} />
                      </label>
                      {showProduct && <label>
                        <span>{t('Продукт')}</span>
                        <select required value={draft.oil_product ?? container.oil_product} onChange={(event) => update(container, 'oil_product', event.target.value)}>
                          <option value="">{t('Выберите продукт')}</option>
                          <option value="diesel">{t('Солярка')}</option>
                          <option value="spindle">{t('Веретенка')}</option>
                        </select>
                      </label>}
                    </div>
                  </div>
                })}
              </section>
            })}
            {!containers.length && <p className="empty-state">{listing ? t('Нет активных ёмкостей') : t('Загрузка...')}</p>}
            <div className="form-actions">
              <button type="submit" disabled={!enteredCount}>{editor ? t('Сохранить новую версию') : t('Сохранить сверку')}</button>
              {editor && <button className="secondary-button" type="button" onClick={() => startEditor(null)}>{t('Выйти из редактирования')}</button>}
              <span>{t`Заполнено: ${enteredCount}`}</span>
            </div>
          </fieldset>
        </form>
      </article>}
      <article className="access-card" id="reconciliation-history">
        <h2>{t('История сверок')}</h2>
        {listing?.items.map((walk) => <div className="reconciliation-history-item" key={walk.id}>
          <div className="reconciliation-heading">
            <strong>{dateTime(walk.created_at)}</strong>
            <button className="secondary-button" type="button" aria-expanded={detail?.id === walk.id} disabled={busy} onClick={() => detail?.id === walk.id ? setDetail(null) : run(async () => setDetail(await loadDetail(walk.id)))}>
              {detail?.id === walk.id ? t('Скрыть') : t('Показать сверку')}
            </button>
          </div>
          {detail?.id === walk.id && <>
            <ReconciliationHistory detail={detail} />
            {canUpdate && <button className="secondary-button" type="button" disabled={busy} onClick={() => startEditor(walk)}>{t('Исправить или дополнить сверку')}</button>}
          </>}
        </div>)}
        {listing && !listing.items.length && <p className="empty-state">{t('Сверок ещё не было.')}</p>}
        {listing?.page_count > 1 && <div className="pagination-actions">
          <button className="secondary-button" type="button" disabled={busy || listing.page <= 1} onClick={() => setPage(listing.page - 1)}>{t('Назад')}</button>
          <span>{listing.page} / {listing.page_count}</span>
          <button className="secondary-button" type="button" disabled={busy || listing.page >= listing.page_count} onClick={() => setPage(listing.page + 1)}>{t('Вперёд')}</button>
        </div>}
      </article>
    </div>
  </DashboardShell>
}
