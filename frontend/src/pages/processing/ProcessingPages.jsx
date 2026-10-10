import { getLocale, t } from '../../i18n/core'
import { localizeAuditEntry } from '../../i18n/audit'
import { useState } from 'react'
import { DashboardShell } from '../../components/Layout/DashboardShell'
import { ListControls } from '../../components/ListControls/ListControls'
import { DeleteConfirmModal, Modal } from '../../components/Modal/Modal'
import { useListControls } from '../../hooks/useListControls'
import { useProcessingCrud } from '../../hooks/useProcessingCrud'

const emptyContainerForm = {
  id: null,
  kind: 'receiving_tank',
  number: '',
  capacity_liters: '',
  is_active: true,
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

function ProcessingPageHeader({ description, title }) {
  return (
    <section className="page-title access-page-title">
      <p className="auth-eyebrow">{t('Переработка отработанного масла')}</p>
      <h1>{title}</h1>
      <p>{description}</p>
    </section>
  )
}

function formatDateTime(value) {
  if (!value) {
    return '—'
  }
  return new Intl.DateTimeFormat(getLocale(), {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(value))
}

function formatVolume(value) {
  if (value === '' || value === null || value === undefined) {
    return '—'
  }
  return t`${Number(value).toLocaleString(getLocale(), { minimumFractionDigits: 3, maximumFractionDigits: 3 })} л`
}

function createIdempotencyKey() {
  return globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}`
}

function ContainerPage({ kind, onLogout, token, user }) {
  const isAdmin = Boolean(user?.is_admin)
  const { boilers, chemicalMixers, deleteContainer, error, processingWorkshops, rawDieselTanks, rawSpindleTanks, receivingTanks, saveContainer, separators } = useProcessingCrud(token, { containerKinds: [kind] })
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
    separator: {
      containers: separators,
      description: t('Учёт вместимости, текущего объёма и доступности сепараторов.'),
      title: t('Сепараторы'),
    },
    chemical_mixer: {
      containers: chemicalMixers,
      description: t('Учёт вместимости, текущего объёма и доступности химических миксеров.'),
      title: t('Химические миксеры'),
    },
    processing_workshop: {
      containers: processingWorkshops,
      description: t('Учёт вместимости, текущего объёма и доступности цехов переработки.'),
      title: t('Цеха переработки'),
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
  }[kind]
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
              <p className="auth-eyebrow">{t('Ёмкости')}</p>
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
                  <span>{t('Текущий объём: ')}{formatVolume(item.current_volume_liters)}</span>
                  {isAdmin && (
                    <>
                      <span>{t('Вместимость: ')}{formatVolume(item.capacity_liters)}{t(' · Свободно: ')}{formatVolume(item.free_volume_liters)}</span>
                      <span>{t('Заполнение: ')}{item.fill_percentage}{t('% · Последнее движение: ')}{formatDateTime(item.last_movement_at)}</span>
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
            {!containers.length && <p className="empty-state">{t('Ёмкости пока не созданы.')}</p>}
            {Boolean(containers.length) && !controls.filteredCount && <p className="empty-state">{t('По вашему запросу ничего не найдено.')}</p>}
          </div>
        </article>
      </section>

      {isContainerFormOpen && (
        <Modal title={containerForm.id ? t('Изменить ёмкость') : t('Новая ёмкость')} onClose={() => setIsContainerFormOpen(false)}>
          <form className="crud-form" onSubmit={handleContainerSubmit}>
            <label>
              <span>{t('Номер')}</span>
              <input min="1" required type="number" value={containerForm.number} onChange={(event) => setContainerForm({ ...containerForm, number: event.target.value })} />
            </label>
            <label>
              <span>{t('Вместимость, л')}</span>
              <input min="1" required step="1" type="number" value={containerForm.capacity_liters} onChange={(event) => setContainerForm({ ...containerForm, capacity_liters: event.target.value })} />
            </label>
            <label className="checkbox-row">
              <input checked={containerForm.is_active} type="checkbox" onChange={(event) => setContainerForm({ ...containerForm, is_active: event.target.checked })} />{t('Активна')}</label>
            <div className="form-actions">
              <button type="submit">{containerForm.id ? t('Сохранить') : t('Создать')}</button>
              <button className="secondary-button" type="button" onClick={() => setIsContainerFormOpen(false)}>{t('Отмена')}</button>
            </div>
          </form>
        </Modal>
      )}

      {deleteTarget && (
        <DeleteConfirmModal
          entityName={t('ёмкость')}
          itemName={t(deleteTarget.name)}
          onCancel={() => setDeleteTarget(null)}
          onConfirm={handleDelete}
        />
      )}
    </DashboardShell>
  )
}

export function ReceivingTanksPage(props) {
  return <ContainerPage {...props} kind="receiving_tank" />
}

export function PreheatingBoilersPage(props) {
  return <ContainerPage {...props} kind="preheating_boiler" />
}

export function SeparatorsPage(props) {
  return <ContainerPage {...props} kind="separator" />
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
            <label>
              <span>{t('Приёмный бак')}</span>
              <select required value={form.source_tank_id} onChange={(event) => setForm({ ...form, source_tank_id: event.target.value })}>
                <option value="">{t('Выберите приёмный бак')}</option>
                {availableTanks.map((tank) => (
                  <option key={tank.id} value={tank.id}>{t(tank.name)}{t(' · доступно ')}{formatVolume(tank.current_volume_liters)}</option>
                ))}
              </select>
            </label>

            <label>
              <span>{t('Котёл первичного прогрева')}</span>
              <select required value={form.destination_boiler_id} onChange={(event) => setForm({ ...form, destination_boiler_id: event.target.value })}>
                <option value="">{t('Выберите котёл')}</option>
                {availableBoilers.map((boiler) => (
                  <option key={boiler.id} value={boiler.id}>{t(boiler.name)}{t(' · сейчас ')}{formatVolume(boiler.current_volume_liters)}</option>
                ))}
              </select>
            </label>

            <label>
              <span>{t('Объём движения, л')}</span>
              <input
                min="0.001"
                placeholder="0.000"
                required
                step="0.001"
                type="number"
                value={form.volume_liters}
                onChange={(event) => setForm({ ...form, volume_liters: event.target.value })}
              />
            </label>

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

export function SeparatorLoadingPage({ onLogout, token, user }) {
  const { boilers, createBoilerToSeparatorMovement, error, separators } = useProcessingCrud(token, { containerKinds: ['preheating_boiler', 'separator'] })
  const [form, setForm] = useState(() => ({
    source_boiler_id: '',
    destination_separator_id: '',
    volume_liters: '',
    idempotency_key: createIdempotencyKey(),
  }))
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [createdMovement, setCreatedMovement] = useState(null)
  const availableBoilers = boilers.filter((boiler) => boiler.is_active && Number(boiler.current_volume_liters) > 0)
  const availableSeparators = separators.filter((separator) => separator.is_active && separator.can_receive)
  const selectedBoiler = boilers.find((boiler) => String(boiler.id) === String(form.source_boiler_id))
  const selectedSeparator = separators.find((separator) => String(separator.id) === String(form.destination_separator_id))
  const volume = Number(form.volume_liters)
  const sourceVolume = Number(selectedBoiler?.current_volume_liters || 0)
  const destinationVolume = Number(selectedSeparator?.current_volume_liters || 0)
  const destinationFreeVolume = selectedSeparator?.free_volume_liters === undefined
    ? null
    : Number(selectedSeparator.free_volume_liters)
  const hasPositiveVolume = Number.isFinite(volume) && volume > 0
  const exceedsSource = hasPositiveVolume && volume > sourceVolume
  const exceedsDestination = hasPositiveVolume && destinationFreeVolume !== null && volume > destinationFreeVolume
  const canSubmit = Boolean(selectedBoiler && selectedSeparator && hasPositiveVolume && !exceedsSource && !exceedsDestination && !isSubmitting)

  async function handleSubmit(event) {
    event.preventDefault()
    if (!canSubmit) {
      return
    }

    setIsSubmitting(true)
    setCreatedMovement(null)
    const movement = await createBoilerToSeparatorMovement(form)
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
    <DashboardShell title={t('Загрузка сепаратора')} onLogout={onLogout} user={user}>
      <ProcessingPageHeader
        title={t('Загрузка сепаратора')}
        description={t('Регистрация движения отработанного масла из котла первичного прогрева в сепаратор.')}
      />

      {error && <p className="access-error">{t(error)}</p>}

      <section className="boiler-loading-layout">
        <article className="access-card boiler-loading-form-card">
          <div className="panel-heading">
            <div>
              <p className="auth-eyebrow">{t('Новое движение')}</p>
              <h3>{t('Выберите котёл, сепаратор и объём')}</h3>
            </div>
          </div>

          <form className="crud-form boiler-loading-form" onSubmit={handleSubmit}>
            <label>
              <span>{t('Котёл первичного прогрева')}</span>
              <select required value={form.source_boiler_id} onChange={(event) => setForm({ ...form, source_boiler_id: event.target.value })}>
                <option value="">{t('Выберите котёл')}</option>
                {availableBoilers.map((boiler) => (
                  <option key={boiler.id} value={boiler.id}>{t(boiler.name)}{t(' · доступно ')}{formatVolume(boiler.current_volume_liters)}</option>
                ))}
              </select>
            </label>

            <label>
              <span>{t('Сепаратор')}</span>
              <select required value={form.destination_separator_id} onChange={(event) => setForm({ ...form, destination_separator_id: event.target.value })}>
                <option value="">{t('Выберите сепаратор')}</option>
                {availableSeparators.map((separator) => (
                  <option key={separator.id} value={separator.id}>{t(separator.name)}{t(' · сейчас ')}{formatVolume(separator.current_volume_liters)}</option>
                ))}
              </select>
            </label>

            <label>
              <span>{t('Объём движения, л')}</span>
              <input
                min="0.001"
                placeholder="0.000"
                required
                step="0.001"
                type="number"
                value={form.volume_liters}
                onChange={(event) => setForm({ ...form, volume_liters: event.target.value })}
              />
            </label>

            {exceedsSource && <p className="access-error">{t('Указанный объём превышает остаток выбранного котла.')}</p>}
            {exceedsDestination && <p className="access-error">{t('Указанный объём превышает свободное место сепаратора.')}</p>}
            {!availableBoilers.length && <p className="empty-state">{t('Нет активных котлов с доступным маслом.')}</p>}
            {!availableSeparators.length && <p className="empty-state">{t('Нет активных сепараторов, доступных для загрузки.')}</p>}

            <div className="form-actions">
              <button disabled={!canSubmit} type="submit">{isSubmitting ? t('Выполняется...') : t('Подтвердить движение')}</button>
              <button
                className="secondary-button"
                type="button"
                onClick={() => {
                  setCreatedMovement(null)
                  setForm({
                    source_boiler_id: '',
                    destination_separator_id: '',
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
                <span>{t('Котёл')}</span>
                <strong>{t(selectedBoiler?.name) || t('Не выбран')}</strong>
                <small>{t('Сейчас: ')}{formatVolume(selectedBoiler?.current_volume_liters)}</small>
                <small>{t('Останется: ')}{selectedBoiler && hasPositiveVolume && !exceedsSource ? formatVolume(sourceVolume - volume) : '—'}</small>
              </div>
              <span aria-hidden="true" className="movement-preview-arrow">→</span>
              <div>
                <span>{t('Сепаратор')}</span>
                <strong>{t(selectedSeparator?.name) || t('Не выбран')}</strong>
                <small>{t('Сейчас: ')}{formatVolume(selectedSeparator?.current_volume_liters)}</small>
                <small>{t('Будет: ')}{selectedSeparator && hasPositiveVolume ? formatVolume(destinationVolume + volume) : '—'}</small>
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

export function ChemicalMixerLoadingPage({ onLogout, token, user }) {
  const { chemicalMixers, createChemicalMixerLoading, error, separators } = useProcessingCrud(token, { containerKinds: ['separator', 'chemical_mixer'] })
  const [form, setForm] = useState(() => ({
    source_separator_id: '',
    destination_mixer_id: '',
    volume_liters: '',
    idempotency_key: createIdempotencyKey(),
  }))
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [createdMovement, setCreatedMovement] = useState(null)
  const availableSeparators = separators.filter((separator) => separator.is_active && Number(separator.current_volume_liters) > 0)
  const availableMixers = chemicalMixers.filter((mixer) => mixer.is_active && mixer.can_receive)
  const selectedSeparator = separators.find((separator) => String(separator.id) === String(form.source_separator_id))
  const selectedMixer = chemicalMixers.find((mixer) => String(mixer.id) === String(form.destination_mixer_id))
  const volume = Number(form.volume_liters)
  const sourceVolume = Number(selectedSeparator?.current_volume_liters || 0)
  const destinationVolume = Number(selectedMixer?.current_volume_liters || 0)
  const destinationFreeVolume = selectedMixer?.free_volume_liters === undefined
    ? null
    : Number(selectedMixer.free_volume_liters)
  const hasPositiveVolume = Number.isFinite(volume) && volume > 0
  const exceedsSource = hasPositiveVolume && volume > sourceVolume
  const exceedsDestination = hasPositiveVolume && destinationFreeVolume !== null && volume > destinationFreeVolume
  const canSubmit = Boolean(selectedSeparator && selectedMixer && hasPositiveVolume && !exceedsSource && !exceedsDestination && !isSubmitting)

  async function handleSubmit(event) {
    event.preventDefault()
    if (!canSubmit) {
      return
    }

    setIsSubmitting(true)
    setCreatedMovement(null)
    const movement = await createChemicalMixerLoading(form)
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
    <DashboardShell title={t('Загрузка химического миксера')} onLogout={onLogout} user={user}>
      <ProcessingPageHeader
        title={t('Загрузка химического миксера')}
        description={t('Регистрация движения очищенного отработанного масла из сепаратора в химический миксер.')}
      />

      {error && <p className="access-error">{t(error)}</p>}

      <section className="boiler-loading-layout">
        <article className="access-card boiler-loading-form-card">
          <div className="panel-heading">
            <div>
              <p className="auth-eyebrow">{t('Новое движение')}</p>
              <h3>{t('Выберите сепаратор, миксер и объём')}</h3>
            </div>
          </div>

          <form className="crud-form boiler-loading-form" onSubmit={handleSubmit}>
            <label>
              <span>{t('Сепаратор')}</span>
              <select required value={form.source_separator_id} onChange={(event) => setForm({ ...form, source_separator_id: event.target.value })}>
                <option value="">{t('Выберите сепаратор')}</option>
                {availableSeparators.map((separator) => (
                  <option key={separator.id} value={separator.id}>{t(separator.name)}{t(' · доступно ')}{formatVolume(separator.current_volume_liters)}</option>
                ))}
              </select>
            </label>

            <label>
              <span>{t('Химический миксер')}</span>
              <select required value={form.destination_mixer_id} onChange={(event) => setForm({ ...form, destination_mixer_id: event.target.value })}>
                <option value="">{t('Выберите химический миксер')}</option>
                {availableMixers.map((mixer) => (
                  <option key={mixer.id} value={mixer.id}>{t(mixer.name)}{t(' · сейчас ')}{formatVolume(mixer.current_volume_liters)}</option>
                ))}
              </select>
            </label>

            <label>
              <span>{t('Объём движения, л')}</span>
              <input
                min="0.001"
                placeholder="0.000"
                required
                step="0.001"
                type="number"
                value={form.volume_liters}
                onChange={(event) => setForm({ ...form, volume_liters: event.target.value })}
              />
            </label>

            {exceedsSource && <p className="access-error">{t('Указанный объём превышает остаток выбранного сепаратора.')}</p>}
            {exceedsDestination && <p className="access-error">{t('Указанный объём превышает свободное место химического миксера.')}</p>}
            {!availableSeparators.length && <p className="empty-state">{t('Нет активных сепараторов с доступным маслом.')}</p>}
            {!availableMixers.length && <p className="empty-state">{t('Нет активных химических миксеров, доступных для загрузки.')}</p>}

            <div className="form-actions">
              <button disabled={!canSubmit} type="submit">{isSubmitting ? t('Выполняется...') : t('Подтвердить движение')}</button>
              <button
                className="secondary-button"
                type="button"
                onClick={() => {
                  setCreatedMovement(null)
                  setForm({
                    source_separator_id: '',
                    destination_mixer_id: '',
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
                <span>{t('Сепаратор')}</span>
                <strong>{t(selectedSeparator?.name) || t('Не выбран')}</strong>
                <small>{t('Сейчас: ')}{formatVolume(selectedSeparator?.current_volume_liters)}</small>
                <small>{t('Останется: ')}{selectedSeparator && hasPositiveVolume && !exceedsSource ? formatVolume(sourceVolume - volume) : '—'}</small>
              </div>
              <span aria-hidden="true" className="movement-preview-arrow">→</span>
              <div>
                <span>{t('Химический миксер')}</span>
                <strong>{t(selectedMixer?.name) || t('Не выбран')}</strong>
                <small>{t('Сейчас: ')}{formatVolume(selectedMixer?.current_volume_liters)}</small>
                <small>{t('Будет: ')}{selectedMixer && hasPositiveVolume ? formatVolume(destinationVolume + volume) : '—'}</small>
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
  const { chemicalMixers, createWorkshopLoading, error, processingWorkshops } = useProcessingCrud(token, { containerKinds: ['chemical_mixer', 'processing_workshop'] })
  const [form, setForm] = useState(() => ({
    source_mixer_id: '',
    destination_workshop_id: '',
    volume_liters: '',
    idempotency_key: createIdempotencyKey(),
  }))
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [createdMovement, setCreatedMovement] = useState(null)
  const availableMixers = chemicalMixers.filter((mixer) => mixer.is_active && Number(mixer.current_volume_liters) > 0)
  const availableWorkshops = processingWorkshops.filter((workshop) => workshop.is_active && workshop.can_receive)
  const selectedMixer = chemicalMixers.find((mixer) => String(mixer.id) === String(form.source_mixer_id))
  const selectedWorkshop = processingWorkshops.find((workshop) => String(workshop.id) === String(form.destination_workshop_id))
  const volume = Number(form.volume_liters)
  const sourceVolume = Number(selectedMixer?.current_volume_liters || 0)
  const destinationVolume = Number(selectedWorkshop?.current_volume_liters || 0)
  const destinationFreeVolume = selectedWorkshop?.free_volume_liters === undefined
    ? null
    : Number(selectedWorkshop.free_volume_liters)
  const hasPositiveVolume = Number.isFinite(volume) && volume > 0
  const exceedsSource = hasPositiveVolume && volume > sourceVolume
  const exceedsDestination = hasPositiveVolume && destinationFreeVolume !== null && volume > destinationFreeVolume
  const canSubmit = Boolean(selectedMixer && selectedWorkshop && hasPositiveVolume && !exceedsSource && !exceedsDestination && !isSubmitting)

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
    <DashboardShell title={t('Загрузка в цех переработки')} onLogout={onLogout} user={user}>
      <ProcessingPageHeader
        title={t('Загрузка в цех переработки')}
        description={t('Регистрация движения химически подготовленного масла из химического миксера в цех переработки.')}
      />

      {error && <p className="access-error">{t(error)}</p>}

      <section className="boiler-loading-layout">
        <article className="access-card boiler-loading-form-card">
          <div className="panel-heading">
            <div>
              <p className="auth-eyebrow">{t('Новое движение')}</p>
              <h3>{t('Выберите миксер, цех и объём')}</h3>
            </div>
          </div>

          <form className="crud-form boiler-loading-form" onSubmit={handleSubmit}>
            <label>
              <span>{t('Химический миксер')}</span>
              <select required value={form.source_mixer_id} onChange={(event) => setForm({ ...form, source_mixer_id: event.target.value })}>
                <option value="">{t('Выберите химический миксер')}</option>
                {availableMixers.map((mixer) => (
                  <option key={mixer.id} value={mixer.id}>{t(mixer.name)}{t(' · доступно ')}{formatVolume(mixer.current_volume_liters)}</option>
                ))}
              </select>
            </label>

            <label>
              <span>{t('Цех переработки')}</span>
              <select required value={form.destination_workshop_id} onChange={(event) => setForm({ ...form, destination_workshop_id: event.target.value })}>
                <option value="">{t('Выберите цех переработки')}</option>
                {availableWorkshops.map((workshop) => (
                  <option key={workshop.id} value={workshop.id}>{t(workshop.name)}{t(' · сейчас ')}{formatVolume(workshop.current_volume_liters)}</option>
                ))}
              </select>
            </label>

            <label>
              <span>{t('Объём движения, л')}</span>
              <input
                min="0.001"
                placeholder="0.000"
                required
                step="0.001"
                type="number"
                value={form.volume_liters}
                onChange={(event) => setForm({ ...form, volume_liters: event.target.value })}
              />
            </label>

            {exceedsSource && <p className="access-error">{t('Указанный объём превышает остаток выбранного химического миксера.')}</p>}
            {exceedsDestination && <p className="access-error">{t('Указанный объём превышает свободное место цеха переработки.')}</p>}
            {!availableMixers.length && <p className="empty-state">{t('Нет активных химических миксеров с доступным маслом.')}</p>}
            {!availableWorkshops.length && <p className="empty-state">{t('Нет активных цехов переработки, доступных для загрузки.')}</p>}

            <div className="form-actions">
              <button disabled={!canSubmit} type="submit">{isSubmitting ? t('Выполняется...') : t('Подтвердить движение')}</button>
              <button
                className="secondary-button"
                type="button"
                onClick={() => {
                  setCreatedMovement(null)
                  setForm({
                    source_mixer_id: '',
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
                <span>{t('Химический миксер')}</span>
                <strong>{t(selectedMixer?.name) || t('Не выбран')}</strong>
                <small>{t('Сейчас: ')}{formatVolume(selectedMixer?.current_volume_liters)}</small>
                <small>{t('Останется: ')}{selectedMixer && hasPositiveVolume && !exceedsSource ? formatVolume(sourceVolume - volume) : '—'}</small>
              </div>
              <span aria-hidden="true" className="movement-preview-arrow">→</span>
              <div>
                <span>{t('Цех переработки')}</span>
                <strong>{t(selectedWorkshop?.name) || t('Не выбран')}</strong>
                <small>{t('Сейчас: ')}{formatVolume(selectedWorkshop?.current_volume_liters)}</small>
                <small>{t('Будет: ')}{selectedWorkshop && hasPositiveVolume ? formatVolume(destinationVolume + volume) : '—'}</small>
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

function RawProductTankLoadingPage({ onLogout, productType, token, user }) {
  const {
    createRawDieselTankLoading,
    createRawSpindleTankLoading,
    error,
    processingWorkshops,
    rawDieselTanks,
    rawSpindleTanks,
  } = useProcessingCrud(token, {
    containerKinds: ['processing_workshop', productType === 'diesel' ? 'raw_diesel_tank' : 'raw_spindle_tank'],
  })
  const isDiesel = productType === 'diesel'
  const tanks = isDiesel ? rawDieselTanks : rawSpindleTanks
  const createMovement = isDiesel ? createRawDieselTankLoading : createRawSpindleTankLoading
  const title = isDiesel ? t('Загрузка бака сырой солярки') : t('Загрузка бака сырой веретенки')
  const productName = isDiesel ? t('Сырая солярка') : t('Сырая веретенка')
  const [form, setForm] = useState(() => ({
    source_workshop_id: '',
    destination_tank_id: '',
    volume_liters: '',
    idempotency_key: createIdempotencyKey(),
  }))
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [createdMovement, setCreatedMovement] = useState(null)
  const availableWorkshops = processingWorkshops.filter((workshop) => workshop.is_active && Number(workshop.current_volume_liters) > 0)
  const availableTanks = tanks.filter((tank) => tank.is_active && tank.can_receive)
  const selectedWorkshop = processingWorkshops.find((workshop) => String(workshop.id) === String(form.source_workshop_id))
  const selectedTank = tanks.find((tank) => String(tank.id) === String(form.destination_tank_id))
  const volume = Number(form.volume_liters)
  const sourceVolume = Number(selectedWorkshop?.current_volume_liters || 0)
  const destinationVolume = Number(selectedTank?.current_volume_liters || 0)
  const destinationFreeVolume = selectedTank?.free_volume_liters === undefined
    ? null
    : Number(selectedTank.free_volume_liters)
  const hasPositiveVolume = Number.isFinite(volume) && volume > 0
  const exceedsSource = hasPositiveVolume && volume > sourceVolume
  const exceedsDestination = hasPositiveVolume && destinationFreeVolume !== null && volume > destinationFreeVolume
  const canSubmit = Boolean(selectedWorkshop && selectedTank && hasPositiveVolume && !exceedsSource && !exceedsDestination && !isSubmitting)

  async function handleSubmit(event) {
    event.preventDefault()
    if (!canSubmit) {
      return
    }

    setIsSubmitting(true)
    setCreatedMovement(null)
    const movement = await createMovement(form)
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
        title={title}
        description={t`Регистрация движения продукта «${productName}» из цеха переработки в отдельный бак.`}
      />

      {error && <p className="access-error">{t(error)}</p>}

      <section className="boiler-loading-layout">
        <article className="access-card boiler-loading-form-card">
          <div className="panel-heading">
            <div>
              <p className="auth-eyebrow">{t('Новое движение')}</p>
              <h3>{t('Выберите цех, бак и объём')}</h3>
            </div>
          </div>

          <form className="crud-form boiler-loading-form" onSubmit={handleSubmit}>
            <label>
              <span>{t('Цех переработки')}</span>
              <select required value={form.source_workshop_id} onChange={(event) => setForm({ ...form, source_workshop_id: event.target.value })}>
                <option value="">{t('Выберите цех переработки')}</option>
                {availableWorkshops.map((workshop) => (
                  <option key={workshop.id} value={workshop.id}>{t(workshop.name)}{t(' · доступно ')}{formatVolume(workshop.current_volume_liters)}</option>
                ))}
              </select>
            </label>

            <label>
              <span>{isDiesel ? t('Бак сырой солярки') : t('Бак сырой веретенки')}</span>
              <select required value={form.destination_tank_id} onChange={(event) => setForm({ ...form, destination_tank_id: event.target.value })}>
                <option value="">{t('Выберите бак')}</option>
                {availableTanks.map((tank) => (
                  <option key={tank.id} value={tank.id}>{t(tank.name)}{t(' · сейчас ')}{formatVolume(tank.current_volume_liters)}</option>
                ))}
              </select>
            </label>

            <label>
              <span>{t('Объём движения, л')}</span>
              <input
                min="0.001"
                placeholder="0.000"
                required
                step="0.001"
                type="number"
                value={form.volume_liters}
                onChange={(event) => setForm({ ...form, volume_liters: event.target.value })}
              />
            </label>

            {exceedsSource && <p className="access-error">{t('Указанный объём превышает остаток выбранного цеха.')}</p>}
            {exceedsDestination && <p className="access-error">{t('Указанный объём превышает свободное место выбранного бака.')}</p>}
            {!availableWorkshops.length && <p className="empty-state">{t('Нет активных цехов с доступным продуктом.')}</p>}
            {!availableTanks.length && <p className="empty-state">{t('Нет активных баков, доступных для загрузки.')}</p>}

            <div className="form-actions">
              <button disabled={!canSubmit} type="submit">{isSubmitting ? t('Выполняется...') : t('Подтвердить движение')}</button>
              <button
                className="secondary-button"
                type="button"
                onClick={() => {
                  setCreatedMovement(null)
                  setForm({
                    source_workshop_id: '',
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
                <span>{t('Цех переработки')}</span>
                <strong>{t(selectedWorkshop?.name) || t('Не выбран')}</strong>
                <small>{t('Сейчас: ')}{formatVolume(selectedWorkshop?.current_volume_liters)}</small>
                <small>{t('Останется: ')}{selectedWorkshop && hasPositiveVolume && !exceedsSource ? formatVolume(sourceVolume - volume) : '—'}</small>
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

export function RawDieselTankLoadingPage(props) {
  return <RawProductTankLoadingPage {...props} productType="diesel" />
}

export function RawSpindleTankLoadingPage(props) {
  return <RawProductTankLoadingPage {...props} productType="spindle" />
}

export function SeparatorOutputPage({ onLogout, token, user }) {
  const { createSeparatorOutputMovement, error, separators } = useProcessingCrud(token, { containerKinds: ['separator'] })
  const [form, setForm] = useState(() => ({
    source_separator_id: '',
    output_type: 'water',
    volume_liters: '',
    idempotency_key: createIdempotencyKey(),
  }))
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [createdMovement, setCreatedMovement] = useState(null)
  const availableSeparators = separators.filter((separator) => separator.is_active && Number(separator.current_volume_liters) > 0)
  const selectedSeparator = separators.find((separator) => String(separator.id) === String(form.source_separator_id))
  const volume = Number(form.volume_liters)
  const sourceVolume = Number(selectedSeparator?.current_volume_liters || 0)
  const hasPositiveVolume = Number.isFinite(volume) && volume > 0
  const exceedsSource = hasPositiveVolume && volume > sourceVolume
  const canSubmit = Boolean(selectedSeparator && hasPositiveVolume && !exceedsSource && !isSubmitting)

  async function handleSubmit(event) {
    event.preventDefault()
    if (!canSubmit) {
      return
    }

    setIsSubmitting(true)
    setCreatedMovement(null)
    const movement = await createSeparatorOutputMovement(form)
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
    <DashboardShell title={t('Отгрузка сепаратора')} onLogout={onLogout} user={user}>
      <ProcessingPageHeader
        title={t('Отгрузка сепаратора')}
        description={t('Регистрация отгрузки технической воды или технического мусора из сепаратора. Топливный выход здесь не учитывается.')}
      />

      {error && <p className="access-error">{t(error)}</p>}

      <section className="boiler-loading-layout">
        <article className="access-card boiler-loading-form-card">
          <div className="panel-heading">
            <div>
              <p className="auth-eyebrow">{t('Новая отгрузка')}</p>
              <h3>{t('Выберите сепаратор, вид отхода и объём')}</h3>
            </div>
          </div>

          <form className="crud-form boiler-loading-form" onSubmit={handleSubmit}>
            <label>
              <span>{t('Сепаратор')}</span>
              <select required value={form.source_separator_id} onChange={(event) => setForm({ ...form, source_separator_id: event.target.value })}>
                <option value="">{t('Выберите сепаратор')}</option>
                {availableSeparators.map((separator) => (
                  <option key={separator.id} value={separator.id}>{t(separator.name)}{t(' · доступно ')}{formatVolume(separator.current_volume_liters)}</option>
                ))}
              </select>
            </label>

            <fieldset className="separator-output-options">
              <legend>{t('Что отгружается')}</legend>
              <div className="unit-radio-group" role="radiogroup" aria-label={t('Вид отгрузки сепаратора')}>
                {[
                  ['water', t('Техническая вода')],
                  ['technical_waste', t('Технический мусор')],
                ].map(([value, label]) => (
                  <label className={form.output_type === value ? 'active' : ''} key={value}>
                    <input
                      checked={form.output_type === value}
                      name="separator-output-type"
                      type="radio"
                      value={value}
                      onChange={(event) => setForm({ ...form, output_type: event.target.value })}
                    />
                    {label}
                  </label>
                ))}
              </div>
            </fieldset>

            <label>
              <span>{t('Объём отгрузки, л')}</span>
              <input
                min="0.001"
                placeholder="0.000"
                required
                step="0.001"
                type="number"
                value={form.volume_liters}
                onChange={(event) => setForm({ ...form, volume_liters: event.target.value })}
              />
            </label>

            {exceedsSource && <p className="access-error">{t('Указанный объём превышает остаток выбранного сепаратора.')}</p>}
            {!availableSeparators.length && <p className="empty-state">{t('Нет активных сепараторов с доступным объёмом.')}</p>}

            <div className="form-actions">
              <button disabled={!canSubmit} type="submit">{isSubmitting ? t('Выполняется...') : t('Подтвердить отгрузку')}</button>
              <button
                className="secondary-button"
                type="button"
                onClick={() => {
                  setCreatedMovement(null)
                  setForm({
                    source_separator_id: '',
                    output_type: 'water',
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
            <h3>{t('После отгрузки')}</h3>
            <div className="movement-preview-grid">
              <div>
                <span>{t('Сепаратор')}</span>
                <strong>{t(selectedSeparator?.name) || t('Не выбран')}</strong>
                <small>{t('Сейчас: ')}{formatVolume(selectedSeparator?.current_volume_liters)}</small>
                <small>{t('Останется: ')}{selectedSeparator && hasPositiveVolume && !exceedsSource ? formatVolume(sourceVolume - volume) : '—'}</small>
              </div>
              <span aria-hidden="true" className="movement-preview-arrow">→</span>
              <div>
                <span>{t('Отгрузка')}</span>
                <strong>{form.output_type === 'water' ? t('Техническая вода') : t('Технический мусор')}</strong>
                <small>{t('Объём: ')}{hasPositiveVolume ? formatVolume(volume) : '—'}</small>
              </div>
            </div>
          </article>

          {createdMovement && (
            <article className="access-card movement-success-card">
              <p className="auth-eyebrow">{t('Отгрузка выполнена')}</p>
              <h3>{createdMovement.movement_number}</h3>
              <span>{t(createdMovement.source)} → {t(createdMovement.product_name)}</span>
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
              <option value="boiler_to_separator">{t('Загрузка сепаратора')}</option>
              <option value="separator_output">{t('Отгрузка сепаратора')}</option>
              <option value="separator_to_chemical_mixer">{t('Загрузка химического миксера')}</option>
              <option value="chemical_mixer_to_workshop">{t('Загрузка в цех переработки')}</option>
              <option value="workshop_to_raw_diesel_tank">{t('Загрузка бака сырой солярки')}</option>
              <option value="workshop_to_raw_spindle_tank">{t('Загрузка бака сырой веретенки')}</option>
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
