import { formatNumber, t } from '../i18n/core'

export const reconciliationModule = 'container-reconciliation'
export const reconciliationPath = '/processing/reconciliation'
export const reconciliationApi = '/api/processing/container-reconciliations/'

export const reconciliationStages = [
  ['receiving_tank', 'Приёмные баки'],
  ['preheating_boiler', 'Котлы первичного прогрева'],
  ['processing_workshop', 'Реакторы переработки'],
  ['raw_diesel_tank', 'Баки сырой солярки'],
  ['raw_spindle_tank', 'Баки сырой веретенки'],
  ['nigrol_tank', 'Баки нигрола'],
  ['chemical_mixer', 'Химические миксеры'],
  ['finishing_mixer', 'Песочные миксеры'],
  ['finishing_filter', 'Финишные фильтры'],
  ['finished_diesel_tank', 'Баки готовой солярки'],
  ['finished_spindle_tank', 'Баки готовой веретенки'],
]

export function reconciliationLiters(value, signed = false) {
  return `${formatNumber(value, { maximumFractionDigits: 3, signDisplay: signed ? 'exceptZero' : 'auto' })} ${t('л')}`
}

export function reconciliationPercent(value, signed = false) {
  return value == null ? '—' : `${formatNumber(value, { maximumFractionDigits: 2, signDisplay: signed ? 'exceptZero' : 'auto' })}%`
}

export function reconciliationDifference(row) {
  const liters = reconciliationLiters(row.difference_liters, true)
  return row.deviation_percent == null ? liters : `${reconciliationPercent(row.deviation_percent, true)} · ${liters}`
}
