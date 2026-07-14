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
  return isAdminUser(user) || !(receipt.is_completed || batch.is_locked || batch.is_analysis_rejected)
}

function canManageAnalysis(item) {
  return !(item.is_approved || item.is_rejected)
}

function hasPositiveQuantity(value) {
  return Number(value) > 0
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
  const { addReceiptBatch, completeReceipt, deleteReceipt, deleteReceiptBatch, error, receipts, saveReceipt, saveReceiptBatch, suppliers } = useOperationsCrud(token)
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
  const selectedReceiptSupplier = suppliers.find((supplier) => String(supplier.id) === String(receiptForm.supplier_id))

  function openCreateModal() {
    setReceiptForm(emptyReceiptForm)
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
    setIsFormOpen(true)
  }

  async function handleReceiptSubmit(event) {
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
    const isCompleted = await completeReceipt(receiptForm.id)
    if (isCompleted) {
      setIsFormOpen(false)
    }
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
                onChange={(supplierId) => setReceiptForm({ ...receiptForm, supplier_id: supplierId })}
              />
            )}
            {receiptForm.is_existing && (
              <div className="entity-list">
                <div className="panel-heading">
                  <div>
                    <p className="auth-eyebrow">Партии</p>
                    <h3>Порции приема</h3>
                  </div>
                  <button disabled={receiptForm.is_completed && !isAdminUser(user)} type="button" onClick={handleAddBatch}>Добавить партию</button>
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
                        <select disabled={!canManageBatch(batch, receiptForm, user)} value={batch.input_unit} onChange={(event) => updateBatchForm(batch.id, { input_unit: event.target.value })}>
                          <option value="liters">Литры</option>
                          <option value="kilograms">Килограммы</option>
                        </select>
                        <button disabled={!canManageBatch(batch, receiptForm, user) || !hasPositiveQuantity(batch.input_quantity)} type="button" onClick={() => handleBatchSave(batch)}>Сохранить</button>
                        <button className="danger-button" disabled={!canManageBatch(batch, receiptForm, user) || receiptForm.batches.length <= 1} type="button" onClick={() => handleBatchDelete(batch)}>Удалить</button>
                      </div>
                    ) : (
                      <div className="row-actions">
                        <span className="empty-state">Количество после одобрения анализа</span>
                        <button className="danger-button" disabled={!canManageBatch(batch, receiptForm, user) || receiptForm.batches.length <= 1} type="button" onClick={() => handleBatchDelete(batch)}>Удалить</button>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
            <div className="form-actions">
              {receiptForm.can_complete && (
                <button type="button" onClick={handleReceiptCompleteFromModal}>Завершить прием</button>
              )}
              {!receiptForm.is_existing && <button disabled={receiptForm.is_locked && !isAdminUser(user)} type="submit">Создать</button>}
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
    setIsFormOpen(true)
  }

  const isDecisionLocked = (analysisForm.is_approved || analysisForm.is_rejected) && !isAdminUser(user)

  async function handleAnalysisSubmit(event, statusPayload) {
    event.preventDefault()
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
            <input disabled={isDecisionLocked} placeholder="Плотность, г/см³" min="0" step="0.0001" type="number" value={analysisForm.density} onChange={(event) => setAnalysisForm({ ...analysisForm, density: event.target.value })} />
            <input disabled={isDecisionLocked} placeholder="Температура вспышки, °C" step="0.01" type="number" value={analysisForm.flash_point_temperature} onChange={(event) => setAnalysisForm({ ...analysisForm, flash_point_temperature: event.target.value })} />
            <input disabled={isDecisionLocked} placeholder="Текущая температура, °C" step="0.01" type="number" value={analysisForm.current_temperature} onChange={(event) => setAnalysisForm({ ...analysisForm, current_temperature: event.target.value })} />
            <input disabled={isDecisionLocked} placeholder="Количество воды, %" min="0" step="0.001" type="number" value={analysisForm.water_percentage} onChange={(event) => setAnalysisForm({ ...analysisForm, water_percentage: event.target.value })} />
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
