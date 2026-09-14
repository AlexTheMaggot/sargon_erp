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
      <p className="auth-eyebrow">Переработка отработанного масла</p>
      <h1>{title}</h1>
      <p>{description}</p>
    </section>
  )
}

function formatDateTime(value) {
  if (!value) {
    return '—'
  }
  return new Intl.DateTimeFormat('ru-RU', {
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
  return `${Number(value).toLocaleString('ru-RU', { minimumFractionDigits: 3, maximumFractionDigits: 3 })} л`
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
      description: 'Текущий объём принятого отработанного масла и передача сырья в котлы.',
      title: 'Приёмные баки',
    },
    preheating_boiler: {
      containers: boilers,
      description: 'Учёт загрузки котлов первичного прогрева без запуска и параметров прогрева.',
      title: 'Котлы первичного прогрева',
    },
    separator: {
      containers: separators,
      description: 'Учёт вместимости, текущего объёма и доступности сепараторов.',
      title: 'Сепараторы',
    },
    chemical_mixer: {
      containers: chemicalMixers,
      description: 'Учёт вместимости, текущего объёма и доступности химических миксеров.',
      title: 'Химические миксеры',
    },
    processing_workshop: {
      containers: processingWorkshops,
      description: 'Учёт вместимости, текущего объёма и доступности цехов переработки.',
      title: 'Цеха переработки',
    },
    raw_diesel_tank: {
      containers: rawDieselTanks,
      description: 'Учёт вместимости, текущего объёма и доступности баков сырой солярки.',
      title: 'Баки сырой солярки',
    },
    raw_spindle_tank: {
      containers: rawSpindleTanks,
      description: 'Учёт вместимости, текущего объёма и доступности баков сырой веретенки.',
      title: 'Баки сырой веретенки',
    },
  }[kind]
  const containers = pageConfig.containers
  const controls = useListControls(containers, (item) => [item.number, item.name, item.current_volume_liters].join(' '))
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

      {error && <p className="access-error">{error}</p>}

      <section className="access-grid">
        <article className="access-card">
          <div className="panel-heading">
            <div>
              <p className="auth-eyebrow">Ёмкости</p>
              <h3>{title}</h3>
            </div>
            {isAdmin && <button type="button" onClick={openCreateModal}>Создать</button>}
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
                  <strong>{item.name}</strong>
                  <span>Текущий объём: {formatVolume(item.current_volume_liters)}</span>
                  {isAdmin && (
                    <>
                      <span>Вместимость: {formatVolume(item.capacity_liters)} · Свободно: {formatVolume(item.free_volume_liters)}</span>
                      <span>Заполнение: {item.fill_percentage}% · Последнее движение: {formatDateTime(item.last_movement_at)}</span>
                      <span>{item.is_active ? 'Активна' : 'Деактивирована'}</span>
                      {!isTankPage && Boolean(item.recent_loadings?.length) && (
                        <span>Последние загрузки: {item.recent_loadings.map((movement) => `${formatDateTime(movement.moved_at)} — ${formatVolume(movement.volume_liters)}`).join('; ')}</span>
                      )}
                    </>
                  )}
                </div>
                <div className="row-actions">
                  {isAdmin && <button type="button" onClick={() => openEditModal(item)}>Изменить</button>}
                  {isAdmin && <button className="danger-button" type="button" onClick={() => setDeleteTarget(item)}>Удалить</button>}
                </div>
              </div>
            ))}
            {!containers.length && <p className="empty-state">Ёмкости пока не созданы.</p>}
            {Boolean(containers.length) && !controls.filteredCount && <p className="empty-state">По вашему запросу ничего не найдено.</p>}
          </div>
        </article>
      </section>

      {isContainerFormOpen && (
        <Modal title={containerForm.id ? 'Изменить ёмкость' : 'Новая ёмкость'} onClose={() => setIsContainerFormOpen(false)}>
          <form className="crud-form" onSubmit={handleContainerSubmit}>
            <label>
              <span>Номер</span>
              <input min="1" required type="number" value={containerForm.number} onChange={(event) => setContainerForm({ ...containerForm, number: event.target.value })} />
            </label>
            <label>
              <span>Вместимость, л</span>
              <input min="1" required step="1" type="number" value={containerForm.capacity_liters} onChange={(event) => setContainerForm({ ...containerForm, capacity_liters: event.target.value })} />
            </label>
            <label className="checkbox-row">
              <input checked={containerForm.is_active} type="checkbox" onChange={(event) => setContainerForm({ ...containerForm, is_active: event.target.checked })} />
              Активна
            </label>
            <div className="form-actions">
              <button type="submit">{containerForm.id ? 'Сохранить' : 'Создать'}</button>
              <button className="secondary-button" type="button" onClick={() => setIsContainerFormOpen(false)}>Отмена</button>
            </div>
          </form>
        </Modal>
      )}

      {deleteTarget && (
        <DeleteConfirmModal
          entityName="ёмкость"
          itemName={deleteTarget.name}
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
    <DashboardShell title="Загрузка котла отработки" onLogout={onLogout} user={user}>
      <ProcessingPageHeader
        title="Загрузка котла отработки"
        description="Регистрация движения отработанного масла из приёмного бака в котёл первичного прогрева."
      />

      {error && <p className="access-error">{error}</p>}

      <section className="boiler-loading-layout">
        <article className="access-card boiler-loading-form-card">
          <div className="panel-heading">
            <div>
              <p className="auth-eyebrow">Новое движение</p>
              <h3>Выберите источник, котёл и объём</h3>
            </div>
          </div>

          <form className="crud-form boiler-loading-form" onSubmit={handleSubmit}>
            <label>
              <span>Приёмный бак</span>
              <select required value={form.source_tank_id} onChange={(event) => setForm({ ...form, source_tank_id: event.target.value })}>
                <option value="">Выберите приёмный бак</option>
                {availableTanks.map((tank) => (
                  <option key={tank.id} value={tank.id}>{tank.name} · доступно {formatVolume(tank.current_volume_liters)}</option>
                ))}
              </select>
            </label>

            <label>
              <span>Котёл первичного прогрева</span>
              <select required value={form.destination_boiler_id} onChange={(event) => setForm({ ...form, destination_boiler_id: event.target.value })}>
                <option value="">Выберите котёл</option>
                {availableBoilers.map((boiler) => (
                  <option key={boiler.id} value={boiler.id}>{boiler.name} · сейчас {formatVolume(boiler.current_volume_liters)}</option>
                ))}
              </select>
            </label>

            <label>
              <span>Объём движения, л</span>
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

            {exceedsSource && <p className="access-error">Указанный объём превышает остаток выбранного приёмного бака.</p>}
            {exceedsDestination && <p className="access-error">Указанный объём превышает свободное место выбранного котла.</p>}
            {!availableTanks.length && <p className="empty-state">Нет активных приёмных баков с доступным маслом.</p>}
            {!availableBoilers.length && <p className="empty-state">Нет активных котлов, доступных для загрузки.</p>}

            <div className="form-actions">
              <button disabled={!canSubmit} type="submit">{isSubmitting ? 'Выполняется...' : 'Подтвердить движение'}</button>
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
              >
                Очистить
              </button>
            </div>
          </form>
        </article>

        <aside className="boiler-loading-summary">
          <article className="access-card movement-preview-card">
            <p className="auth-eyebrow">Предварительный баланс</p>
            <h3>После движения</h3>
            <div className="movement-preview-grid">
              <div>
                <span>Приёмный бак</span>
                <strong>{selectedTank?.name || 'Не выбран'}</strong>
                <small>Сейчас: {formatVolume(selectedTank?.current_volume_liters)}</small>
                <small>Останется: {selectedTank && hasPositiveVolume && !exceedsSource ? formatVolume(sourceVolume - volume) : '—'}</small>
              </div>
              <span aria-hidden="true" className="movement-preview-arrow">→</span>
              <div>
                <span>Котёл</span>
                <strong>{selectedBoiler?.name || 'Не выбран'}</strong>
                <small>Сейчас: {formatVolume(selectedBoiler?.current_volume_liters)}</small>
                <small>Будет: {selectedBoiler && hasPositiveVolume ? formatVolume(destinationVolume + volume) : '—'}</small>
              </div>
            </div>
          </article>

          {createdMovement && (
            <article className="access-card movement-success-card">
              <p className="auth-eyebrow">Движение выполнено</p>
              <h3>{createdMovement.movement_number}</h3>
              <span>{createdMovement.source} → {createdMovement.destination}</span>
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
    <DashboardShell title="Загрузка сепаратора" onLogout={onLogout} user={user}>
      <ProcessingPageHeader
        title="Загрузка сепаратора"
        description="Регистрация движения отработанного масла из котла первичного прогрева в сепаратор."
      />

      {error && <p className="access-error">{error}</p>}

      <section className="boiler-loading-layout">
        <article className="access-card boiler-loading-form-card">
          <div className="panel-heading">
            <div>
              <p className="auth-eyebrow">Новое движение</p>
              <h3>Выберите котёл, сепаратор и объём</h3>
            </div>
          </div>

          <form className="crud-form boiler-loading-form" onSubmit={handleSubmit}>
            <label>
              <span>Котёл первичного прогрева</span>
              <select required value={form.source_boiler_id} onChange={(event) => setForm({ ...form, source_boiler_id: event.target.value })}>
                <option value="">Выберите котёл</option>
                {availableBoilers.map((boiler) => (
                  <option key={boiler.id} value={boiler.id}>{boiler.name} · доступно {formatVolume(boiler.current_volume_liters)}</option>
                ))}
              </select>
            </label>

            <label>
              <span>Сепаратор</span>
              <select required value={form.destination_separator_id} onChange={(event) => setForm({ ...form, destination_separator_id: event.target.value })}>
                <option value="">Выберите сепаратор</option>
                {availableSeparators.map((separator) => (
                  <option key={separator.id} value={separator.id}>{separator.name} · сейчас {formatVolume(separator.current_volume_liters)}</option>
                ))}
              </select>
            </label>

            <label>
              <span>Объём движения, л</span>
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

            {exceedsSource && <p className="access-error">Указанный объём превышает остаток выбранного котла.</p>}
            {exceedsDestination && <p className="access-error">Указанный объём превышает свободное место сепаратора.</p>}
            {!availableBoilers.length && <p className="empty-state">Нет активных котлов с доступным маслом.</p>}
            {!availableSeparators.length && <p className="empty-state">Нет активных сепараторов, доступных для загрузки.</p>}

            <div className="form-actions">
              <button disabled={!canSubmit} type="submit">{isSubmitting ? 'Выполняется...' : 'Подтвердить движение'}</button>
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
              >
                Очистить
              </button>
            </div>
          </form>
        </article>

        <aside className="boiler-loading-summary">
          <article className="access-card movement-preview-card">
            <p className="auth-eyebrow">Предварительный баланс</p>
            <h3>После движения</h3>
            <div className="movement-preview-grid">
              <div>
                <span>Котёл</span>
                <strong>{selectedBoiler?.name || 'Не выбран'}</strong>
                <small>Сейчас: {formatVolume(selectedBoiler?.current_volume_liters)}</small>
                <small>Останется: {selectedBoiler && hasPositiveVolume && !exceedsSource ? formatVolume(sourceVolume - volume) : '—'}</small>
              </div>
              <span aria-hidden="true" className="movement-preview-arrow">→</span>
              <div>
                <span>Сепаратор</span>
                <strong>{selectedSeparator?.name || 'Не выбран'}</strong>
                <small>Сейчас: {formatVolume(selectedSeparator?.current_volume_liters)}</small>
                <small>Будет: {selectedSeparator && hasPositiveVolume ? formatVolume(destinationVolume + volume) : '—'}</small>
              </div>
            </div>
          </article>

          {createdMovement && (
            <article className="access-card movement-success-card">
              <p className="auth-eyebrow">Движение выполнено</p>
              <h3>{createdMovement.movement_number}</h3>
              <span>{createdMovement.source} → {createdMovement.destination}</span>
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
    <DashboardShell title="Загрузка химического миксера" onLogout={onLogout} user={user}>
      <ProcessingPageHeader
        title="Загрузка химического миксера"
        description="Регистрация движения очищенного отработанного масла из сепаратора в химический миксер."
      />

      {error && <p className="access-error">{error}</p>}

      <section className="boiler-loading-layout">
        <article className="access-card boiler-loading-form-card">
          <div className="panel-heading">
            <div>
              <p className="auth-eyebrow">Новое движение</p>
              <h3>Выберите сепаратор, миксер и объём</h3>
            </div>
          </div>

          <form className="crud-form boiler-loading-form" onSubmit={handleSubmit}>
            <label>
              <span>Сепаратор</span>
              <select required value={form.source_separator_id} onChange={(event) => setForm({ ...form, source_separator_id: event.target.value })}>
                <option value="">Выберите сепаратор</option>
                {availableSeparators.map((separator) => (
                  <option key={separator.id} value={separator.id}>{separator.name} · доступно {formatVolume(separator.current_volume_liters)}</option>
                ))}
              </select>
            </label>

            <label>
              <span>Химический миксер</span>
              <select required value={form.destination_mixer_id} onChange={(event) => setForm({ ...form, destination_mixer_id: event.target.value })}>
                <option value="">Выберите химический миксер</option>
                {availableMixers.map((mixer) => (
                  <option key={mixer.id} value={mixer.id}>{mixer.name} · сейчас {formatVolume(mixer.current_volume_liters)}</option>
                ))}
              </select>
            </label>

            <label>
              <span>Объём движения, л</span>
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

            {exceedsSource && <p className="access-error">Указанный объём превышает остаток выбранного сепаратора.</p>}
            {exceedsDestination && <p className="access-error">Указанный объём превышает свободное место химического миксера.</p>}
            {!availableSeparators.length && <p className="empty-state">Нет активных сепараторов с доступным маслом.</p>}
            {!availableMixers.length && <p className="empty-state">Нет активных химических миксеров, доступных для загрузки.</p>}

            <div className="form-actions">
              <button disabled={!canSubmit} type="submit">{isSubmitting ? 'Выполняется...' : 'Подтвердить движение'}</button>
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
              >
                Очистить
              </button>
            </div>
          </form>
        </article>

        <aside className="boiler-loading-summary">
          <article className="access-card movement-preview-card">
            <p className="auth-eyebrow">Предварительный баланс</p>
            <h3>После движения</h3>
            <div className="movement-preview-grid">
              <div>
                <span>Сепаратор</span>
                <strong>{selectedSeparator?.name || 'Не выбран'}</strong>
                <small>Сейчас: {formatVolume(selectedSeparator?.current_volume_liters)}</small>
                <small>Останется: {selectedSeparator && hasPositiveVolume && !exceedsSource ? formatVolume(sourceVolume - volume) : '—'}</small>
              </div>
              <span aria-hidden="true" className="movement-preview-arrow">→</span>
              <div>
                <span>Химический миксер</span>
                <strong>{selectedMixer?.name || 'Не выбран'}</strong>
                <small>Сейчас: {formatVolume(selectedMixer?.current_volume_liters)}</small>
                <small>Будет: {selectedMixer && hasPositiveVolume ? formatVolume(destinationVolume + volume) : '—'}</small>
              </div>
            </div>
          </article>

          {createdMovement && (
            <article className="access-card movement-success-card">
              <p className="auth-eyebrow">Движение выполнено</p>
              <h3>{createdMovement.movement_number}</h3>
              <span>{createdMovement.source} → {createdMovement.destination}</span>
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
    <DashboardShell title="Загрузка в цех переработки" onLogout={onLogout} user={user}>
      <ProcessingPageHeader
        title="Загрузка в цех переработки"
        description="Регистрация движения химически подготовленного масла из химического миксера в цех переработки."
      />

      {error && <p className="access-error">{error}</p>}

      <section className="boiler-loading-layout">
        <article className="access-card boiler-loading-form-card">
          <div className="panel-heading">
            <div>
              <p className="auth-eyebrow">Новое движение</p>
              <h3>Выберите миксер, цех и объём</h3>
            </div>
          </div>

          <form className="crud-form boiler-loading-form" onSubmit={handleSubmit}>
            <label>
              <span>Химический миксер</span>
              <select required value={form.source_mixer_id} onChange={(event) => setForm({ ...form, source_mixer_id: event.target.value })}>
                <option value="">Выберите химический миксер</option>
                {availableMixers.map((mixer) => (
                  <option key={mixer.id} value={mixer.id}>{mixer.name} · доступно {formatVolume(mixer.current_volume_liters)}</option>
                ))}
              </select>
            </label>

            <label>
              <span>Цех переработки</span>
              <select required value={form.destination_workshop_id} onChange={(event) => setForm({ ...form, destination_workshop_id: event.target.value })}>
                <option value="">Выберите цех переработки</option>
                {availableWorkshops.map((workshop) => (
                  <option key={workshop.id} value={workshop.id}>{workshop.name} · сейчас {formatVolume(workshop.current_volume_liters)}</option>
                ))}
              </select>
            </label>

            <label>
              <span>Объём движения, л</span>
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

            {exceedsSource && <p className="access-error">Указанный объём превышает остаток выбранного химического миксера.</p>}
            {exceedsDestination && <p className="access-error">Указанный объём превышает свободное место цеха переработки.</p>}
            {!availableMixers.length && <p className="empty-state">Нет активных химических миксеров с доступным маслом.</p>}
            {!availableWorkshops.length && <p className="empty-state">Нет активных цехов переработки, доступных для загрузки.</p>}

            <div className="form-actions">
              <button disabled={!canSubmit} type="submit">{isSubmitting ? 'Выполняется...' : 'Подтвердить движение'}</button>
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
              >
                Очистить
              </button>
            </div>
          </form>
        </article>

        <aside className="boiler-loading-summary">
          <article className="access-card movement-preview-card">
            <p className="auth-eyebrow">Предварительный баланс</p>
            <h3>После движения</h3>
            <div className="movement-preview-grid">
              <div>
                <span>Химический миксер</span>
                <strong>{selectedMixer?.name || 'Не выбран'}</strong>
                <small>Сейчас: {formatVolume(selectedMixer?.current_volume_liters)}</small>
                <small>Останется: {selectedMixer && hasPositiveVolume && !exceedsSource ? formatVolume(sourceVolume - volume) : '—'}</small>
              </div>
              <span aria-hidden="true" className="movement-preview-arrow">→</span>
              <div>
                <span>Цех переработки</span>
                <strong>{selectedWorkshop?.name || 'Не выбран'}</strong>
                <small>Сейчас: {formatVolume(selectedWorkshop?.current_volume_liters)}</small>
                <small>Будет: {selectedWorkshop && hasPositiveVolume ? formatVolume(destinationVolume + volume) : '—'}</small>
              </div>
            </div>
          </article>

          {createdMovement && (
            <article className="access-card movement-success-card">
              <p className="auth-eyebrow">Движение выполнено</p>
              <h3>{createdMovement.movement_number}</h3>
              <span>{createdMovement.source} → {createdMovement.destination}</span>
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
  const title = isDiesel ? 'Загрузка бака сырой солярки' : 'Загрузка бака сырой веретенки'
  const productName = isDiesel ? 'Сырая солярка' : 'Сырая веретенка'
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
        description={`Регистрация движения продукта «${productName}» из цеха переработки в отдельный бак.`}
      />

      {error && <p className="access-error">{error}</p>}

      <section className="boiler-loading-layout">
        <article className="access-card boiler-loading-form-card">
          <div className="panel-heading">
            <div>
              <p className="auth-eyebrow">Новое движение</p>
              <h3>Выберите цех, бак и объём</h3>
            </div>
          </div>

          <form className="crud-form boiler-loading-form" onSubmit={handleSubmit}>
            <label>
              <span>Цех переработки</span>
              <select required value={form.source_workshop_id} onChange={(event) => setForm({ ...form, source_workshop_id: event.target.value })}>
                <option value="">Выберите цех переработки</option>
                {availableWorkshops.map((workshop) => (
                  <option key={workshop.id} value={workshop.id}>{workshop.name} · доступно {formatVolume(workshop.current_volume_liters)}</option>
                ))}
              </select>
            </label>

            <label>
              <span>{isDiesel ? 'Бак сырой солярки' : 'Бак сырой веретенки'}</span>
              <select required value={form.destination_tank_id} onChange={(event) => setForm({ ...form, destination_tank_id: event.target.value })}>
                <option value="">Выберите бак</option>
                {availableTanks.map((tank) => (
                  <option key={tank.id} value={tank.id}>{tank.name} · сейчас {formatVolume(tank.current_volume_liters)}</option>
                ))}
              </select>
            </label>

            <label>
              <span>Объём движения, л</span>
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

            {exceedsSource && <p className="access-error">Указанный объём превышает остаток выбранного цеха.</p>}
            {exceedsDestination && <p className="access-error">Указанный объём превышает свободное место выбранного бака.</p>}
            {!availableWorkshops.length && <p className="empty-state">Нет активных цехов с доступным продуктом.</p>}
            {!availableTanks.length && <p className="empty-state">Нет активных баков, доступных для загрузки.</p>}

            <div className="form-actions">
              <button disabled={!canSubmit} type="submit">{isSubmitting ? 'Выполняется...' : 'Подтвердить движение'}</button>
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
              >
                Очистить
              </button>
            </div>
          </form>
        </article>

        <aside className="boiler-loading-summary">
          <article className="access-card movement-preview-card">
            <p className="auth-eyebrow">Предварительный баланс</p>
            <h3>После движения</h3>
            <div className="movement-preview-grid">
              <div>
                <span>Цех переработки</span>
                <strong>{selectedWorkshop?.name || 'Не выбран'}</strong>
                <small>Сейчас: {formatVolume(selectedWorkshop?.current_volume_liters)}</small>
                <small>Останется: {selectedWorkshop && hasPositiveVolume && !exceedsSource ? formatVolume(sourceVolume - volume) : '—'}</small>
              </div>
              <span aria-hidden="true" className="movement-preview-arrow">→</span>
              <div>
                <span>{productName}</span>
                <strong>{selectedTank?.name || 'Не выбран'}</strong>
                <small>Сейчас: {formatVolume(selectedTank?.current_volume_liters)}</small>
                <small>Будет: {selectedTank && hasPositiveVolume ? formatVolume(destinationVolume + volume) : '—'}</small>
              </div>
            </div>
          </article>

          {createdMovement && (
            <article className="access-card movement-success-card">
              <p className="auth-eyebrow">Движение выполнено</p>
              <h3>{createdMovement.movement_number}</h3>
              <span>{createdMovement.source} → {createdMovement.destination}</span>
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
    <DashboardShell title="Отгрузка сепаратора" onLogout={onLogout} user={user}>
      <ProcessingPageHeader
        title="Отгрузка сепаратора"
        description="Регистрация отгрузки технической воды или технического мусора из сепаратора. Топливный выход здесь не учитывается."
      />

      {error && <p className="access-error">{error}</p>}

      <section className="boiler-loading-layout">
        <article className="access-card boiler-loading-form-card">
          <div className="panel-heading">
            <div>
              <p className="auth-eyebrow">Новая отгрузка</p>
              <h3>Выберите сепаратор, вид отхода и объём</h3>
            </div>
          </div>

          <form className="crud-form boiler-loading-form" onSubmit={handleSubmit}>
            <label>
              <span>Сепаратор</span>
              <select required value={form.source_separator_id} onChange={(event) => setForm({ ...form, source_separator_id: event.target.value })}>
                <option value="">Выберите сепаратор</option>
                {availableSeparators.map((separator) => (
                  <option key={separator.id} value={separator.id}>{separator.name} · доступно {formatVolume(separator.current_volume_liters)}</option>
                ))}
              </select>
            </label>

            <fieldset className="separator-output-options">
              <legend>Что отгружается</legend>
              <div className="unit-radio-group" role="radiogroup" aria-label="Вид отгрузки сепаратора">
                {[
                  ['water', 'Техническая вода'],
                  ['technical_waste', 'Технический мусор'],
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
              <span>Объём отгрузки, л</span>
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

            {exceedsSource && <p className="access-error">Указанный объём превышает остаток выбранного сепаратора.</p>}
            {!availableSeparators.length && <p className="empty-state">Нет активных сепараторов с доступным объёмом.</p>}

            <div className="form-actions">
              <button disabled={!canSubmit} type="submit">{isSubmitting ? 'Выполняется...' : 'Подтвердить отгрузку'}</button>
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
              >
                Очистить
              </button>
            </div>
          </form>
        </article>

        <aside className="boiler-loading-summary">
          <article className="access-card movement-preview-card">
            <p className="auth-eyebrow">Предварительный баланс</p>
            <h3>После отгрузки</h3>
            <div className="movement-preview-grid">
              <div>
                <span>Сепаратор</span>
                <strong>{selectedSeparator?.name || 'Не выбран'}</strong>
                <small>Сейчас: {formatVolume(selectedSeparator?.current_volume_liters)}</small>
                <small>Останется: {selectedSeparator && hasPositiveVolume && !exceedsSource ? formatVolume(sourceVolume - volume) : '—'}</small>
              </div>
              <span aria-hidden="true" className="movement-preview-arrow">→</span>
              <div>
                <span>Отгрузка</span>
                <strong>{form.output_type === 'water' ? 'Техническая вода' : 'Технический мусор'}</strong>
                <small>Объём: {hasPositiveVolume ? formatVolume(volume) : '—'}</small>
              </div>
            </div>
          </article>

          {createdMovement && (
            <article className="access-card movement-success-card">
              <p className="auth-eyebrow">Отгрузка выполнена</p>
              <h3>{createdMovement.movement_number}</h3>
              <span>{createdMovement.source} → {createdMovement.product_name}</span>
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
    <DashboardShell title="Журнал" onLogout={onLogout} user={user}>
      <ProcessingPageHeader title="Журнал операций" description="Движения масла и аудит изменяющих действий первого производственного этапа." />
      {error && <p className="access-error">{error}</p>}

      <section className="access-grid">
        <article className="access-card">
          <form className="journal-filters" onSubmit={applyFilters}>
            <input placeholder="Поиск" value={filters.query} onChange={(event) => setFilters({ ...filters, query: event.target.value })} />
            <input aria-label="Дата с" type="date" value={filters.date_from} onChange={(event) => setFilters({ ...filters, date_from: event.target.value })} />
            <input aria-label="Дата по" type="date" value={filters.date_to} onChange={(event) => setFilters({ ...filters, date_to: event.target.value })} />
            <select value={filters.movement_type} onChange={(event) => setFilters({ ...filters, movement_type: event.target.value })}>
              <option value="">Все типы</option>
              <option value="receipt_to_tank">Поступление из приёмки</option>
              <option value="tank_to_boiler">Загрузка котла</option>
              <option value="boiler_to_separator">Загрузка сепаратора</option>
              <option value="separator_output">Отгрузка сепаратора</option>
              <option value="separator_to_chemical_mixer">Загрузка химического миксера</option>
              <option value="chemical_mixer_to_workshop">Загрузка в цех переработки</option>
              <option value="workshop_to_raw_diesel_tank">Загрузка бака сырой солярки</option>
              <option value="workshop_to_raw_spindle_tank">Загрузка бака сырой веретенки</option>
              <option value="compensation">Компенсация</option>
            </select>
            <select value={filters.status} onChange={(event) => setFilters({ ...filters, status: event.target.value })}>
              <option value="">Все состояния</option>
              <option value="confirmed">Подтверждено</option>
              <option value="success">Успешно</option>
              <option value="rejected">Отклонено</option>
            </select>
            <input placeholder="Источник" value={filters.source} onChange={(event) => setFilters({ ...filters, source: event.target.value })} />
            <input placeholder="Получатель" value={filters.destination} onChange={(event) => setFilters({ ...filters, destination: event.target.value })} />
            <input placeholder="Пользователь" value={filters.user} onChange={(event) => setFilters({ ...filters, user: event.target.value })} />
            <input placeholder="Номер движения" value={filters.number} onChange={(event) => setFilters({ ...filters, number: event.target.value })} />
            <input min="0.001" placeholder="Объём" step="0.001" type="number" value={filters.volume} onChange={(event) => setFilters({ ...filters, volume: event.target.value })} />
            <div className="form-actions">
              <button type="submit">Применить</button>
              <button className="secondary-button" type="button" onClick={() => { setFilters(emptyJournalFilters); fetchJournal({}, 1) }}>Сбросить</button>
            </div>
          </form>

          <div className="entity-list">
            {journal.items.map((item) => (
              <div className="entity-row journal-row" key={`${item.entry_type}-${item.id}`}>
                <div>
                  <strong>{item.entry_type === 'movement' ? item.movement_number : item.action}</strong>
                  {item.entry_type === 'movement' ? (
                    <>
                      <span>{item.movement_type_label} · {formatVolume(item.volume_liters)}</span>
                      <span>{item.source || '—'} → {item.destination || '—'}</span>
                      <span>{formatDateTime(item.moved_at)} · {item.created_by || 'Система'}</span>
                    </>
                  ) : (
                    <>
                      <span>{item.object_type} #{item.object_id || '—'} · {item.result}</span>
                      <span>{formatDateTime(item.created_at)} · {item.user || 'Система'}</span>
                    </>
                  )}
                </div>
                <div className="row-actions">
                  <button type="button" onClick={() => setSelectedEntry(item)}>Подробнее</button>
                  {item.entry_type === 'movement' && item.can_compensate && (
                    <button className="danger-button" type="button" onClick={() => setCompensationTarget(item)}>Компенсировать</button>
                  )}
                </div>
              </div>
            ))}
            {!journal.items.length && <p className="empty-state">Записи не найдены.</p>}
          </div>

          <div className="list-pagination journal-pagination">
            <span>{journal.total} записей</span>
            <div className="pagination-actions">
              <button className="secondary-button" disabled={journal.page <= 1} type="button" onClick={() => changePage(journal.page - 1)}>Назад</button>
              <strong>{journal.page} / {journal.page_count}</strong>
              <button className="secondary-button" disabled={journal.page >= journal.page_count} type="button" onClick={() => changePage(journal.page + 1)}>Вперёд</button>
            </div>
          </div>
        </article>
      </section>

      {selectedEntry && (
        <Modal title="Детали записи" onClose={() => setSelectedEntry(null)}>
          <pre className="journal-details">{JSON.stringify(selectedEntry, null, 2)}</pre>
        </Modal>
      )}

      {compensationTarget && (
        <Modal title="Компенсировать движение" onClose={() => setCompensationTarget(null)}>
          <form className="crud-form" onSubmit={handleCompensation}>
            <p>Будет создано отдельное обратное движение для {compensationTarget.movement_number}.</p>
            <label>
              <span>Причина</span>
              <textarea required value={compensationReason} onChange={(event) => setCompensationReason(event.target.value)} />
            </label>
            <div className="form-actions">
              <button className="danger-button" type="submit">Создать компенсацию</button>
              <button className="secondary-button" type="button" onClick={() => setCompensationTarget(null)}>Отмена</button>
            </div>
          </form>
        </Modal>
      )}
    </DashboardShell>
  )
}
