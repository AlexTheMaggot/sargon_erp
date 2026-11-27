import { t } from './core.js'
import { auditFields } from './systemMessages.js'

const systemValueFields = new Set(['entry_type', 'action', 'object_type', 'result', 'movement_type', 'movement_type_label', 'status', 'status_label', 'source', 'destination', 'product_name', 'receipt_snapshot', 'batch_snapshot', 'kind', 'quantity_unit', 'reactor', 'mixer', 'discharge_kind', 'via_filter'])

export function localizeAuditEntry(entry, isContainerSnapshot = false) {
  return Object.fromEntries(Object.entries(entry).map(([key, value]) => {
    const label = auditFields[key] ? t(auditFields[key][0]) : key
    const localized = value && typeof value === 'object' && !Array.isArray(value)
      ? localizeAuditEntry(value, key === 'changes' && entry.action === 'container_deleted')
      : typeof value === 'boolean' ? t(value ? 'Да' : 'Нет')
        : systemValueFields.has(key) || (isContainerSnapshot && key === 'name') ? t(value) : value
    return [label, localized]
  }))
}
