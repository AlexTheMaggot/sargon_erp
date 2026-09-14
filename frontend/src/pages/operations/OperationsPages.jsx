import { useCallback, useEffect, useRef, useState } from 'react'
import { DashboardShell } from '../../components/Layout/DashboardShell'
import { ListControls } from '../../components/ListControls/ListControls'
import { DeleteConfirmModal, Modal as OperationsModal } from '../../components/Modal/Modal'
import { emptyLaboratoryAnalysisForm, emptyReceiptForm } from '../../constants/forms'
import { useListControls } from '../../hooks/useListControls'
import { useOperationsCrud } from '../../hooks/useOperationsCrud'
import notificationSound from '../../assets/notification.mp3'

const unitLabels = {
  liters: 'литры',
  kilograms: 'килограммы',
}

const analysisFilterOptions = [
  { value: 'pending', label: 'Ждут решения' },
  { value: 'approved', label: 'Только одобренные' },
  { value: 'rejected', label: 'Только отказанные' },
  { value: 'all', label: 'Все записи' },
]

const BASE_DENSITY_MIN = 0.850
const BASE_DENSITY_MAX = 0.905
const BASE_DENSITY_TEMPERATURE = 20
const DENSITY_TEMPERATURE_CORRECTION = 0.00065

function OperationsPageHeader({ description, title }) {
  return (
    <section className="page-title access-page-title">
      <p className="auth-eyebrow">Производство</p>
      <h1>{title}</h1>
      <p>{description}</p>
    </section>
  )
}

function receiptLabel(receipt) {
  return `#${receipt.id} · ${receipt.supplier?.company_name || 'Поставщик не указан'}`
}

function receiptStatusLabel(receipt) {
  if (receipt.is_completed) {
    return 'Прием завершен'
  }
  if (receipt.has_pending_batches) {
    return 'Есть партии, ожидающие решения'
  }
  if (receipt.has_rejected_batches) {
    return 'Есть отклоненные партии'
  }
  if (receipt.approved_batch_count) {
    return 'Все партии обработаны'
  }
  return 'Ожидает партий'
}

function batchStatusLabel(batch) {
  if (batch.is_analysis_rejected) {
    return 'Анализ отклонен'
  }
  if (batch.is_analysis_approved) {
    return 'Анализ одобрен'
  }
  if (batch.is_analysis_filled) {
    return 'Заполнен, ожидает решения'
  }
  return 'Ожидает анализа'
}

function normalizeSearchText(value) {
  return String(value ?? '').toLowerCase().trim()
}

function supplierSearchText(supplier) {
  return [
    supplier.company_name,
    supplier.city?.name,
    supplier.address,
    supplier.phone,
  ].join(' ')
}

function supplierOptionLabel(supplier) {
  const cityName = supplier.city?.name || 'город не указан'
  return `${supplier.company_name} · ${cityName}`
}

function SearchableSupplierSelect({ disabled, onChange, suppliers, value }) {
  const [searchQuery, setSearchQuery] = useState('')
  const normalizedQuery = normalizeSearchText(searchQuery)
  const selectedSupplier = suppliers.find((supplier) => String(supplier.id) === String(value))
  const filteredSuppliers = suppliers
    .filter((supplier) => normalizeSearchText(supplierSearchText(supplier)).includes(normalizedQuery))
    .slice(0, 5)

  function handleSupplierSelect(supplier) {
    onChange(supplier.id)
    setSearchQuery(supplier.company_name)
  }

  return (
    <div className="searchable-select">
      <label>
        <span>Поставщик</span>
        <input
          disabled={disabled}
          placeholder="Слепой поиск по поставщику, городу, адресу или телефону"
          type="search"
          value={searchQuery}
          onChange={(event) => setSearchQuery(event.target.value)}
        />
      </label>
      {selectedSupplier && <p className="selected-supplier">Выбран: {supplierOptionLabel(selectedSupplier)}</p>}
      {!disabled && !selectedSupplier && <p className="select-hint">Выберите поставщика из результатов поиска.</p>}
      {!disabled && normalizedQuery.length >= 3 && (
        <div className="supplier-results">
          {filteredSuppliers.map((supplier) => (
            <button key={supplier.id} type="button" onClick={() => handleSupplierSelect(supplier)}>
              <strong>{supplier.company_name}</strong>
              <span>{supplier.city?.name || 'Город не указан'} · {supplier.address || 'Адрес не указан'} · {supplier.phone || 'Телефон не указан'}</span>
            </button>
          ))}
          {!filteredSuppliers.length && <p className="select-hint">Поставщики не найдены.</p>}
        </div>
      )}
      {!disabled && normalizedQuery.length > 0 && normalizedQuery.length < 3 && <p className="select-hint">Введите минимум 3 символа для поиска.</p>}
    </div>
  )
}

function SelectedSupplierCard({ supplier }) {
  if (!supplier) {
    return <p className="empty-state">Поставщик не найден.</p>
  }

  return (
    <div className="selected-supplier-card">
      <span>Поставщик</span>
      <strong>{supplier.company_name}</strong>
      <p>{supplier.city?.name || 'Город не указан'} · {supplier.address || 'Адрес не указан'} · {supplier.phone || 'Телефон не указан'}</p>
    </div>
  )
}

function isAdminUser(user) {
  return Boolean(user?.is_admin)
}

function canManageReceipt(item, user) {
  return isAdminUser(user) || !item.is_completed
}

function canManageBatch(batch, receipt, user) {
  if (batch.is_distributed) {
    return false
  }
  return isAdminUser(user) || !(receipt.is_completed || batch.is_locked || batch.is_analysis_rejected)
}

function canManageAnalysis(item) {
  return !(item.is_approved || item.is_rejected)
}

function hasPositiveQuantity(value) {
  return Number(value) > 0
}

function hasCompleteDistribution(receipt, distributions) {
  const pendingBatches = receipt.batches.filter((batch) => batch.is_analysis_approved && !batch.is_distributed)
  if (!pendingBatches.length) {
    return false
  }

  return pendingBatches.every((batch) => {
    const rows = distributions[batch.id] || []
    if (!rows.length || rows.some((row) => !row.tank_id || !hasPositiveQuantity(row.volume_liters))) {
      return false
    }

    const distributedVolume = rows.reduce((total, row) => total + Number(row.volume_liters), 0)
    return Math.abs(distributedVolume - Number(batch.quantity_liters)) < 0.0005
  })
}

function validateLaboratoryApproval(form) {
  const fieldValues = [
    form.density,
    form.flash_point_temperature,
    form.current_temperature,
    form.water_percentage,
  ]
  if (fieldValues.some((value) => value === '' || !Number.isFinite(Number(value)))) {
    return 'Заполните все показатели корректными числовыми значениями.'
  }
  if (Number(form.density) <= 0) {
    return 'Плотность должна быть больше нуля.'
  }
  if (Number(form.water_percentage) < 0 || Number(form.water_percentage) > 100) {
    return 'Количество воды должно быть в диапазоне от 0 до 100%.'
  }
  return ''
}

function filterAnalysesByDecision(analyses, filterValue) {
  if (filterValue === 'approved') {
    return analyses.filter((item) => item.is_approved)
  }
  if (filterValue === 'rejected') {
    return analyses.filter((item) => item.is_rejected)
  }
  if (filterValue === 'pending') {
    return analyses.filter((item) => !item.is_approved && !item.is_rejected)
  }
  return analyses
}

function analysisRowClassName(item) {
  if (item.is_approved) {
    return 'entity-row supplier-row analysis-row approved'
  }
  if (item.is_rejected) {
    return 'entity-row supplier-row analysis-row rejected'
  }
  return 'entity-row supplier-row analysis-row'
}

function parseNumericValue(value) {
  if (value === null || value === undefined || value === '') {
    return null
  }

  const numericValue = Number(value)
  return Number.isFinite(numericValue) ? numericValue : null
}

function formatDensity(value) {
  return value.toFixed(3)
}

function formatDateTime(value) {
  if (!value) {
    return '—'
  }

  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return '—'
  }

  return new Intl.DateTimeFormat('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
}

function calculateDensityRange(temperature) {
  const temperatureDifference = temperature - BASE_DENSITY_TEMPERATURE
  const correction = DENSITY_TEMPERATURE_CORRECTION * temperatureDifference

  return {
    min: BASE_DENSITY_MIN - correction,
    max: BASE_DENSITY_MAX - correction,
  }
}

function getDensityCheck(densityValue, temperatureValue) {
  const density = parseNumericValue(densityValue)
  const temperature = parseNumericValue(temperatureValue)

  if (temperature === null) {
    return {
      tone: 'neutral',
      message: 'Введите текущую температуру, чтобы проверить плотность по температурной поправке.',
    }
  }

  const range = calculateDensityRange(temperature)
  const rangeText = `${formatDensity(range.min)}–${formatDensity(range.max)} г/см³`

  if (density === null) {
    return {
      tone: 'neutral',
      message: `Рекомендуемый диапазон при ${temperature}°C: ${rangeText}.`,
    }
  }

  if (density < range.min || density > range.max) {
    return {
      tone: 'warning',
      message: `Плотность вне рекомендуемого диапазона при ${temperature}°C: ${rangeText}.`,
    }
  }

  return {
    tone: 'success',
    message: `Плотность в рекомендуемом диапазоне при ${temperature}°C: ${rangeText}.`,
  }
}

function DensityCheckNotice({ density, temperature }) {
  const densityCheck = getDensityCheck(density, temperature)

  return (
    <p className={`density-check ${densityCheck.tone}`}>
      {densityCheck.message}
    </p>
  )
}

export function RawMaterialReceiptsPage({ onLogout, token, user }) {
  const { addReceiptBatch, completeReceipt, deleteReceipt, deleteReceiptBatch, error, receipts, receivingTanks, saveReceipt, saveReceiptBatch, suppliers } = useOperationsCrud(token)
  const receiptControls = useListControls(receipts, (item) => [
    item.id,
    item.supplier?.company_name,
    item.supplier?.city?.name,
    item.quantity_liters,
    item.batches?.map((batch) => `${batch.sequence_number} ${batch.input_quantity} ${batch.quantity_liters}`).join(' '),
  ].join(' '))
  const [receiptForm, setReceiptForm] = useState(emptyReceiptForm)
  const [isFormOpen, setIsFormOpen] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState(null)
  const [distributions, setDistributions] = useState({})
  const [formError, setFormError] = useState('')
  const selectedReceiptSupplier = suppliers.find((supplier) => String(supplier.id) === String(receiptForm.supplier_id))
  const isDistributionComplete = hasCompleteDistribution(receiptForm, distributions)

  function openCreateModal() {
    setReceiptForm(emptyReceiptForm)
    setDistributions({})
    setFormError('')
    setIsFormOpen(true)
  }

  function openEditModal(item) {
    setReceiptForm({
      id: item.id,
      supplier_id: item.supplier_id || '',
      input_quantity: item.input_quantity,
      input_unit: item.input_unit,
      can_set_quantity: item.can_set_quantity,
      can_complete: item.can_complete,
      is_completed: item.is_completed,
      is_locked: item.is_locked,
      is_existing: true,
      batches: item.batches || [],
    })
    setDistributions(Object.fromEntries(
      (item.batches || [])
        .filter((batch) => batch.is_analysis_approved && !batch.is_distributed)
        .map((batch) => [batch.id, [{ tank_id: '', volume_liters: '' }]]),
    ))
    setFormError('')
    setIsFormOpen(true)
  }

  async function handleReceiptSubmit(event) {
    if (!receiptForm.supplier_id) {
      event.preventDefault()
      setFormError('Выберите поставщика из результатов поиска.')
      return
    }
    const isSaved = await saveReceipt(event, receiptForm, () => setReceiptForm(emptyReceiptForm))
    if (isSaved) {
      setIsFormOpen(false)
    }
  }

  async function handleReceiptDelete() {
    const isDeleted = await deleteReceipt(deleteTarget.id)
    if (isDeleted) {
      setDeleteTarget(null)
    }
  }

  async function handleReceiptCompleteFromModal() {
    if (!receiptForm.id) {
      return
    }
    if (!isDistributionComplete) {
      setFormError('Полностью распределите объём каждой партии по приёмным бакам.')
      return
    }
    setFormError('')
    const distributionPayload = Object.entries(distributions).flatMap(([batchId, rows]) => rows
      .filter((row) => row.tank_id && row.volume_liters)
      .map((row) => ({
        batch_id: Number(batchId),
        tank_id: Number(row.tank_id),
        volume_liters: row.volume_liters,
      })))
    const isCompleted = await completeReceipt(receiptForm.id, distributionPayload)
    if (isCompleted) {
      setIsFormOpen(false)
    }
  }

  function updateDistribution(batchId, rowIndex, updates) {
    setDistributions((current) => ({
      ...current,
      [batchId]: current[batchId].map((row, index) => (index === rowIndex ? { ...row, ...updates } : row)),
    }))
  }

  function addDistribution(batchId) {
    setDistributions((current) => ({
      ...current,
      [batchId]: [...(current[batchId] || []), { tank_id: '', volume_liters: '' }],
    }))
  }

  function removeDistribution(batchId, rowIndex) {
    setDistributions((current) => ({
      ...current,
      [batchId]: current[batchId].filter((_, index) => index !== rowIndex),
    }))
  }

  async function handleAddBatch() {
    const createdBatch = await addReceiptBatch(receiptForm.id)
    if (createdBatch?.id) {
      setReceiptForm((currentForm) => ({
        ...currentForm,
        batches: [...currentForm.batches, createdBatch],
      }))
    }
  }

  function updateBatchForm(batchId, updates) {
    setReceiptForm((currentForm) => ({
      ...currentForm,
      batches: currentForm.batches.map((batch) => (batch.id === batchId ? { ...batch, ...updates } : batch)),
    }))
  }

  async function handleBatchSave(batch) {
    const updatedBatch = await saveReceiptBatch(batch)
    if (updatedBatch?.id) {
      setReceiptForm((currentForm) => ({
        ...currentForm,
        batches: currentForm.batches.map((item) => (item.id === updatedBatch.id ? updatedBatch : item)),
      }))
    }
  }

  async function handleBatchDelete(batch) {
    const isDeleted = await deleteReceiptBatch(batch.id)
    if (isDeleted) {
      setReceiptForm((currentForm) => ({
        ...currentForm,
        batches: currentForm.batches.filter((item) => item.id !== batch.id),
      }))
    }
  }

  return (
    <DashboardShell title="Прием сырья" onLogout={onLogout} user={user}>
      <OperationsPageHeader
        title="Прием сырья"
        description="Регистрация поступления сырья от поставщиков. Количество хранится в литрах; килограммы пересчитываются по плотности лабораторного анализа."
      />

      {error && <p className="access-error">{error}</p>}

      <section className="access-grid">
        <article className="access-card">
          <div className="panel-heading">
            <div>
              <p className="auth-eyebrow">Прием</p>
              <h3>Поступления сырья</h3>
            </div>
            <button type="button" onClick={openCreateModal}>Создать</button>
          </div>

          <ListControls
            currentPage={receiptControls.currentPage}
            filteredCount={receiptControls.filteredCount}
            onPageChange={receiptControls.setCurrentPage}
            onSearchChange={receiptControls.setSearchQuery}
            pageCount={receiptControls.pageCount}
            searchQuery={receiptControls.searchQuery}
            totalCount={receiptControls.totalCount}
          />

          <div className="entity-list">
            {receiptControls.paginatedItems.map((item) => (
              <div className={`entity-row supplier-row ${item.is_completed && !isAdminUser(user) ? 'disabled-row' : ''}`} key={item.id}>
                <div>
                  <strong>{receiptLabel(item)}</strong>
                  <span>
                    Партии: {item.batch_count || 0} · Одобрено: {item.approved_batch_count || 0} · Отказано: {item.rejected_batch_count || 0} · Ожидает: {item.pending_batch_count || 0}
                  </span>
                  <span>{item.supplier?.city?.name || 'Город не указан'} · В литрах: {item.quantity_liters || '—'} · {receiptStatusLabel(item)}</span>
                  <span>Создано: {formatDateTime(item.created_at)} · Завершено: {formatDateTime(item.completed_at)}</span>
                </div>
                <div className="row-actions">
                  <button disabled={!canManageReceipt(item, user)} type="button" onClick={() => openEditModal(item)}>Изменить</button>
                  <button className="danger-button" disabled={!canManageReceipt(item, user)} type="button" onClick={() => setDeleteTarget(item)}>Удалить</button>
                </div>
              </div>
            ))}
            {!receipts.length && <p className="empty-state">Поступлений пока нет. Добавьте первую запись приема.</p>}
            {Boolean(receipts.length) && !receiptControls.filteredCount && <p className="empty-state">По вашему запросу ничего не найдено.</p>}
          </div>
        </article>
      </section>

      {isFormOpen && (
        <OperationsModal title={receiptForm.id ? 'Редактировать прием' : 'Новый прием сырья'} onClose={() => setIsFormOpen(false)}>
          <form className="crud-form" onSubmit={handleReceiptSubmit}>
            {formError && <p className="form-error" role="alert">{formError}</p>}
            {receiptForm.is_locked && <p className="access-error">Запись заблокирована: лабораторный анализ заполнен, но ещё не одобрен.</p>}
            {receiptForm.is_existing ? (
              <>
                <SelectedSupplierCard supplier={selectedReceiptSupplier} />
                <p className="empty-state">Поставщик фиксируется при создании заявки и больше не изменяется.</p>
              </>
            ) : (
              <SearchableSupplierSelect
                disabled={receiptForm.is_locked}
                suppliers={suppliers}
                value={receiptForm.supplier_id}
                onChange={(supplierId) => {
                  setReceiptForm({ ...receiptForm, supplier_id: supplierId })
                  setFormError('')
                }}
              />
            )}
            {receiptForm.is_existing && (
              <div className="entity-list">
                <div className="panel-heading">
                  <div>
                    <p className="auth-eyebrow">Партии</p>
                    <h3>Порции приема</h3>
                  </div>
                  <button disabled={receiptForm.is_completed} type="button" onClick={handleAddBatch}>Добавить партию</button>
                </div>
                {receiptForm.batches.map((batch) => (
                  <div className="entity-row supplier-row" key={batch.id}>
                    <div>
                      <strong>Партия #{batch.sequence_number}</strong>
                      <span>Анализ: #{batch.laboratory_analysis_id} · {batchStatusLabel(batch)}</span>
                      <span>Введено: {batch.input_quantity ? `${batch.input_quantity} ${unitLabels[batch.input_unit]}` : 'не указано'} · В литрах: {batch.quantity_liters || '—'}</span>
                    </div>
                    {batch.can_set_quantity ? (
                      <div className="row-actions">
                        <input disabled={!canManageBatch(batch, receiptForm, user)} min="0" placeholder="Количество" step="0.001" type="number" value={batch.input_quantity} onChange={(event) => updateBatchForm(batch.id, { input_quantity: event.target.value })} />
                        <div className="unit-radio-group" role="radiogroup" aria-label={`Единица измерения партии ${batch.sequence_number}`}>
                          {[
                            { value: 'liters', label: 'Литры' },
                            { value: 'kilograms', label: 'Килограммы' },
                          ].map((unit) => (
                            <label className={batch.input_unit === unit.value ? 'active' : ''} key={unit.value}>
                              <input
                                checked={batch.input_unit === unit.value}
                                disabled={!canManageBatch(batch, receiptForm, user)}
                                name={`batch-unit-${batch.id}`}
                                type="radio"
                                value={unit.value}
                                onChange={(event) => updateBatchForm(batch.id, { input_unit: event.target.value })}
                              />
                              {unit.label}
                            </label>
                          ))}
                        </div>
                        <button disabled={!canManageBatch(batch, receiptForm, user) || !hasPositiveQuantity(batch.input_quantity)} type="button" onClick={() => handleBatchSave(batch)}>Сохранить</button>
                        <button className="danger-button" disabled={!canManageBatch(batch, receiptForm, user) || receiptForm.batches.length <= 1} type="button" onClick={() => handleBatchDelete(batch)}>Удалить</button>
                      </div>
                    ) : (
                      <div className="row-actions">
                        <span className="empty-state">{batch.is_distributed ? 'Партия уже распределена' : 'Количество после одобрения анализа'}</span>
                        <button className="danger-button" disabled={!canManageBatch(batch, receiptForm, user) || receiptForm.batches.length <= 1} type="button" onClick={() => handleBatchDelete(batch)}>Удалить</button>
                      </div>
                    )}
                  </div>
                ))}
                {receiptForm.can_complete && receiptForm.batches.some((batch) => batch.is_analysis_approved && !batch.is_distributed) && (
                  <section className="receipt-distribution">
                    <div>
                      <p className="auth-eyebrow">Распределение</p>
                      <h3>Разместить партии по приёмным бакам</h3>
                      <p>Сумма по каждой партии должна точно совпадать с её объёмом в литрах.</p>
                    </div>
                    {receiptForm.batches.filter((batch) => batch.is_analysis_approved && !batch.is_distributed).map((batch) => (
                      <div className="distribution-batch" key={batch.id}>
                        <div className="distribution-batch-heading">
                          <strong>Партия #{batch.sequence_number}</strong>
                          <span>Нужно распределить: {batch.quantity_liters} л</span>
                        </div>
                        {(distributions[batch.id] || []).map((row, rowIndex) => (
                          <div className="distribution-row" key={`${batch.id}-${rowIndex}`}>
                            <select required value={row.tank_id} onChange={(event) => updateDistribution(batch.id, rowIndex, { tank_id: event.target.value })}>
                              <option value="">Выберите бак</option>
                              {receivingTanks.map((tank) => (
                                <option key={tank.id} value={tank.id}>{tank.name} · свободно {tank.free_volume_liters} л</option>
                              ))}
                            </select>
                            <input min="0.001" placeholder="Объём, л" required step="0.001" type="number" value={row.volume_liters} onChange={(event) => updateDistribution(batch.id, rowIndex, { volume_liters: event.target.value })} />
                            {(distributions[batch.id] || []).length > 1 && (
                              <button className="danger-button" type="button" onClick={() => removeDistribution(batch.id, rowIndex)}>Убрать</button>
                            )}
                          </div>
                        ))}
                        <button className="secondary-button" type="button" onClick={() => addDistribution(batch.id)}>Добавить бак</button>
                      </div>
                    ))}
                  </section>
                )}
              </div>
            )}
            <div className="form-actions">
              {receiptForm.can_complete && !isDistributionComplete && (
                <p className="form-action-hint">Кнопка завершения станет доступна после полного распределения каждой партии.</p>
              )}
              {receiptForm.can_complete && (
                <button disabled={!isDistributionComplete} type="button" onClick={handleReceiptCompleteFromModal}>Завершить прием</button>
              )}
              {!receiptForm.is_existing && <button disabled={!receiptForm.supplier_id || (receiptForm.is_locked && !isAdminUser(user))} type="submit">Создать</button>}
              <button className="secondary-button" type="button" onClick={() => setIsFormOpen(false)}>Отмена</button>
            </div>
          </form>
        </OperationsModal>
      )}

      {deleteTarget && (
        <DeleteConfirmModal
          entityName="запись приема"
          itemName={receiptLabel(deleteTarget)}
          onCancel={() => setDeleteTarget(null)}
          onConfirm={handleReceiptDelete}
        />
      )}
    </DashboardShell>
  )
}

export function LaboratoryAnalysesPage({ onLogout, token, user }) {
  const notificationAudioRef = useRef(null)
  const pendingNotificationRef = useRef(false)
  const playNewAnalysisNotification = useCallback(() => {
    const audio = notificationAudioRef.current
    if (!audio) {
      return
    }

    audio.currentTime = 0
    audio.play().catch(() => {
      pendingNotificationRef.current = true
    })
  }, [])

  useEffect(() => {
    const audio = notificationAudioRef.current
    if (!audio) {
      return undefined
    }

    function removeUnlockListeners() {
      window.removeEventListener('pointerdown', unlockAudio, true)
      window.removeEventListener('keydown', unlockAudio, true)
    }

    async function unlockAudio() {
      removeUnlockListeners()
      const previousVolume = audio.volume
      audio.volume = 0

      try {
        await audio.play()
        audio.pause()
        audio.currentTime = 0
      } catch {
        pendingNotificationRef.current = false
      } finally {
        audio.volume = previousVolume
      }

      if (pendingNotificationRef.current) {
        pendingNotificationRef.current = false
        audio.currentTime = 0
        audio.play().catch(() => {})
      }
    }

    window.addEventListener('pointerdown', unlockAudio, true)
    window.addEventListener('keydown', unlockAudio, true)

    return removeUnlockListeners
  }, [])

  const { analyses, error, saveAnalysisStatus } = useOperationsCrud(token, {
    onReceiptCreated: playNewAnalysisNotification,
  })
  const [decisionFilter, setDecisionFilter] = useState('pending')
  const filteredAnalyses = filterAnalysesByDecision(analyses, decisionFilter)
  const analysisControls = useListControls(filteredAnalyses, (item) => [
    item.id,
    item.receipt?.supplier?.company_name,
    item.batch_sequence_number,
    item.density,
    item.flash_point_temperature,
    item.current_temperature,
    item.water_percentage,
  ].join(' '))
  const [analysisForm, setAnalysisForm] = useState(emptyLaboratoryAnalysisForm)
  const [isFormOpen, setIsFormOpen] = useState(false)
  const [formError, setFormError] = useState('')

  function openEditModal(item) {
    setAnalysisForm({
      id: item.id,
      density: item.density,
      flash_point_temperature: item.flash_point_temperature,
      current_temperature: item.current_temperature,
      water_percentage: item.water_percentage,
      is_approved: item.is_approved,
      is_rejected: item.is_rejected,
    })
    setFormError('')
    setIsFormOpen(true)
  }

  const isDecisionLocked = (analysisForm.is_approved || analysisForm.is_rejected) && !isAdminUser(user)

  async function handleAnalysisSubmit(event, statusPayload) {
    event.preventDefault()
    if (statusPayload.is_approved) {
      const validationError = validateLaboratoryApproval(analysisForm)
      if (validationError) {
        setFormError(validationError)
        return
      }
    }
    setFormError('')
    const isSaved = await saveAnalysisStatus(analysisForm, () => setAnalysisForm(emptyLaboratoryAnalysisForm), statusPayload)
    if (isSaved) {
      setIsFormOpen(false)
    }
  }

  return (
    <DashboardShell title="Лабораторный анализ" onLogout={onLogout} user={user}>
      <audio ref={notificationAudioRef} src={notificationSound} preload="auto" />

      <OperationsPageHeader
        title="Лабораторный анализ"
        description="Фиксация плотности, температурных показателей и процента воды. Анализ один-к-одному связан с записью приема сырья."
      />

      {error && <p className="access-error">{error}</p>}

      <section className="access-grid">
        <article className="access-card">
          <div className="panel-heading">
            <div>
              <p className="auth-eyebrow">Лаборатория</p>
              <h3>Анализы сырья</h3>
            </div>
            <span className="empty-state">Создается автоматически при приеме</span>
          </div>

          <ListControls
            currentPage={analysisControls.currentPage}
            filteredCount={analysisControls.filteredCount}
            onPageChange={analysisControls.setCurrentPage}
            onSearchChange={analysisControls.setSearchQuery}
            pageCount={analysisControls.pageCount}
            searchQuery={analysisControls.searchQuery}
            totalCount={analysisControls.totalCount}
          />

          <div className="filter-pills" role="radiogroup" aria-label="Фильтр статуса анализа">
            {analysisFilterOptions.map((option) => (
              <label className={decisionFilter === option.value ? 'active' : ''} key={option.value}>
                <input
                  type="radio"
                  name="analysis_filter"
                  value={option.value}
                  checked={decisionFilter === option.value}
                  onChange={(event) => setDecisionFilter(event.target.value)}
                />
                <span>{option.label}</span>
              </label>
            ))}
          </div>

          <div className="entity-list">
            {analysisControls.paginatedItems.map((item) => (
              <div className={analysisRowClassName(item)} key={item.id}>
                <div>
                  <strong>Анализ #{item.id} · {receiptLabel(item.receipt)} · Партия #{item.batch_sequence_number || '—'}</strong>
                  <span>Плотность: {item.density || '—'} г/см³ · Вода: {item.water_percentage || '—'}%</span>
                  <span>Температура вспышки: {item.flash_point_temperature || '—'} °C · Текущая: {item.current_temperature || '—'} °C</span>
                  <span>Создано: {formatDateTime(item.created_at)} · Решение: {formatDateTime(item.decided_at)}</span>
                  <span>{item.is_rejected ? 'Отказан' : item.is_approved ? 'Одобрен' : item.is_filled ? 'Заполнен, ожидает решения' : 'Ожидает заполнения'}</span>
                  <DensityCheckNotice density={item.density} temperature={item.current_temperature} />
                </div>
                {canManageAnalysis(item) && (
                  <div className="row-actions">
                    <button type="button" onClick={() => openEditModal(item)}>Изменить</button>
                  </div>
                )}
              </div>
            ))}
            {!analyses.length && <p className="empty-state">Анализов пока нет. Добавьте первый лабораторный анализ.</p>}
            {Boolean(analyses.length) && !analysisControls.filteredCount && <p className="empty-state">По вашему запросу ничего не найдено.</p>}
          </div>
        </article>
      </section>

      {isFormOpen && (
        <OperationsModal title="Редактировать лабораторный анализ" onClose={() => setIsFormOpen(false)}>
          <form className="crud-form" onSubmit={(event) => handleAnalysisSubmit(event, {})}>
            {isDecisionLocked && <p className="empty-state">Статус уже выставлен. Данные и решение может изменить только администратор.</p>}
            {formError && <p className="form-error" role="alert">{formError}</p>}
            <label>
              <span>Плотность, г/см³</span>
              <input disabled={isDecisionLocked} min="0" step="0.0001" type="number" value={analysisForm.density} onChange={(event) => setAnalysisForm({ ...analysisForm, density: event.target.value })} />
            </label>
            <label>
              <span>Температура вспышки, °C</span>
              <input disabled={isDecisionLocked} step="0.01" type="number" value={analysisForm.flash_point_temperature} onChange={(event) => setAnalysisForm({ ...analysisForm, flash_point_temperature: event.target.value })} />
            </label>
            <label>
              <span>Текущая температура, °C</span>
              <input disabled={isDecisionLocked} step="0.01" type="number" value={analysisForm.current_temperature} onChange={(event) => setAnalysisForm({ ...analysisForm, current_temperature: event.target.value })} />
            </label>
            <label>
              <span>Количество воды, %</span>
              <input disabled={isDecisionLocked} min="0" max="100" step="0.001" type="number" value={analysisForm.water_percentage} onChange={(event) => setAnalysisForm({ ...analysisForm, water_percentage: event.target.value })} />
            </label>
            <DensityCheckNotice density={analysisForm.density} temperature={analysisForm.current_temperature} />
            <div className="form-actions">
              <button disabled={isDecisionLocked} type="button" onClick={(event) => handleAnalysisSubmit(event, { is_approved: true, is_rejected: false })}>Одобрить</button>
              <button className="danger-button" disabled={isDecisionLocked} type="button" onClick={(event) => handleAnalysisSubmit(event, { is_approved: false, is_rejected: true })}>Отказать</button>
              <button className="secondary-button" disabled={isDecisionLocked} type="submit">Сохранить без решения</button>
              <button className="secondary-button" type="button" onClick={() => setIsFormOpen(false)}>Отмена</button>
            </div>
          </form>
        </OperationsModal>
      )}
    </DashboardShell>
  )
}
