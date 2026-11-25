import { getLocale, t } from '../../i18n/core'

export function formatDateTime(value, includeSeconds = false) {
  if (!value) {
    return '—'
  }
  return new Intl.DateTimeFormat(getLocale(), {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    ...(includeSeconds ? { second: '2-digit' } : {}),
  }).format(new Date(value))
}

export function formatVolume(value) {
  if (value === '' || value === null || value === undefined) {
    return '—'
  }
  return t`${Number(value).toLocaleString(getLocale(), { minimumFractionDigits: 3, maximumFractionDigits: 3 })} л`
}

export function createIdempotencyKey() {
  return globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}`
}

export function formatReceiver(run) {
  return `${t(run.reactor_name)} · ${t`Ресивер №${run.number}`}`
}
