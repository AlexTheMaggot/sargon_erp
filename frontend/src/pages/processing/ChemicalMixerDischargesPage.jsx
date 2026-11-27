import { useEffect, useRef, useState } from 'react'
import { apiRequest } from '../../api/client'
import { DashboardShell } from '../../components/Layout/DashboardShell'
import { chemicalMixerDischarges, mixerDischargeTypes } from '../../constants/chemicalMixerDischarges'
import { formatNumber, t } from '../../i18n/core'
import { createIdempotencyKey, formatDateTime } from './processingFormat'
import './OilFinishingPage.css'

const endpoint = `/api${chemicalMixerDischarges.path}/`

export function ChemicalMixerDischargesPage({ onLogout, token, user }) {
  const [type, setType] = useState('water')
  const [mixers, setMixers] = useState(null)
  const [selectedMixerId, setSelectedMixerId] = useState('')
  const [quantity, setQuantity] = useState('')
  const [error, setError] = useState('')
  const [referenceError, setReferenceError] = useState('')
  const [saved, setSaved] = useState(null)
  const [submitting, setSubmitting] = useState(false)
  const pending = useRef(false)
  const requestKey = useRef(null)
  const options = mixers || []
  const mixerId = selectedMixerId || (options.length === 1 ? String(options[0].id) : '')
  const canCreate = user?.is_admin || user?.access?.[chemicalMixerDischarges.moduleCode]?.includes('create')
  const canSubmit = Boolean(mixerId && Number.isFinite(Number(quantity)) && Number(quantity) > 0)
  const amountLabel = `${t('Количество')}, ${t(mixerDischargeTypes[type].unit)}`
  const title = t(chemicalMixerDischarges.label)

  useEffect(() => {
    const controller = new AbortController()
    apiRequest(endpoint, token, { signal: controller.signal })
      .then((data) => { if (!controller.signal.aborted) setMixers(data.mixers) })
      .catch((failure) => { if (!controller.signal.aborted) setReferenceError(failure.message) })
    return () => controller.abort()
  }, [token])

  function clearFeedback() {
    requestKey.current = null
    setError('')
    setSaved(null)
  }

  function switchType(nextType) {
    if (type === nextType) return
    setType(nextType)
    setQuantity('')
    clearFeedback()
  }

  async function submit(event) {
    event.preventDefault()
    if (!canCreate || pending.current || !canSubmit) return
    pending.current = true
    setSubmitting(true)
    setError('')
    requestKey.current ||= createIdempotencyKey()
    try {
      const result = await apiRequest(endpoint, token, {
        method: 'POST',
        body: JSON.stringify({
          mixer_id: Number(mixerId), discharge_type: type, quantity, idempotency_key: requestKey.current,
        }),
      })
      setSaved(result)
      setQuantity('')
      requestKey.current = null
    } catch (failure) {
      setError(failure.message)
    } finally {
      pending.current = false
      setSubmitting(false)
    }
  }

  return (
    <DashboardShell title={title} onLogout={onLogout} user={user}>
      <section className="page-title access-page-title">
        <h1>{title}</h1>
        <p>{t('Выгрузка не меняет остатки масла и склада.')}</p>
      </section>
      {(referenceError || error) && <p className="access-error" role="alert">{t(referenceError || error)}</p>}
      <section className="access-grid">
        <article className="access-card">
          <div className="production-mode-options" role="group" aria-label={t('Вид выгрузки')}>
            {Object.entries(mixerDischargeTypes).map(([code, config]) => (
              <button
                key={code} type="button" className={code === type ? undefined : 'secondary-button'}
                aria-pressed={code === type} disabled={submitting} onClick={() => switchType(code)}
              >{t(config.label)}</button>
            ))}
          </div>
          {!mixers && !referenceError && <p className="empty-state">{t('Загрузка…')}</p>}
          {mixers && !options.length && <p className="empty-state">{t('Нет активных химических миксеров.')}</p>}
          {canCreate && <form className="crud-form" onSubmit={submit}>
            <fieldset className="oil-finishing-fields" disabled={submitting || !options.length}>
              <select
                aria-label={t('Химический миксер')} required value={mixerId}
                onChange={(event) => { setSelectedMixerId(event.target.value); clearFeedback() }}
              >
                <option value="">{t('Выберите химический миксер')}</option>
                {options.map((mixer) => <option key={mixer.id} value={mixer.id}>{t(mixer.name)}</option>)}
              </select>
              <input
                aria-label={amountLabel} placeholder={amountLabel}
                type="number" min="0.001" max="99999999999.999" step="0.001" required value={quantity}
                onChange={(event) => { setQuantity(event.target.value); clearFeedback() }}
              />
              <div className="form-actions">
                <button type="submit" disabled={!canSubmit}>
                  {t(submitting ? 'Выполняется...' : 'Записать выгрузку')}
                </button>
              </div>
            </fieldset>
          </form>}
          {saved && <div className="production-loading-success" role="status">
            <strong>{t('Выгрузка записана')}</strong>
            <div>{t(saved.mixer_name)} · {t(mixerDischargeTypes[saved.discharge_type].label)} · {formatNumber(saved.quantity, { maximumFractionDigits: 3 })} {t(saved.quantity_unit)} · {formatDateTime(saved.created_at)}</div>
          </div>}
        </article>
      </section>
    </DashboardShell>
  )
}
