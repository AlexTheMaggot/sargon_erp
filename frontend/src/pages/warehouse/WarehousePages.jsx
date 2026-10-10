import { getLocale, localizeStaticData, t } from '../../i18n/core'
import { useEffect, useMemo, useState } from 'react'
import { apiRequest } from '../../api/client'
import { DashboardShell } from '../../components/Layout/DashboardShell'
import { ListControls } from '../../components/ListControls/ListControls'
import { DeleteConfirmModal, Modal } from '../../components/Modal/Modal'
import { useListControls } from '../../hooks/useListControls'
import { useWarehouseDocuments, useWarehouseOverview, useWarehouseReferenceData, useWarehouseSettings } from '../../hooks/useWarehouse'

const DOCUMENT_CONFIG = {
  receipt: { title: 'Поступления', eyebrow: 'Приход', permission: 'receipt', action: 'Создать поступление' },
  issue: { title: 'Внутренний расход', eyebrow: 'Расход', permission: 'issue', action: 'Создать расход' },
  transfer: { title: 'Перемещения', eyebrow: 'Логистика', permission: 'transfer', action: 'Создать перемещение' },
  inventory: { title: 'Инвентаризация', eyebrow: 'Контроль', permission: 'inventory', action: 'Создать инвентаризацию' },
}

const STATUS_CLASS = {
  draft: 'neutral',
  posted: 'approved',
  completed: 'approved',
  in_transit: 'pending',
  rejected: 'rejected',
  cancelled: 'rejected',
}

function localDateTimeValue() {
  const now = new Date()
  now.setMinutes(now.getMinutes() - now.getTimezoneOffset())
  return now.toISOString().slice(0, 16)
}

function formatDate(value) {
  return value ? new Date(value).toLocaleString(getLocale()) : '—'
}

function formatMoney(value) {
  return t`${Number(value || 0).toLocaleString(getLocale(), { minimumFractionDigits: 2, maximumFractionDigits: 2 })} сум`
}

function PageHeader({ description, eyebrow = t('Складской учёт'), title }) {
  return (
    <section className="page-title access-page-title">
      <p className="auth-eyebrow">{eyebrow}</p>
      <h1>{title}</h1>
      <p>{description}</p>
    </section>
  )
}

function Shell({ children, onLogout, title, user }) {
  return <DashboardShell title={title} onLogout={onLogout} user={user}>{children}</DashboardShell>
}

export function WarehouseOverviewPage({ onLogout, token, user }) {
  const { overview, error } = useWarehouseOverview(token)
  const controls = useListControls(overview.balances, (balance) => [
    balance.warehouse.name,
    balance.item.name,
    t(balance.item.category.name),
  ].join(' '))

  return (
    <Shell title={t('Складской учёт')} onLogout={onLogout} user={user}>
      <PageHeader title={t('Складские остатки')} description={t('Фактические остатки и средневзвешенная стоимость отдельно по каждому складу.')} />
      {error && <p className="access-error">{t(error)}</p>}
      <section className="warehouse-summary-grid">
        <article><span>{t('Стоимость остатков')}</span><strong>{formatMoney(overview.total_value)}</strong></article>
        <article><span>{t('Активных складов')}</span><strong>{overview.warehouse_count}</strong></article>
        <article><span>{t('Номенклатур')}</span><strong>{overview.item_count}</strong></article>
        <article><span>{t('Перемещений в пути')}</span><strong>{overview.in_transit_count}</strong></article>
      </section>
      <section className="access-grid">
        <article className="access-card">
          <div className="panel-heading"><div><p className="auth-eyebrow">{t('Остатки')}</p><h3>{t('По складам и товарам')}</h3></div></div>
          <ListControls {...controls} onPageChange={controls.setCurrentPage} onSearchChange={controls.setSearchQuery} />
          <div className="entity-list">
            {controls.paginatedItems.map((balance) => (
              <div className="entity-row warehouse-balance-row" key={balance.id}>
                <div><strong>{balance.item.name}</strong><span>{balance.warehouse.name} · {t(balance.item.category.name)}</span></div>
                <div className="warehouse-balance-values">
                  <strong>{balance.quantity} {t(balance.item.unit.symbol)}</strong>
                  <span>{formatMoney(balance.average_unit_cost)} / {t(balance.item.unit.symbol)}</span>
                  <span>{t('Всего: ')}{formatMoney(balance.total_value)}</span>
                </div>
              </div>
            ))}
            {!controls.filteredCount && <p className="empty-state">{t('Остатков пока нет.')}</p>}
          </div>
        </article>
      </section>
    </Shell>
  )
}

function emptyDocument(documentType) {
  return {
    document_type: documentType,
    document_date: localDateTimeValue(),
    source_warehouse_id: '',
    destination_warehouse_id: '',
    supplier_id: '',
    purpose: '',
    lines: [{ item_id: '', quantity: '', unit_price: '' }],
  }
}

function WarehouseDocumentPage({ documentType, onLogout, token, user }) {
  const config = localizeStaticData(DOCUMENT_CONFIG[documentType])
  const access = user?.access?.['warehouse-accounting'] || []
  const canCreate = user?.is_admin || access.includes(config.permission)
  const canConfirm = user?.is_admin || access.includes('transfer-confirm')
  const { warehouses, items, suppliers, error: referenceError } = useWarehouseReferenceData(token)
  const { documents, error, createDocument, postDocument, decideTransfer, cancelDocument, deleteDocument } = useWarehouseDocuments(token, documentType)
  const controls = useListControls(documents, (document) => [
    document.number,
    t(document.status_label),
    document.source_warehouse?.name,
    document.destination_warehouse?.name,
    document.supplier?.company_name,
    document.purpose,
  ].join(' '))
  const [form, setForm] = useState(emptyDocument(documentType))
  const [isOpen, setIsOpen] = useState(false)

  function updateLine(index, field, value) {
    setForm((current) => ({
      ...current,
      lines: current.lines.map((line, lineIndex) => lineIndex === index ? { ...line, [field]: value } : line),
    }))
  }

  async function submitDocument(event) {
    event.preventDefault()
    const created = await createDocument({
      ...form,
      source_warehouse_id: form.source_warehouse_id || null,
      destination_warehouse_id: form.destination_warehouse_id || null,
      supplier_id: form.supplier_id || null,
      lines: form.lines.map((line) => ({
        item_id: Number(line.item_id),
        quantity: line.quantity,
        ...(documentType === 'receipt' ? { unit_price: line.unit_price } : {}),
      })),
    })
    if (created) {
      setIsOpen(false)
      setForm(emptyDocument(documentType))
    }
  }

  return (
    <Shell title={config.title} onLogout={onLogout} user={user}>
      <PageHeader eyebrow={config.eyebrow} title={config.title} description={t('Документы сначала сохраняются как черновики, затем проводятся отдельным действием.')} />
      {(error || referenceError) && <p className="access-error">{t(error || referenceError)}</p>}
      <section className="access-grid">
        <article className="access-card">
          <div className="panel-heading">
            <div><p className="auth-eyebrow">{t('Документы')}</p><h3>{t('Журнал операций')}</h3></div>
            {canCreate && <button type="button" onClick={() => setIsOpen(true)}>{config.action}</button>}
          </div>
          <ListControls {...controls} onPageChange={controls.setCurrentPage} onSearchChange={controls.setSearchQuery} />
          <div className="entity-list">
            {controls.paginatedItems.map((document) => (
              <div className="entity-row warehouse-document-row" key={document.id}>
                <div>
                  <strong>{document.number}</strong>
                  <span>{formatDate(document.document_date)} · {document.source_warehouse?.name || document.supplier?.company_name || t('Инвентаризация')}{document.destination_warehouse ? ` → ${document.destination_warehouse.name}` : ''}</span>
                  <span>{document.lines.map((line) => `${line.item.name}: ${line.quantity} ${t(line.item.unit.symbol)}`).join('; ')}</span>
                  {document.purpose && <span>{t('Назначение: ')}{document.purpose}</span>}
                </div>
                <div className="warehouse-document-actions">
                  <span className={`status-pill ${STATUS_CLASS[document.status] || 'neutral'}`}>{t(document.status_label)}</span>
                  <div className="row-actions">
                    {document.status === 'draft' && canCreate && <button type="button" onClick={() => postDocument(document.id)}>{t('Провести')}</button>}
                    {document.status === 'draft' && canCreate && <button className="danger-button" type="button" onClick={() => deleteDocument(document.id)}>{t('Удалить')}</button>}
                    {document.status === 'in_transit' && canConfirm && <button type="button" onClick={() => decideTransfer(document.id, 'confirm')}>{t('Принять')}</button>}
                    {document.status === 'in_transit' && canConfirm && <button className="danger-button" type="button" onClick={() => decideTransfer(document.id, 'reject')}>{t('Отклонить')}</button>}
                    {user?.is_admin && ['posted', 'in_transit', 'completed'].includes(document.status) && <button className="danger-button" type="button" onClick={() => cancelDocument(document.id)}>{t('Отменить')}</button>}
                  </div>
                </div>
              </div>
            ))}
            {!controls.filteredCount && <p className="empty-state">{t('Документов пока нет.')}</p>}
          </div>
        </article>
      </section>

      {isOpen && (
        <Modal title={config.action} onClose={() => setIsOpen(false)}>
          <form className="crud-form warehouse-document-form" onSubmit={submitDocument}>
            <label><span>{t('Дата и время')}</span><input required type="datetime-local" value={form.document_date} onChange={(event) => setForm({ ...form, document_date: event.target.value })} /></label>
            {documentType === 'receipt' && <label><span>{t('Поставщик')}</span><select required value={form.supplier_id} onChange={(event) => setForm({ ...form, supplier_id: event.target.value })}><option value="">{t('Выберите поставщика')}</option>{suppliers.map((supplier) => <option key={supplier.id} value={supplier.id}>{supplier.company_name}</option>)}</select></label>}
            {['issue', 'transfer', 'inventory'].includes(documentType) && <label><span>{documentType === 'transfer' ? t('Склад-отправитель') : t('Склад')}</span><select required value={form.source_warehouse_id} onChange={(event) => setForm({ ...form, source_warehouse_id: event.target.value })}><option value="">{t('Выберите склад')}</option>{warehouses.map((warehouse) => <option key={warehouse.id} value={warehouse.id}>{warehouse.name}</option>)}</select></label>}
            {documentType === 'receipt' && <label><span>{t('Склад поступления')}</span><select required value={form.destination_warehouse_id} onChange={(event) => setForm({ ...form, destination_warehouse_id: event.target.value })}><option value="">{t('Выберите склад')}</option>{warehouses.map((warehouse) => <option key={warehouse.id} value={warehouse.id}>{warehouse.name}</option>)}</select></label>}
            {documentType === 'transfer' && <label><span>{t('Склад-получатель')}</span><select required value={form.destination_warehouse_id} onChange={(event) => setForm({ ...form, destination_warehouse_id: event.target.value })}><option value="">{t('Выберите склад')}</option>{warehouses.map((warehouse) => <option disabled={String(warehouse.id) === String(form.source_warehouse_id)} key={warehouse.id} value={warehouse.id}>{warehouse.name}</option>)}</select></label>}
            {documentType === 'issue' && <label><span>{t('Назначение расхода')}</span><textarea required value={form.purpose} onChange={(event) => setForm({ ...form, purpose: event.target.value })} /></label>}
            <div className="warehouse-lines">
              <div className="panel-heading"><div><h3>{t('Позиции')}</h3></div><button className="secondary-button" type="button" onClick={() => setForm({ ...form, lines: [...form.lines, { item_id: '', quantity: '', unit_price: '' }] })}>{t('Добавить строку')}</button></div>
              {form.lines.map((line, index) => {
                const selectedItem = items.find((item) => String(item.id) === String(line.item_id))
                return (
                  <div className="warehouse-line" key={index}>
                    <label><span>{t('Номенклатура')}</span><select required value={line.item_id} onChange={(event) => updateLine(index, 'item_id', event.target.value)}><option value="">{t('Выберите товар')}</option>{items.map((item) => <option key={item.id} value={item.id}>{item.name} ({t(item.unit.symbol)})</option>)}</select></label>
                    <label><span>{documentType === 'inventory' ? t('Фактический остаток') : t('Количество')}{selectedItem ? `, ${t(selectedItem.unit.symbol)}` : ''}</span><input min="0" required step={selectedItem ? 10 ** -selectedItem.unit.decimal_places : '0.01'} type="number" value={line.quantity} onChange={(event) => updateLine(index, 'quantity', event.target.value)} /></label>
                    {documentType === 'receipt' && <label><span>{t('Цена, сум')}</span><input min="0" required step="0.01" type="number" value={line.unit_price} onChange={(event) => updateLine(index, 'unit_price', event.target.value)} /></label>}
                    {form.lines.length > 1 && <button className="danger-button line-remove-button" type="button" onClick={() => setForm({ ...form, lines: form.lines.filter((_, lineIndex) => lineIndex !== index) })}>×</button>}
                  </div>
                )
              })}
            </div>
            <div className="form-actions"><button type="submit">{t('Сохранить черновик')}</button><button className="secondary-button" type="button" onClick={() => setIsOpen(false)}>{t('Отмена')}</button></div>
          </form>
        </Modal>
      )}
    </Shell>
  )
}

export function WarehouseReceiptsPage(props) { return <WarehouseDocumentPage {...props} documentType="receipt" /> }
export function WarehouseIssuesPage(props) { return <WarehouseDocumentPage {...props} documentType="issue" /> }
export function WarehouseTransfersPage(props) { return <WarehouseDocumentPage {...props} documentType="transfer" /> }
export function WarehouseInventoryPage(props) { return <WarehouseDocumentPage {...props} documentType="inventory" /> }

const SETTINGS_CONFIG = {
  categories: { title: 'Категории товаров', singular: 'категорию', createTitle: 'Создать категорию', editTitle: 'Изменить категорию', empty: { id: null, name: '', is_active: true } },
  units: { title: 'Единицы измерения', singular: 'единицу измерения', createTitle: 'Создать единицу измерения', editTitle: 'Изменить единицу измерения', empty: { id: null, name: '', symbol: '', decimal_places: 0, is_active: true } },
  warehouses: { title: 'Склады', singular: 'склад', createTitle: 'Создать склад', editTitle: 'Изменить склад', empty: { id: null, name: '', description: '', is_active: true } },
}

function SimpleSettingsPage({ entity, onLogout, token, user }) {
  const config = localizeStaticData(SETTINGS_CONFIG[entity])
  const { items, error, save, remove } = useWarehouseSettings(token, entity)
  const controls = useListControls(items, (item) => [entity === 'warehouses' ? item.name : t(item.name), t(item.symbol), item.description].join(' '))
  const [form, setForm] = useState(config.empty)
  const [isOpen, setIsOpen] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState(null)

  function edit(item = config.empty) { setForm({ ...item }); setIsOpen(true) }
  async function submit(event) { event.preventDefault(); if (await save(form)) setIsOpen(false) }

  return (
    <Shell title={config.title} onLogout={onLogout} user={user}>
      <PageHeader eyebrow={t('Настройки склада')} title={config.title} description={t('Динамический справочник складской подсистемы.')} />
      {error && <p className="access-error">{t(error)}</p>}
      <section className="access-grid"><article className="access-card">
        <div className="panel-heading"><div><h3>{t('Список')}</h3></div><button type="button" onClick={() => edit()}>{t('Создать')}</button></div>
        <ListControls {...controls} onPageChange={controls.setCurrentPage} onSearchChange={controls.setSearchQuery} />
        <div className="entity-list">{controls.paginatedItems.map((item) => <div className="entity-row" key={item.id}><div><strong>{entity === 'warehouses' ? item.name : t(item.name)}{t(item.symbol) ? ` (${t(item.symbol)})` : ''}</strong><span>{item.description || (item.is_active ? t('Активно') : t('Отключено'))}</span></div><div className="row-actions"><button type="button" onClick={() => edit(item)}>{t('Изменить')}</button><button className="danger-button" type="button" onClick={() => setDeleteTarget(item)}>{t('Удалить')}</button></div></div>)}</div>
      </article></section>
      {isOpen && <Modal title={form.id ? config.editTitle : config.createTitle} onClose={() => setIsOpen(false)}><form className="crud-form" onSubmit={submit}><label><span>{t('Название')}</span><input required value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} /></label>{entity === 'units' && <><label><span>{t('Сокращение')}</span><input required value={form.symbol} onChange={(event) => setForm({ ...form, symbol: event.target.value })} /></label><label><span>{t('Точность')}</span><select value={form.decimal_places} onChange={(event) => setForm({ ...form, decimal_places: Number(event.target.value) })}><option value={0}>{t('Целые')}</option><option value={1}>{t('Десятые')}</option><option value={2}>{t('Сотые')}</option></select></label></>}{entity === 'warehouses' && <label><span>{t('Описание')}</span><textarea value={form.description} onChange={(event) => setForm({ ...form, description: event.target.value })} /></label>}<label className="checkbox-row"><input checked={form.is_active} type="checkbox" onChange={(event) => setForm({ ...form, is_active: event.target.checked })} /><span>{t('Активно')}</span></label><div className="form-actions"><button type="submit">{t('Сохранить')}</button><button className="secondary-button" type="button" onClick={() => setIsOpen(false)}>{t('Отмена')}</button></div></form></Modal>}
      {deleteTarget && <DeleteConfirmModal entityName={config.singular} itemName={entity === 'warehouses' ? deleteTarget.name : t(deleteTarget.name)} onCancel={() => setDeleteTarget(null)} onConfirm={async () => { if (await remove(deleteTarget.id)) setDeleteTarget(null) }} />}
    </Shell>
  )
}

export function WarehouseCategoriesPage(props) { return <SimpleSettingsPage {...props} entity="categories" /> }
export function WarehouseUnitsPage(props) { return <SimpleSettingsPage {...props} entity="units" /> }
export function WarehousesPage(props) { return <SimpleSettingsPage {...props} entity="warehouses" /> }

export function WarehouseItemsPage({ onLogout, token, user }) {
  const { items, error, save, remove } = useWarehouseSettings(token, 'items')
  const [categories, setCategories] = useState([])
  const [units, setUnits] = useState([])
  const empty = useMemo(() => ({ id: null, name: '', category_id: '', unit_id: '', is_active: true }), [])
  const [form, setForm] = useState(empty)
  const [isOpen, setIsOpen] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState(null)
  const controls = useListControls(items, (item) => [item.name, t(item.category.name), t(item.unit.name)].join(' '))

  useEffect(() => {
    Promise.all([
      apiRequest('/api/warehouse/settings/categories/', token),
      apiRequest('/api/warehouse/settings/units/', token),
    ]).then(([categoryData, unitData]) => { setCategories(categoryData.items); setUnits(unitData.items) })
  }, [token])

  function edit(item = empty) {
    setForm(item.id ? { id: item.id, name: item.name, category_id: item.category_id, unit_id: item.unit_id, is_active: item.is_active } : empty)
    setIsOpen(true)
  }

  return (
    <Shell title={t('Номенклатура')} onLogout={onLogout} user={user}>
      <PageHeader eyebrow={t('Настройки склада')} title={t('Номенклатура')} description={t('Карточки учитываемых материалов, запчастей и готовой продукции.')} />
      {error && <p className="access-error">{t(error)}</p>}
      <section className="access-grid"><article className="access-card">
        <div className="panel-heading"><div><h3>{t('Товары и материалы')}</h3></div><button type="button" onClick={() => edit()}>{t('Создать')}</button></div>
        <ListControls {...controls} onPageChange={controls.setCurrentPage} onSearchChange={controls.setSearchQuery} />
        <div className="entity-list">{controls.paginatedItems.map((item) => <div className="entity-row" key={item.id}><div><strong>{item.name}</strong><span>{t(item.category.name)} · {t(item.unit.name)} ({t(item.unit.symbol)}{t(') · последняя цена ')}{formatMoney(item.last_purchase_price)}</span></div><div className="row-actions"><button type="button" onClick={() => edit(item)}>{t('Изменить')}</button><button className="danger-button" type="button" onClick={() => setDeleteTarget(item)}>{t('Удалить')}</button></div></div>)}</div>
      </article></section>
      {isOpen && <Modal title={form.id ? t('Изменить номенклатуру') : t('Новая номенклатура')} onClose={() => setIsOpen(false)}><form className="crud-form" onSubmit={async (event) => { event.preventDefault(); if (await save(form)) setIsOpen(false) }}><label><span>{t('Название')}</span><input required value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} /></label><label><span>{t('Категория')}</span><select required value={form.category_id} onChange={(event) => setForm({ ...form, category_id: Number(event.target.value) })}><option value="">{t('Выберите категорию')}</option>{categories.map((category) => <option key={category.id} value={category.id}>{t(category.name)}</option>)}</select></label><label><span>{t('Единица измерения')}</span><select required value={form.unit_id} onChange={(event) => setForm({ ...form, unit_id: Number(event.target.value) })}><option value="">{t('Выберите единицу')}</option>{units.map((unit) => <option key={unit.id} value={unit.id}>{t(unit.name)} ({t(unit.symbol)})</option>)}</select></label><label className="checkbox-row"><input checked={form.is_active} type="checkbox" onChange={(event) => setForm({ ...form, is_active: event.target.checked })} /><span>{t('Активно')}</span></label><div className="form-actions"><button type="submit">{t('Сохранить')}</button><button className="secondary-button" type="button" onClick={() => setIsOpen(false)}>{t('Отмена')}</button></div></form></Modal>}
      {deleteTarget && <DeleteConfirmModal entityName={t('номенклатуру')} itemName={deleteTarget.name} onCancel={() => setDeleteTarget(null)} onConfirm={async () => { if (await remove(deleteTarget.id)) setDeleteTarget(null) }} />}
    </Shell>
  )
}
