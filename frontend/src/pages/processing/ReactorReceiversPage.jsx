import { useEffect, useState } from 'react'
import { Link } from 'react-router'
import { apiRequest } from '../../api/client'
import { DashboardShell } from '../../components/Layout/DashboardShell'
import { Modal } from '../../components/Modal/Modal'
import { receiverApi, receiverModule, receiverProduct, receiverStatuses } from '../../constants/reactorReceivers'
import { workshopTankTransfers } from '../../constants/workshopTankTransfers'
import { t } from '../../i18n/core'
import { ProcessingPageHeader } from './ProcessingPages'
import { createIdempotencyKey, formatDateTime, formatVolume } from './processingFormat'
import './ReactorReceiversPage.css'

function runDuration(run) {
  if (!run.closed_at) return '—'
  const seconds = Math.floor((Date.parse(run.closed_at) - Date.parse(run.opened_at)) / 1000)
  return t`${Math.floor(seconds / 60)} мин ${seconds % 60} с`
}

export function ReactorReceiversPage({ onLogout, token, user }) {
  const [reactorId, setReactorId] = useState('')
  const [page, setPage] = useState(1)
  const [refresh, setRefresh] = useState(0)
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [decision, setDecision] = useState(null)
  const [busy, setBusy] = useState(false)
  const [decisionError, setDecisionError] = useState('')
  const canRecord = user?.is_admin || user?.access?.[receiverModule]?.includes('create')
  const reactor = !reactorId || String(data?.reactor?.id) === reactorId ? data?.reactor : null

  useEffect(() => {
    const controller = new AbortController()
    const params = new URLSearchParams({ page: String(page) })
    if (reactorId) params.set('reactor_id', reactorId)
    apiRequest(`${receiverApi}?${params}`, token, { signal: controller.signal })
      .then((result) => {
        setData(result)
        setError('')
      })
      .catch((failure) => { if (!controller.signal.aborted) setError(failure.message) })
    return () => controller.abort()
  }, [page, reactorId, refresh, token])

  function confirmAction(action, number, run) {
    setDecisionError('')
    setDecision({ action, number, reactor_id: reactor.id, loading_id: reactor.loading_id, run_id: run?.id, idempotency_key: createIdempotencyKey() })
  }

  async function submitAction(event) {
    event.preventDefault()
    if (busy) return
    setBusy(true)
    setDecisionError('')
    try {
      await apiRequest(receiverApi, token, { method: 'POST', body: JSON.stringify(decision) })
      setDecision(null)
      setPage(1)
    } catch (failure) {
      setDecisionError(failure.message)
    } finally {
      setBusy(false)
      setRefresh((previous) => previous + 1)
    }
  }

  const title = t('Ресиверы реактора')
  return (
    <DashboardShell title={title} onLogout={onLogout} user={user}>
      <ProcessingPageHeader title={title} description={t('После загрузки первым открывается №1. Затем повторяется очередь №2 → №3 → №4 до новой загрузки.')} />
      {error && <p className="access-error" role="alert">{t(error)}</p>}
      <section className="access-card receiver-control">
        <div className="panel-heading">
          <label className="receiver-picker">
            <span>{t('Реактор переработки')}</span>
            <select value={reactorId || reactor?.id || ''} onChange={(event) => { setReactorId(event.target.value); setPage(1) }}>
              {!data?.reactors.length && <option value="">{t('Нет активных реакторов переработки.')}</option>}
              {data?.reactors.map((item) => <option key={item.id} value={item.id}>{t(item.name)}</option>)}
            </select>
          </label>
          <button className="secondary-button" type="button" onClick={() => setRefresh((previous) => previous + 1)}>{t('Обновить')}</button>
        </div>
        {reactor && <>
          <div className="receiver-summary">
            <strong>{reactor.next_receiver == null ? t('Ожидается первая загрузка реактора.') : t`Следующий ресивер: №${reactor.next_receiver}`}</strong>
            <span>{t('Последний фактический замер')}: {reactor.measured_at ? `${formatVolume(reactor.measured_liters)} · ${formatDateTime(reactor.measured_at)}` : t('Нет замера')}</span>
          </div>
          <div className="receiver-grid">
            {reactor.receivers.map(({ number, run }) => {
              const status = run?.status || 'drained'
              const canOpen = canRecord && status === 'drained' && reactor.open_receiver == null && reactor.next_receiver === number
              const outlet = workshopTankTransfers.find((item) => item.kind === (number === 1 ? 'raw_diesel_tank' : 'raw_spindle_tank'))
              const outletPermissions = user?.access?.[outlet.moduleCode]
              const canDrain = user?.is_admin || (outletPermissions?.includes('view') && outletPermissions.includes('create'))
              return <article className={`receiver-card receiver-card--${status}`} key={number}>
                <strong>{t`Ресивер №${number}`}</strong>
                <span>{t(receiverProduct(number))} · {t(receiverStatuses[status])}</span>
                {run && <small>{t('Открыт')}: {formatDateTime(run.opened_at, true)}</small>}
                {run?.closed_at && <small>{t('Закрыт')}: {formatDateTime(run.closed_at, true)}</small>}
                {canOpen && <button type="button" onClick={() => confirmAction('open', number, run)}>{t('Отметить открытие')}</button>}
                {canRecord && status === 'open' && <button type="button" onClick={() => confirmAction('close', number, run)}>{t('Отметить закрытие')}</button>}
                {canDrain && status === 'waiting' && <Link className="secondary-button" to={`${outlet.path}?receiver=${run.id}`}>{t('Перейти к сливу')}</Link>}
              </article>
            })}
          </div>
        </>}
      </section>

      {reactor && <section className="access-card receiver-control">
        <h2>{t('Журнал ресиверов')}</h2>
        {!data.history.length && <p className="empty-state">{t('Открытия ресиверов пока не записаны.')}</p>}
        <ul className="receiver-history">
          {data.history.map((run) => <li key={run.id}>
            <strong>{t`Ресивер №${run.number}`} · {t(receiverStatuses[run.status])}</strong>
            <span>{t('Открыт')}: {formatDateTime(run.opened_at, true)} {run.opened_by}</span>
            {run.closed_at && <>
              <span>{t('Закрыт')}: {formatDateTime(run.closed_at, true)} {run.closed_by}</span>
              <span>{t('Длительность открытия')}: {runDuration(run)}</span>
            </>}
          </li>)}
        </ul>
        {data.page_count > 1 && <div className="form-actions">
          <button className="secondary-button" disabled={data.page <= 1} type="button" onClick={() => setPage(data.page - 1)}>{t('Назад')}</button>
          <button className="secondary-button" disabled={data.page >= data.page_count} type="button" onClick={() => setPage(data.page + 1)}>{t('Далее')}</button>
        </div>}
      </section>}

      {decision && <Modal title={t(decision.action === 'open' ? 'Подтвердить открытие ресивера?' : 'Подтвердить закрытие ресивера?')} onClose={() => { if (!busy) setDecision(null) }}>
        <form className="crud-form" onSubmit={submitAction}>
          <p>{t(reactor?.name)} · {t`Ресивер №${decision.number}`}. {t('Система запишет время подтверждения.')}</p>
          {decisionError && <p className="access-error" role="alert">{t(decisionError)}</p>}
          <div className="form-actions">
            <button disabled={busy} type="submit">{t('Подтвердить')}</button>
            <button className="secondary-button" disabled={busy} type="button" onClick={() => setDecision(null)}>{t('Отмена')}</button>
          </div>
        </form>
      </Modal>}
    </DashboardShell>
  )
}
