import { t } from '../../i18n/core'
import { useSearchParams } from 'react-router'
import { localizeAuditEntry } from '../../i18n/audit'
import { useState } from 'react'
import { DashboardShell } from '../../components/Layout/DashboardShell'
import { ListControls } from '../../components/ListControls/ListControls'
import { DeleteConfirmModal, Modal } from '../../components/Modal/Modal'
import { useListControls } from '../../hooks/useListControls'
import { useProcessingCrud } from '../../hooks/useProcessingCrud'
import { oilContainerConfig, oilFinishingForms } from '../../constants/oilFinishing'
import { oilManufacturingMovements } from '../../constants/oilManufacturing'
import { workshopTankTransfers } from '../../constants/workshopTankTransfers'
import { createIdempotencyKey, formatDateTime, formatReceiver, formatVolume } from './processingFormat'

const emptyContainerForm = {
  id: null,
  kind: 'receiving_tank',
  number: '',
  capacity_liters: '',
  is_active: true,
  oil_grade_id: '',
}

const emptyJournalFilters = {
  query: '',
  date_from: '',
  date_to: '',
  movement_type: '',
  status: '',
  source: '',
  destination: '',
  user: '',
  number: '',
  volume: '',
}

export function ProcessingPageHeader({ description, showEyebrow = true, title }) {
  return (
    <section className="page-title access-page-title">
      {showEyebrow && <p className="auth-eyebrow">{t('Переработка отработанного масла')}</p>}
      <h1>{title}</h1>
      <p>{description}</p>
    </section>
  )
}

function ContainerPage({ kind, onLogout, token, user }) {
  const isAdmin = Boolean(user?.is_admin)
  const isFlowFilter = kind === 'finishing_filter'
  const { boilers, chemicalMixers, deleteContainer, error, oilContainers, oilGrades, processingWorkshops, rawDieselTanks, rawSpindleTanks, receivingTanks, saveContainer } = useProcessingCrud(token, { containerKinds: [kind], loadOilGrades: kind === 'finished_oil_tank' })
  const pageConfig = {
    receiving_tank: {
      containers: receivingTanks,
      description: t('Текущий объём принятого отработанного масла и передача сырья в котлы.'),
      title: t('Приёмные баки'),
    },
    preheating_boiler: {
      containers: boilers,
      description: t('Учёт загрузки котлов первичного прогрева без запуска и параметров прогрева.'),
      title: t('Котлы первичного прогрева'),
    },
    chemical_mixer: {
      containers: chemicalMixers,
      description: t('Учёт вместимости, текущего объёма и доступности химических миксеров.'),
      title: t('Химические миксеры'),
    },
    processing_workshop: {
      containers: processingWorkshops,
      description: t('Реакторы переработки и их последние фактические замеры. У каждого реактора четыре ресивера.'),
      title: t('Реакторы переработки'),
    },
    raw_diesel_tank: {
      containers: rawDieselTanks,
      description: t('Учёт вместимости, текущего объёма и доступности баков сырой солярки.'),
      title: t('Баки сырой солярки'),
    },
    raw_spindle_tank: {
      containers: rawSpindleTanks,
      description: t('Учёт вместимости, текущего объёма и доступности баков сырой веретенки.'),
      title: t('Баки сырой веретенки'),
    },
    nigrol_tank: {
      containers: oilContainers.nigrol_tank || [],
      description: t('Учёт вместимости баков и остатков нигрола, поступившего из реакторов.'),
      title: t('Баки нигрола'),
    },
  }[kind] || {
    containers: oilContainers[kind] || [],
    title: t(oilContainerConfig[kind].title),
    description: t(isFlowFilter ? 'Один общий проточный фильтр без вместимости и учётного остатка масла.' : oilContainerConfig[kind]?.manufacturing ? 'Оборудование производства товарных масел. Марка непустого продуктового бака неизменна.' : 'Учёт вместимости и остатков на линии финишной очистки.'),
  }
  const containers = pageConfig.containers
  const controls = useListControls(containers, (item) => [item.number, t(item.name), item.current_volume_liters].join(' '))
  const [containerForm, setContainerForm] = useState({ ...emptyContainerForm, kind })
  const [isContainerFormOpen, setIsContainerFormOpen] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState(null)
  const isTankPage = kind === 'receiving_tank'
  const title = pageConfig.title

  function openCreateModal() {
    setContainerForm({ ...emptyContainerForm, kind })
    setIsContainerFormOpen(true)
  }

  function openEditModal(item) {
    setContainerForm({
      id: item.id,
      kind: item.kind,
      number: item.number,
      capacity_liters: item.capacity_liters,
      is_active: item.is_active,
      oil_grade_id: item.oil_grade_id || '',
    })
    setIsContainerFormOpen(true)
  }

  async function handleContainerSubmit(event) {
    const saved = await saveContainer(event, containerForm)
    if (saved) {
      setIsContainerFormOpen(false)
    }
  }

  async function handleDelete() {
    const deleted = await deleteContainer(deleteTarget.id)
    if (deleted) {
      setDeleteTarget(null)
    }
  }

  return (
    <DashboardShell title={title} onLogout={onLogout} user={user}>
      <ProcessingPageHeader
        title={title}
        description={pageConfig.description}
      />

      {error && <p className="access-error">{t(error)}</p>}

      <section className="access-grid">
        <article className="access-card">
          <div className="panel-heading">
            <div>
              <p className="auth-eyebrow">{t(isFlowFilter ? 'Оборудование' : 'Ёмкости')}</p>
              <h3>{title}</h3>
            </div>
            {isAdmin && <button type="button" onClick={openCreateModal}>{t('Создать')}</button>}
          </div>

          <ListControls
            currentPage={controls.currentPage}
            filteredCount={controls.filteredCount}
            onPageChange={controls.setCurrentPage}
            onSearchChange={controls.setSearchQuery}
            pageCount={controls.pageCount}
            searchQuery={controls.searchQuery}
            totalCount={controls.totalCount}
          />

          <div className="entity-list">
            {controls.paginatedItems.map((item) => (
              <div className={`entity-row processing-container-row ${!item.is_active ? 'disabled-row' : ''}`} key={item.id}>
                <div>
                  <strong>{t(item.name)}</strong>
                  {isFlowFilter ? (
                    <span>{t('Проточный фильтр')}</span>
                  ) : kind === 'processing_workshop' ? (
                    <span>{t('Последний фактический замер')}: {item.measured_at ? `${formatVolume(item.measured_liters)} · ${formatDateTime(item.measured_at)}` : t('Нет замера')}</span>
                  ) : item.volume_known === false ? <>
                    <span>{item.active_batch ? item.active_batch.number : t('Нет открытой партии')}</span>
                    {item.active_batch && <span>{t('Загружено жидких компонентов')}: {formatVolume(item.active_batch.input_liters)} · {t('Перелито по замеру')}: {formatVolume(item.active_batch.output_liters)}</span>}
                  </> : <span>{t('Текущий объём: ')}{formatVolume(item.current_volume_liters)}</span>}
                  {item.grade_name && <span>{t('Марка масла')}: {item.grade_name}</span>}
                  {item.oil_product && <span>{t(item.oil_product === 'diesel' ? 'Солярка' : 'Веретенка')}</span>}
                  {isAdmin && (
                    <>
                      {!isFlowFilter && <>
                        <span>{t('Вместимость: ')}{formatVolume(item.capacity_liters)}{item.fill_percentage != null && <>{t(' · Свободно: ')}{formatVolume(item.free_volume_liters)}</>}</span>
                        <span>{item.fill_percentage != null && <>{t('Заполнение: ')}{item.fill_percentage}% · </>}{t('Последнее движение')}: {formatDateTime(item.last_movement_at)}</span>
                      </>}
                      <span>{item.is_active ? t('Активна') : t('Деактивирована')}</span>
                      {!isTankPage && Boolean(item.recent_loadings?.length) && (
                        <span>{t('Последние загрузки: ')}{item.recent_loadings.map((movement) => `${formatDateTime(movement.moved_at)} — ${formatVolume(movement.volume_liters)}`).join('; ')}</span>
                      )}
                    </>
                  )}
                </div>
                <div className="row-actions">
                  {isAdmin && <button type="button" onClick={() => openEditModal(item)}>{t('Изменить')}</button>}
                  {isAdmin && <button className="danger-button" type="button" onClick={() => setDeleteTarget(item)}>{t('Удалить')}</button>}
                </div>
              </div>
            ))}
            {!containers.length && <p className="empty-state">{t(isFlowFilter ? 'Фильтр пока не настроен.' : 'Ёмкости пока не созданы.')}</p>}
            {Boolean(containers.length) && !controls.filteredCount && <p className="empty-state">{t('По вашему запросу ничего не найдено.')}</p>}
          </div>
        </article>
      </section>

      {isContainerFormOpen && (
        <Modal title={isFlowFilter ? t(containerForm.id ? 'Изменить фильтр' : 'Новый фильтр') : t(containerForm.id ? 'Изменить ёмкость' : 'Новая ёмкость')} onClose={() => setIsContainerFormOpen(false)}>
          <form className="crud-form" onSubmit={handleContainerSubmit}>
            <label>
              <span>{t('Номер')}</span>
              <input min="1" required type="number" value={containerForm.number} onChange={(event) => setContainerForm({ ...containerForm, number: event.target.value })} />
            </label>
            {!isFlowFilter && <label>
              <span>{t('Вместимость, л')}</span>
              <input min="1" required step="1" type="number" value={containerForm.capacity_liters} onChange={(event) => setContainerForm({ ...containerForm, capacity_liters: event.target.value })} />
            </label>}
            <label className="checkbox-row">
              <input checked={containerForm.is_active} type="checkbox" onChange={(event) => setContainerForm({ ...containerForm, is_active: event.target.checked })} />{t('Активна')}</label>
            {kind === 'finished_oil_tank' && <label><span>{t('Марка масла')}</span><select required value={containerForm.oil_grade_id} onChange={(event) => setContainerForm({ ...containerForm, oil_grade_id: event.target.value })}>
              <option value="">{t('Выберите активную марку масла.')}</option>
              {oilGrades.filter((grade) => grade.is_active || grade.id === Number(containerForm.oil_grade_id)).map((grade) => <option key={grade.id} value={grade.id}>{grade.name}</option>)}
            </select></label>}
            <div className="form-actions">
              <button type="submit">{containerForm.id ? t('Сохранить') : t('Создать')}</button>
              <button className="secondary-button" type="button" onClick={() => setIsContainerFormOpen(false)}>{t('Отмена')}</button>
            </div>
          </form>
        </Modal>
      )}

      {deleteTarget && (
        <DeleteConfirmModal
          entityName={t(isFlowFilter ? 'фильтр' : 'ёмкость')}
          itemName={t(deleteTarget.name)}
          onCancel={() => setDeleteTarget(null)}
          onConfirm={handleDelete}
        />
      )}
    </DashboardShell>
  )
}

export function OilContainersPage({ kind, ...props }) {
  return <ContainerPage kind={kind} {...props} />
}

export function ReceivingTanksPage(props) {
  return <ContainerPage {...props} kind="receiving_tank" />
}

export function PreheatingBoilersPage(props) {
  return <ContainerPage {...props} kind="preheating_boiler" />
}

export function ChemicalMixersPage(props) {
  return <ContainerPage {...props} kind="chemical_mixer" />
}

export function ProcessingWorkshopsPage(props) {
  return <ContainerPage {...props} kind="processing_workshop" />
}

export function RawDieselTanksPage(props) {
  return <ContainerPage {...props} kind="raw_diesel_tank" />
}

export function RawSpindleTanksPage(props) {
  return <ContainerPage {...props} kind="raw_spindle_tank" />
}

export function NigrolTanksPage(props) {
  return <ContainerPage {...props} kind="nigrol_tank" />
}

export function BoilerLoadingPage({ onLogout, token, user }) {
  const { boilers, createTankToBoilerMovement, error, receivingTanks } = useProcessingCrud(token, { containerKinds: ['receiving_tank', 'preheating_boiler'] })
  const [form, setForm] = useState(() => ({
    source_tank_id: '',
    destination_boiler_id: '',
    volume_liters: '',
    idempotency_key: createIdempotencyKey(),
  }))
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [createdMovement, setCreatedMovement] = useState(null)
  const availableTanks = receivingTanks.filter((tank) => tank.is_active && Number(tank.current_volume_liters) > 0)
  const availableBoilers = boilers.filter((boiler) => boiler.is_active && boiler.can_receive)
  const selectedTank = receivingTanks.find((tank) => String(tank.id) === String(form.source_tank_id))
  const selectedBoiler = boilers.find((boiler) => String(boiler.id) === String(form.destination_boiler_id))
  const volume = Number(form.volume_liters)
  const sourceVolume = Number(selectedTank?.current_volume_liters || 0)
  const destinationVolume = Number(selectedBoiler?.current_volume_liters || 0)
  const destinationFreeVolume = selectedBoiler?.free_volume_liters === undefined
    ? null
    : Number(selectedBoiler.free_volume_liters)
  const hasPositiveVolume = Number.isFinite(volume) && volume > 0
  const exceedsSource = hasPositiveVolume && volume > sourceVolume
  const exceedsDestination = hasPositiveVolume && destinationFreeVolume !== null && volume > destinationFreeVolume
  const canSubmit = Boolean(selectedTank && selectedBoiler && hasPositiveVolume && !exceedsSource && !exceedsDestination && !isSubmitting)

  async function handleSubmit(event) {
    event.preventDefault()
    if (!canSubmit) {
      return
    }

    setIsSubmitting(true)
    setCreatedMovement(null)
    const movement = await createTankToBoilerMovement(form)
    setIsSubmitting(false)
    if (movement?.id) {
      setCreatedMovement(movement)
      setForm((current) => ({
        ...current,
        volume_liters: '',
        idempotency_key: createIdempotencyKey(),
      }))
    }
  }

  return (
    <DashboardShell title={t('Загрузка котла отработки')} onLogout={onLogout} user={user}>
      <ProcessingPageHeader
        showEyebrow={false}
        title={t('Загрузка котла отработки')}
        description={t('Регистрация движения отработанного масла из приёмного бака в котёл первичного прогрева.')}
      />

      {error && <p className="access-error">{t(error)}</p>}

      <section className="boiler-loading-layout">
        <article className="access-card boiler-loading-form-card">
          <div className="panel-heading">
            <div>
              <p className="auth-eyebrow">{t('Новое движение')}</p>
              <h3>{t('Выберите источник, котёл и объём')}</h3>
            </div>
          </div>

          <form className="crud-form boiler-loading-form" onSubmit={handleSubmit}>
            <select
              aria-label={t('Приёмный бак')}
              required
              value={form.source_tank_id}
              onChange={(event) => setForm({ ...form, source_tank_id: event.target.value })}
            >
              <option value="">{t('Выберите приёмный бак')}</option>
              {availableTanks.map((tank) => (
                <option key={tank.id} value={tank.id}>{t(tank.name)}{t(' · доступно ')}{formatVolume(tank.current_volume_liters)}</option>
              ))}
            </select>

            <select
              aria-label={t('Котёл первичного прогрева')}
              required
              value={form.destination_boiler_id}
              onChange={(event) => setForm({ ...form, destination_boiler_id: event.target.value })}
            >
              <option value="">{t('Выберите котёл')}</option>
              {availableBoilers.map((boiler) => (
                <option key={boiler.id} value={boiler.id}>{t(boiler.name)}{t(' · сейчас ')}{formatVolume(boiler.current_volume_liters)}</option>
              ))}
            </select>

            <input
              aria-label={t('Объём движения, л')}
              min="0.001"
              placeholder={t('Объем')}
              required
              step="0.001"
              type="number"
              value={form.volume_liters}
              onChange={(event) => setForm({ ...form, volume_liters: event.target.value })}
            />

            {exceedsSource && <p className="access-error">{t('Указанный объём превышает остаток выбранного приёмного бака.')}</p>}
            {exceedsDestination && <p className="access-error">{t('Указанный объём превышает свободное место выбранного котла.')}</p>}
            {!availableTanks.length && <p className="empty-state">{t('Нет активных приёмных баков с доступным маслом.')}</p>}
            {!availableBoilers.length && <p className="empty-state">{t('Нет активных котлов, доступных для загрузки.')}</p>}

            <div className="form-actions">
              <button disabled={!canSubmit} type="submit">{isSubmitting ? t('Выполняется...') : t('Подтвердить движение')}</button>
              <button
                className="secondary-button"
                type="button"
                onClick={() => {
                  setCreatedMovement(null)
                  setForm({
                    source_tank_id: '',
                    destination_boiler_id: '',
                    volume_liters: '',
                    idempotency_key: createIdempotencyKey(),
                  })
                }}
              >{t('Очистить')}</button>
            </div>
          </form>
        </article>

        <aside className="boiler-loading-summary">
          <article className="access-card movement-preview-card">
            <p className="auth-eyebrow">{t('Предварительный баланс')}</p>
            <h3>{t('После движения')}</h3>
            <div className="movement-preview-grid">
              <div>
                <span>{t('Приёмный бак')}</span>
                <strong>{t(selectedTank?.name) || t('Не выбран')}</strong>
                <small>{t('Сейчас: ')}{formatVolume(selectedTank?.current_volume_liters)}</small>
                <small>{t('Останется: ')}{selectedTank && hasPositiveVolume && !exceedsSource ? formatVolume(sourceVolume - volume) : '—'}</small>
              </div>
              <span aria-hidden="true" className="movement-preview-arrow">→</span>
              <div>
                <span>{t('Котёл')}</span>
                <strong>{t(selectedBoiler?.name) || t('Не выбран')}</strong>
                <small>{t('Сейчас: ')}{formatVolume(selectedBoiler?.current_volume_liters)}</small>
                <small>{t('Будет: ')}{selectedBoiler && hasPositiveVolume ? formatVolume(destinationVolume + volume) : '—'}</small>
              </div>
            </div>
          </article>

          {createdMovement && (
            <article className="access-card movement-success-card">
              <p className="auth-eyebrow">{t('Движение выполнено')}</p>
              <h3>{createdMovement.movement_number}</h3>
              <span>{t(createdMovement.source)} → {t(createdMovement.destination)}</span>
              <strong>{formatVolume(createdMovement.volume_liters)}</strong>
              <small>{formatDateTime(createdMovement.moved_at)}</small>
            </article>
          )}
        </aside>
      </section>
    </DashboardShell>
  )
}

export function WorkshopLoadingPage({ onLogout, token, user }) {
  const { boilers, processingWorkshops, createWorkshopLoading, error } = useProcessingCrud(token, { containerKinds: ['preheating_boiler', 'processing_workshop'] })
  const [form, setForm] = useState(() => ({
    source_boiler_id: '',
    destination_workshop_id: '',
    volume_liters: '',
    idempotency_key: createIdempotencyKey(),
  }))
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [createdMovement, setCreatedMovement] = useState(null)
  const canCreate = Boolean(user?.is_admin || user?.access?.['workshop-loading']?.includes('create'))
  const availableBoilers = boilers.filter((boiler) => boiler.is_active && Number(boiler.current_volume_liters) > 0)
  const availableWorkshops = processingWorkshops.filter((workshop) => workshop.is_active && workshop.can_receive)
  const selectedBoiler = boilers.find((boiler) => String(boiler.id) === String(form.source_boiler_id))
  const selectedWorkshop = processingWorkshops.find((workshop) => String(workshop.id) === String(form.destination_workshop_id))
  const volume = Number(form.volume_liters)
  const sourceVolume = Number(selectedBoiler?.current_volume_liters || 0)
  const destinationCapacity = Number(selectedWorkshop?.capacity_liters)
  const hasPositiveVolume = Number.isFinite(volume) && volume > 0
  const exceedsSource = hasPositiveVolume && volume > sourceVolume
  const exceedsDestination = hasPositiveVolume && volume > destinationCapacity
  const canSubmit = Boolean(canCreate && selectedBoiler && selectedWorkshop && hasPositiveVolume && !exceedsSource && !exceedsDestination && !isSubmitting)

  async function handleSubmit(event) {
    event.preventDefault()
    if (!canSubmit) {
      return
    }

    setIsSubmitting(true)
    setCreatedMovement(null)
    const movement = await createWorkshopLoading(form)
    setIsSubmitting(false)
    if (movement?.id) {
      setCreatedMovement(movement)
      setForm((current) => ({
        ...current,
        volume_liters: '',
        idempotency_key: createIdempotencyKey(),
      }))
    }
  }

  return (
    <DashboardShell title={t('Загрузка реактора переработки')} onLogout={onLogout} user={user}>
      <ProcessingPageHeader
        showEyebrow={false}
        title={t('Загрузка реактора переработки')}
        description={t('Загрузите масло из котла. После загрузки первым открывается ресивер №1.')}
      />

      {error && <p className="access-error">{t(error)}</p>}

      <section className="boiler-loading-layout">
        <article className="access-card boiler-loading-form-card">
          <div className="panel-heading">
            <div>
              <p className="auth-eyebrow">{t('Новое движение')}</p>
              <h3>{t('Выберите котёл, реактор и объём')}</h3>
            </div>
          </div>

          <form className="crud-form boiler-loading-form" onSubmit={handleSubmit}>
            <select
              aria-label={t('Котёл первичного прогрева')}
              required
              value={form.source_boiler_id}
              onChange={(event) => setForm({ ...form, source_boiler_id: event.target.value })}
            >
              <option value="">{t('Выберите котёл')}</option>
              {availableBoilers.map((boiler) => (
                <option key={boiler.id} value={boiler.id}>{t(boiler.name)}{t(' · доступно ')}{formatVolume(boiler.current_volume_liters)}</option>
              ))}
            </select>

            <select
              aria-label={t('Реактор переработки')}
              required
              value={form.destination_workshop_id}
              onChange={(event) => setForm({ ...form, destination_workshop_id: event.target.value })}
            >
              <option value="">{t('Выберите реактор')}</option>
              {availableWorkshops.map((workshop) => (
                <option key={workshop.id} value={workshop.id}>{t(workshop.name)}</option>
              ))}
            </select>

            <input
              aria-label={t('Объём движения, л')}
              min="0.001"
              placeholder={t('Объем')}
              required
              step="0.001"
              type="number"
              value={form.volume_liters}
              onChange={(event) => setForm({ ...form, volume_liters: event.target.value })}
            />

            {exceedsSource && <p className="access-error">{t('Указанный объём превышает остаток выбранного котла.')}</p>}
            {exceedsDestination && <p className="access-error">{t('Объём движения превышает вместимость реактора.')}</p>}
            {!availableBoilers.length && <p className="empty-state">{t('Нет активных котлов с доступным маслом.')}</p>}
            {!availableWorkshops.length && <p className="empty-state">{t('Нет активных реакторов переработки.')}</p>}

            <div className="form-actions">
              <button disabled={!canSubmit} type="submit">{isSubmitting ? t('Выполняется...') : t('Подтвердить движение')}</button>
              <button
                className="secondary-button"
                type="button"
                onClick={() => {
                  setCreatedMovement(null)
                  setForm({
                    source_boiler_id: '',
                    destination_workshop_id: '',
                    volume_liters: '',
                    idempotency_key: createIdempotencyKey(),
                  })
                }}
              >{t('Очистить')}</button>
            </div>
          </form>
        </article>

        <aside className="boiler-loading-summary">
          <article className="access-card movement-preview-card">
            <p className="auth-eyebrow">{t('Предварительный баланс')}</p>
            <h3>{t('После движения')}</h3>
            <div className="movement-preview-grid">
              <div>
                <span>{t('Котёл первичного прогрева')}</span>
                <strong>{t(selectedBoiler?.name) || t('Не выбран')}</strong>
                <small>{t('Сейчас: ')}{formatVolume(selectedBoiler?.current_volume_liters)}</small>
                <small>{t('Останется: ')}{selectedBoiler && hasPositiveVolume && !exceedsSource ? formatVolume(sourceVolume - volume) : '—'}</small>
              </div>
              <span aria-hidden="true" className="movement-preview-arrow">→</span>
              <div>
                <span>{t('Реактор переработки')}</span>
                <strong>{t(selectedWorkshop?.name) || t('Не выбран')}</strong>
                <small>{t('Последний фактический замер')}: {formatVolume(selectedWorkshop?.measured_liters)}</small>
                {selectedWorkshop?.measured_at && <small>{formatDateTime(selectedWorkshop.measured_at)}</small>}
              </div>
            </div>
          </article>

          {createdMovement && (
            <article className="access-card movement-success-card">
              <p className="auth-eyebrow">{t('Движение выполнено')}</p>
              <h3>{createdMovement.movement_number}</h3>
              <span>{t(createdMovement.source)} → {t(createdMovement.destination)}</span>
              <strong>{formatVolume(createdMovement.volume_liters)}</strong>
              <small>{formatDateTime(createdMovement.moved_at)}</small>
            </article>
          )}
        </aside>
      </section>
    </DashboardShell>
  )
}

export function WorkshopTankLoadingPage({ config, onLogout, token, user }) {
  const { createWorkshopTankLoading, error, oilContainers, processingWorkshops, receiverRuns } = useProcessingCrud(token, {
    containerKinds: config.receiver ? [config.kind] : ['processing_workshop', config.kind],
    receiverOutlet: config.receiver ? config.endpoint : undefined,
  })
  const [searchParams] = useSearchParams()
  const sourceField = config.receiver ? 'receiver_run_id' : 'source_workshop_id'
  const sourceLabel = t(config.receiver ? 'Закрытый ресивер' : 'Реактор переработки')
  const tanks = oilContainers[config.kind] || []
  const title = t(config.label)
  const productName = t(config.productName)
  const canCreate = Boolean(user?.is_admin || user?.access?.[config.moduleCode]?.includes('create'))
  const [form, setForm] = useState(() => ({
    [sourceField]: config.receiver ? searchParams.get('receiver') || '' : '',
    destination_tank_id: '',
    volume_liters: '',
    idempotency_key: createIdempotencyKey(),
  }))
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [createdMovement, setCreatedMovement] = useState(null)
  const sources = config.receiver ? receiverRuns : processingWorkshops.filter((workshop) => workshop.is_active)
  const sourceName = (source) => config.receiver ? formatReceiver(source) : t(source.name)
  const availableTanks = tanks.filter((tank) => tank.is_active && tank.can_receive)
  const selectedSource = sources.find((item) => String(item.id) === form[sourceField])
  const selectedTank = tanks.find((tank) => String(tank.id) === String(form.destination_tank_id))
  const volume = Number(form.volume_liters)
  const destinationVolume = Number(selectedTank?.current_volume_liters || 0)
  const destinationFreeVolume = selectedTank?.free_volume_liters === undefined
    ? null
    : Number(selectedTank.free_volume_liters)
  const hasPositiveVolume = Number.isFinite(volume) && volume > 0
  const exceedsSource = !config.receiver && hasPositiveVolume && volume > Number(selectedSource?.capacity_liters)
  const exceedsDestination = hasPositiveVolume && destinationFreeVolume !== null && volume > destinationFreeVolume
  const canSubmit = Boolean(canCreate && selectedSource && selectedTank?.can_receive && hasPositiveVolume && !exceedsSource && !exceedsDestination && !isSubmitting)

  async function handleSubmit(event) {
    event.preventDefault()
    if (!canSubmit) {
      return
    }

    setIsSubmitting(true)
    setCreatedMovement(null)
    const movement = await createWorkshopTankLoading(config.endpoint, form)
    setIsSubmitting(false)
    if (movement?.id) {
      setCreatedMovement(movement)
      setForm((current) => ({
        ...current,
        volume_liters: '',
        idempotency_key: createIdempotencyKey(),
      }))
    }
  }

  return (
    <DashboardShell title={title} onLogout={onLogout} user={user}>
      <ProcessingPageHeader
        showEyebrow={Boolean(config.receiver)}
        title={title}
        description={t(config.description)}
      />

      {error && <p className="access-error">{t(error)}</p>}

      <section className="boiler-loading-layout">
        <article className="access-card boiler-loading-form-card">
          <div className="panel-heading">
            <div>
              <p className="auth-eyebrow">{t('Новое движение')}</p>
              <h3>{t('Выберите источник, бак и объём')}</h3>
            </div>
          </div>

          <form className="crud-form boiler-loading-form" onSubmit={handleSubmit}>
            <select
              aria-label={sourceLabel}
              required
              value={selectedSource ? form[sourceField] : ''}
              onChange={(event) => setForm({ ...form, [sourceField]: event.target.value })}
            >
              <option value="">{t(config.receiver ? 'Выберите закрытый ресивер' : 'Выберите реактор')}</option>
              {sources.map((item) => <option key={item.id} value={item.id}>{sourceName(item)}</option>)}
            </select>

            <select
              aria-label={t(config.tankLabel)}
              required
              value={form.destination_tank_id}
              onChange={(event) => setForm({ ...form, destination_tank_id: event.target.value })}
            >
              <option value="">{t('Выберите бак')}</option>
              {availableTanks.map((tank) => (
                <option key={tank.id} value={tank.id}>{t(tank.name)}{t(' · сейчас ')}{formatVolume(tank.current_volume_liters)}</option>
              ))}
            </select>

            <input
              aria-label={t('Объём движения, л')}
              min="0.001"
              placeholder={t('Объем')}
              required
              step="0.001"
              type="number"
              value={form.volume_liters}
              onChange={(event) => setForm({ ...form, volume_liters: event.target.value })}
            />

            {exceedsSource && <p className="access-error">{t('Объём движения превышает вместимость реактора.')}</p>}
            {exceedsDestination && <p className="access-error">{t('Указанный объём превышает свободное место выбранного бака.')}</p>}
            {!sources.length && <p className="empty-state">{t(config.receiver ? 'Нет закрытых ресиверов, готовых к сливу.' : 'Нет активных реакторов переработки.')}</p>}
            {!availableTanks.length && <p className="empty-state">{t('Нет активных баков, доступных для загрузки.')}</p>}

            <div className="form-actions">
              <button disabled={!canSubmit} type="submit">{isSubmitting ? t('Выполняется...') : t(config.receiver ? 'Подтвердить полный слив' : 'Подтвердить движение')}</button>
              <button
                className="secondary-button"
                type="button"
                onClick={() => {
                  setCreatedMovement(null)
                  setForm({
                    [sourceField]: '',
                    destination_tank_id: '',
                    volume_liters: '',
                    idempotency_key: createIdempotencyKey(),
                  })
                }}
              >{t('Очистить')}</button>
            </div>
          </form>
        </article>

        <aside className="boiler-loading-summary">
          <article className="access-card movement-preview-card">
            <p className="auth-eyebrow">{t('Предварительный баланс')}</p>
            <h3>{t('После движения')}</h3>
            <div className="movement-preview-grid">
              <div>
                <span>{sourceLabel}</span>
                <strong>{selectedSource ? sourceName(selectedSource) : t('Не выбран')}</strong>
                {config.receiver && selectedSource && <small>{t('Закрыт')}: {formatDateTime(selectedSource.closed_at, true)}</small>}
              </div>
              <span aria-hidden="true" className="movement-preview-arrow">→</span>
              <div>
                <span>{productName}</span>
                <strong>{t(selectedTank?.name) || t('Не выбран')}</strong>
                <small>{t('Сейчас: ')}{formatVolume(selectedTank?.current_volume_liters)}</small>
                <small>{t('Будет: ')}{selectedTank && hasPositiveVolume ? formatVolume(destinationVolume + volume) : '—'}</small>
              </div>
            </div>
          </article>

          {createdMovement && (
            <article className="access-card movement-success-card">
              <p className="auth-eyebrow">{t('Движение выполнено')}</p>
              <h3>{createdMovement.movement_number}</h3>
              <span>{t(createdMovement.source)} → {t(createdMovement.destination)}</span>
              <strong>{formatVolume(createdMovement.volume_liters)}</strong>
              <small>{formatDateTime(createdMovement.moved_at)}</small>
            </article>
          )}
        </aside>
      </section>
    </DashboardShell>
  )
}

export function ProcessingJournalPage({ onLogout, token, user }) {
  const { compensateMovement, error, fetchJournal, journal } = useProcessingCrud(token, { containerKinds: [], loadJournal: true })
  const [filters, setFilters] = useState(emptyJournalFilters)
  const [selectedEntry, setSelectedEntry] = useState(null)
  const [compensationTarget, setCompensationTarget] = useState(null)
  const [compensationReason, setCompensationReason] = useState('')

  async function applyFilters(event) {
    event.preventDefault()
    await fetchJournal(filters, 1)
  }

  async function changePage(page) {
    await fetchJournal(filters, page)
  }

  async function handleCompensation(event) {
    event.preventDefault()
    const compensated = await compensateMovement(compensationTarget.id, compensationReason)
    if (compensated) {
      setCompensationTarget(null)
      setCompensationReason('')
      await fetchJournal(filters, journal.page)
    }
  }

  return (
    <DashboardShell title={t('Журнал')} onLogout={onLogout} user={user}>
      <ProcessingPageHeader title={t('Журнал операций')} description={t('Движения масла и аудит изменяющих действий первого производственного этапа.')} />
      {error && <p className="access-error">{t(error)}</p>}

      <section className="access-grid">
        <article className="access-card">
          <form className="journal-filters" onSubmit={applyFilters}>
            <input placeholder={t('Поиск')} value={filters.query} onChange={(event) => setFilters({ ...filters, query: event.target.value })} />
            <input aria-label={t('Дата с')} type="date" value={filters.date_from} onChange={(event) => setFilters({ ...filters, date_from: event.target.value })} />
            <input aria-label={t('Дата по')} type="date" value={filters.date_to} onChange={(event) => setFilters({ ...filters, date_to: event.target.value })} />
            <select value={filters.movement_type} onChange={(event) => setFilters({ ...filters, movement_type: event.target.value })}>
              <option value="">{t('Все типы')}</option>
              <option value="receipt_to_tank">{t('Поступление из приёмки')}</option>
              <option value="tank_to_boiler">{t('Загрузка котла')}</option>
              <option value="boiler_to_workshop">{t('Загрузка в цех переработки')}</option>
              <option value="boiler_to_reactor">{t('Загрузка реактора переработки')}</option>
              {workshopTankTransfers.map((config) => <option key={config.movementType} value={config.movementType}>{t(config.label)}</option>)}
              <option value="workshop_to_raw_diesel_tank">{t('Загрузка бака сырой солярки')}</option>
              <option value="workshop_to_raw_spindle_tank">{t('Загрузка бака сырой веретенки')}</option>
              <option value="workshop_to_nigrol_tank">{t('Отгрузка нигрола (прежний маршрут)')}</option>
              {Object.values(oilFinishingForms).map((config) => <option key={config.movementType} value={config.movementType}>{t(config.title)}</option>)}
              <option value="mixer_to_filter">{t('Загрузка финишного фильтра (прежний маршрут)')}</option>
              <option value="filter_to_finished_tank">{t('Загрузка бака готовой продукции (прежний маршрут)')}</option>
              <option value="boiler_to_chemical_mixer">{t('Загрузка химического миксера (прежний маршрут)')}</option>
              <option value="chemical_mixer_to_workshop">{t('Загрузка в цех переработки (прежний маршрут)')}</option>
              <option value="raw_to_finishing_mixer">{t('Загрузка песочного миксера (прежний маршрут)')}</option>
              {Object.entries(oilManufacturingMovements).map(([code, name]) => <option key={code} value={code}>{t(name)}</option>)}
              <option value="compensation">{t('Компенсация')}</option>
            </select>
            <select value={filters.status} onChange={(event) => setFilters({ ...filters, status: event.target.value })}>
              <option value="">{t('Все состояния')}</option>
              <option value="confirmed">{t('Подтверждено')}</option>
              <option value="success">{t('Успешно')}</option>
              <option value="rejected">{t('Отклонено')}</option>
            </select>
            <input placeholder={t('Источник')} value={filters.source} onChange={(event) => setFilters({ ...filters, source: event.target.value })} />
            <input placeholder={t('Получатель')} value={filters.destination} onChange={(event) => setFilters({ ...filters, destination: event.target.value })} />
            <input placeholder={t('Пользователь')} value={filters.user} onChange={(event) => setFilters({ ...filters, user: event.target.value })} />
            <input placeholder={t('Номер движения')} value={filters.number} onChange={(event) => setFilters({ ...filters, number: event.target.value })} />
            <input min="0.001" placeholder={t('Объём')} step="0.001" type="number" value={filters.volume} onChange={(event) => setFilters({ ...filters, volume: event.target.value })} />
            <div className="form-actions">
              <button type="submit">{t('Применить')}</button>
              <button className="secondary-button" type="button" onClick={() => { setFilters(emptyJournalFilters); fetchJournal({}, 1) }}>{t('Сбросить')}</button>
            </div>
          </form>

          <div className="entity-list">
            {journal.items.map((item) => (
              <div className="entity-row journal-row" key={`${item.entry_type}-${item.id}`}>
                <div>
                  <strong>{item.entry_type === 'movement' ? item.movement_number : t(item.action)}</strong>
                  {item.entry_type === 'movement' ? (
                    <>
                      <span>{t(item.movement_type_label)} · {formatVolume(item.volume_liters)}</span>
                      <span>{t(item.source) || '—'} → {t(item.destination) || '—'}</span>
                      <span>{formatDateTime(item.moved_at)} · {item.created_by || t('Система')}</span>
                    </>
                  ) : (
                    <>
                      <span>{t(item.object_type)} #{item.object_id || '—'} · {t(item.result)}</span>
                      <span>{formatDateTime(item.created_at)} · {item.user || t('Система')}</span>
                    </>
                  )}
                </div>
                <div className="row-actions">
                  <button type="button" onClick={() => setSelectedEntry(item)}>{t('Подробнее')}</button>
                  {item.entry_type === 'movement' && item.can_compensate && (
                    <button className="danger-button" type="button" onClick={() => setCompensationTarget(item)}>{t('Компенсировать')}</button>
                  )}
                </div>
              </div>
            ))}
            {!journal.items.length && <p className="empty-state">{t('Записи не найдены.')}</p>}
          </div>

          <div className="list-pagination journal-pagination">
            <span>{journal.total}{t(' записей')}</span>
            <div className="pagination-actions">
              <button className="secondary-button" disabled={journal.page <= 1} type="button" onClick={() => changePage(journal.page - 1)}>{t('Назад')}</button>
              <strong>{journal.page} / {journal.page_count}</strong>
              <button className="secondary-button" disabled={journal.page >= journal.page_count} type="button" onClick={() => changePage(journal.page + 1)}>{t('Вперёд')}</button>
            </div>
          </div>
        </article>
      </section>

      {selectedEntry && (
        <Modal title={t('Детали записи')} onClose={() => setSelectedEntry(null)}>
          <pre className="journal-details">{JSON.stringify(localizeAuditEntry(selectedEntry), null, 2)}</pre>
        </Modal>
      )}

      {compensationTarget && (
        <Modal title={t('Компенсировать движение')} onClose={() => setCompensationTarget(null)}>
          <form className="crud-form" onSubmit={handleCompensation}>
            <p>{t('Будет создано отдельное обратное движение для ')}{compensationTarget.movement_number}.</p>
            <label>
              <span>{t('Причина')}</span>
              <textarea required value={compensationReason} onChange={(event) => setCompensationReason(event.target.value)} />
            </label>
            <div className="form-actions">
              <button className="danger-button" type="submit">{t('Создать компенсацию')}</button>
              <button className="secondary-button" type="button" onClick={() => setCompensationTarget(null)}>{t('Отмена')}</button>
            </div>
          </form>
        </Modal>
      )}
    </DashboardShell>
  )
}
