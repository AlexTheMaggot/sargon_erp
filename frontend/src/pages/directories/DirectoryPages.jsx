import { t } from '../../i18n/core'
import { useState } from 'react'
import { DashboardShell } from '../../components/Layout/DashboardShell'
import { ListControls } from '../../components/ListControls/ListControls'
import { DeleteConfirmModal, Modal as AccessModal } from '../../components/Modal/Modal'
import { emptyCityForm, emptySupplierForm } from '../../constants/forms'
import { useDirectoryCrud } from '../../hooks/useDirectoryCrud'
import { useListControls } from '../../hooks/useListControls'

function DirectoryPageHeader({ description, title }) {
  return (
    <section className="page-title access-page-title">
      <p className="auth-eyebrow">{t('Справочник')}</p>
      <h1>{title}</h1>
      <p>{description}</p>
    </section>
  )
}

export function CitiesPage({ onLogout, token, user }) {
  const { cities, error, saveCity, deleteCity } = useDirectoryCrud(token)
  const cityControls = useListControls(cities, (item) => [item.id, item.name].join(' '))
  const [cityForm, setCityForm] = useState(emptyCityForm)
  const [isFormOpen, setIsFormOpen] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState(null)

  function openCreateModal() {
    setCityForm(emptyCityForm)
    setIsFormOpen(true)
  }

  function openEditModal(item) {
    setCityForm({ id: item.id, name: item.name })
    setIsFormOpen(true)
  }

  async function handleCitySubmit(event) {
    const isSaved = await saveCity(event, cityForm, () => setCityForm(emptyCityForm))
    if (isSaved) {
      setIsFormOpen(false)
    }
  }

  async function handleCityDelete() {
    const isDeleted = await deleteCity(deleteTarget.id)
    if (isDeleted) {
      setDeleteTarget(null)
    }
  }

  return (
    <DashboardShell title={t('Города')} onLogout={onLogout} user={user}>
      <DirectoryPageHeader
        title={t('Города')}
        description={t('Отдельный справочник городов. Город нельзя удалить, если он используется поставщиком.')}
      />

      {error && <p className="access-error">{t(error)}</p>}

      <section className="access-grid">
        <article className="access-card">
          <div className="panel-heading">
            <div>
              <p className="auth-eyebrow">{t('Города')}</p>
              <h3>{t('Список городов')}</h3>
            </div>
            <button type="button" onClick={openCreateModal}>{t('Создать')}</button>
          </div>

          <ListControls
            currentPage={cityControls.currentPage}
            filteredCount={cityControls.filteredCount}
            onPageChange={cityControls.setCurrentPage}
            onSearchChange={cityControls.setSearchQuery}
            pageCount={cityControls.pageCount}
            searchQuery={cityControls.searchQuery}
            totalCount={cityControls.totalCount}
          />

          <div className="entity-list">
            {cityControls.paginatedItems.map((item) => (
              <div className="entity-row" key={item.id}>
                <div><strong>{item.name}</strong><span>ID: {item.id}</span></div>
                <div className="row-actions">
                  <button type="button" onClick={() => openEditModal(item)}>{t('Изменить')}</button>
                  <button className="danger-button" type="button" onClick={() => setDeleteTarget(item)}>{t('Удалить')}</button>
                </div>
              </div>
            ))}
            {!cities.length && <p className="empty-state">{t('Городов пока нет. Добавьте первый город.')}</p>}
            {Boolean(cities.length) && !cityControls.filteredCount && <p className="empty-state">{t('По вашему запросу ничего не найдено.')}</p>}
          </div>
        </article>
      </section>

      {isFormOpen && (
        <AccessModal title={cityForm.id ? t('Редактировать город') : t('Новый город')} onClose={() => setIsFormOpen(false)}>
          <form className="crud-form" onSubmit={handleCitySubmit}>
            <input placeholder={t('Название города')} value={cityForm.name} onChange={(event) => setCityForm({ ...cityForm, name: event.target.value })} />
            <div className="form-actions">
              <button type="submit">{cityForm.id ? t('Сохранить') : t('Создать')}</button>
              <button className="secondary-button" type="button" onClick={() => setIsFormOpen(false)}>{t('Отмена')}</button>
            </div>
          </form>
        </AccessModal>
      )}

      {deleteTarget && (
        <DeleteConfirmModal
          entityName={t('город')}
          itemName={deleteTarget.name}
          onCancel={() => setDeleteTarget(null)}
          onConfirm={handleCityDelete}
        />
      )}
    </DashboardShell>
  )
}

export function SuppliersPage({ onLogout, token, user }) {
  const { suppliers, cities, error, saveSupplier, deleteSupplier } = useDirectoryCrud(token)
  const supplierControls = useListControls(suppliers, (item) => [
    item.company_name,
    item.city?.name,
    item.address,
    item.phone,
  ].join(' '))
  const [supplierForm, setSupplierForm] = useState(emptySupplierForm)
  const [isSupplierFormOpen, setIsSupplierFormOpen] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState(null)

  function openCreateModal() {
    setSupplierForm(emptySupplierForm)
    setIsSupplierFormOpen(true)
  }

  function openEditModal(item) {
    setSupplierForm({
      id: item.id,
      company_name: item.company_name,
      city_id: item.city_id || '',
      address: item.address,
      phone: item.phone,
    })
    setIsSupplierFormOpen(true)
  }

  async function handleSupplierSubmit(event) {
    const isSaved = await saveSupplier(event, supplierForm, () => setSupplierForm(emptySupplierForm))
    if (isSaved) {
      setIsSupplierFormOpen(false)
    }
  }

  async function handleSupplierDelete() {
    const isDeleted = await deleteSupplier(deleteTarget.id)
    if (isDeleted) {
      setDeleteTarget(null)
    }
  }

  return (
    <DashboardShell title={t('Поставщики')} onLogout={onLogout} user={user}>
      <DirectoryPageHeader
        title={t('Поставщики')}
        description={t('Справочник поставщиков сырья и услуг. Город хранится отдельной сущностью и выбирается в карточке поставщика.')}
      />

      {error && <p className="access-error">{t(error)}</p>}

      <section className="access-grid">
        <article className="access-card">
          <div className="panel-heading">
            <div>
              <p className="auth-eyebrow">{t('Поставщики')}</p>
              <h3>{t('Список поставщиков')}</h3>
            </div>
            <div className="row-actions">
              <button type="button" onClick={openCreateModal}>{t('Создать')}</button>
            </div>
          </div>

          <ListControls
            currentPage={supplierControls.currentPage}
            filteredCount={supplierControls.filteredCount}
            onPageChange={supplierControls.setCurrentPage}
            onSearchChange={supplierControls.setSearchQuery}
            pageCount={supplierControls.pageCount}
            searchQuery={supplierControls.searchQuery}
            totalCount={supplierControls.totalCount}
          />

          <div className="entity-list">
            {supplierControls.paginatedItems.map((item) => (
              <div className="entity-row supplier-row" key={item.id}>
                <div>
                  <strong>{item.company_name}</strong>
                  <span>{item.city?.name || t('Город не указан')} · {item.address} · {item.phone}</span>
                </div>
                <div className="row-actions">
                  <button type="button" onClick={() => openEditModal(item)}>{t('Изменить')}</button>
                  <button className="danger-button" type="button" onClick={() => setDeleteTarget(item)}>{t('Удалить')}</button>
                </div>
              </div>
            ))}
            {!suppliers.length && <p className="empty-state">{t('Поставщиков пока нет. Добавьте первого поставщика.')}</p>}
            {Boolean(suppliers.length) && !supplierControls.filteredCount && <p className="empty-state">{t('По вашему запросу ничего не найдено.')}</p>}
          </div>
        </article>
      </section>

      {isSupplierFormOpen && (
        <AccessModal title={supplierForm.id ? t('Редактировать поставщика') : t('Новый поставщик')} onClose={() => setIsSupplierFormOpen(false)}>
          <form className="crud-form" onSubmit={handleSupplierSubmit}>
            <input placeholder={t('Название компании')} value={supplierForm.company_name} onChange={(event) => setSupplierForm({ ...supplierForm, company_name: event.target.value })} />
            <select value={supplierForm.city_id || ''} onChange={(event) => setSupplierForm({ ...supplierForm, city_id: event.target.value ? Number(event.target.value) : '' })}>
              <option value="">{t('Выберите город')}</option>
              {cities.map((city) => <option key={city.id} value={city.id}>{city.name}</option>)}
            </select>
            <input placeholder={t('Адрес')} value={supplierForm.address} onChange={(event) => setSupplierForm({ ...supplierForm, address: event.target.value })} />
            <input placeholder={t('Номер телефона')} value={supplierForm.phone} onChange={(event) => setSupplierForm({ ...supplierForm, phone: event.target.value })} />
            <div className="form-actions">
              <button type="submit">{supplierForm.id ? t('Сохранить') : t('Создать')}</button>
              <button className="secondary-button" type="button" onClick={() => setIsSupplierFormOpen(false)}>{t('Отмена')}</button>
            </div>
          </form>
        </AccessModal>
      )}

      {deleteTarget && (
        <DeleteConfirmModal
          entityName={t('поставщика')}
          itemName={deleteTarget.company_name}
          onCancel={() => setDeleteTarget(null)}
          onConfirm={handleSupplierDelete}
        />
      )}
    </DashboardShell>
  )
}
