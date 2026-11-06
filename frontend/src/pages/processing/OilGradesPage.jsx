import { useState } from 'react'
import { DashboardShell } from '../../components/Layout/DashboardShell'
import { ListControls } from '../../components/ListControls/ListControls'
import { DeleteConfirmModal, Modal } from '../../components/Modal/Modal'
import { emptyOilGradeForm } from '../../constants/forms'
import { useListControls } from '../../hooks/useListControls'
import { useWarehouseSettings } from '../../hooks/useWarehouse'
import { t } from '../../i18n/core'

export function OilGradesPage({ onLogout, token, user }) {
  const { items, error, save, remove } = useWarehouseSettings(token, 'oil-grades', '/api/oil-production/grades/')
  const controls = useListControls(items, (item) => item.name)
  const [form, setForm] = useState(emptyOilGradeForm)
  const [isOpen, setIsOpen] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState(null)
  const [isSubmitting, setIsSubmitting] = useState(false)

  async function submit(event) {
    event.preventDefault()
    if (isSubmitting) return
    setIsSubmitting(true)
    try { if (await save(form)) setIsOpen(false) } finally { setIsSubmitting(false) }
  }

  return <DashboardShell title={t('Марки масел')} onLogout={onLogout} user={user}>
    <section className="page-title access-page-title"><p className="auth-eyebrow">{t('Производство масел')}</p><h1>{t('Марки масел')}</h1><p>{t('Марка связывает производственную партию и продуктовый бак. Смешивание разных марок запрещено.')}</p></section>
    {error && <p className="access-error" role="alert">{t(error)}</p>}
    <section className="access-grid"><article className="access-card">
      <div className="panel-heading"><h3>{t('Список')}</h3>{user?.is_admin && <button type="button" onClick={() => { setForm(emptyOilGradeForm); setIsOpen(true) }}>{t('Создать')}</button>}</div>
      <ListControls {...controls} onPageChange={controls.setCurrentPage} onSearchChange={controls.setSearchQuery} />
      <div className="entity-list">{controls.paginatedItems.map((item) => <div className="entity-row" key={item.id}><div><strong>{item.name}</strong><span>{t(item.is_active ? 'Активно' : 'Отключено')}</span></div>{user?.is_admin && <div className="row-actions"><button type="button" onClick={() => { setForm({ ...item }); setIsOpen(true) }}>{t('Изменить')}</button><button type="button" className="danger-button" onClick={() => setDeleteTarget(item)}>{t('Удалить')}</button></div>}</div>)}{!controls.filteredCount && <p className="empty-state">{t('Записи не найдены.')}</p>}</div>
    </article></section>
    {isOpen && <Modal title={t(form.id ? 'Изменить марку масла' : 'Новая марка масла')} onClose={() => !isSubmitting && setIsOpen(false)}><form className="crud-form" onSubmit={submit}><label><span>{t('Название')}</span><input required maxLength={120} disabled={isSubmitting} value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} /></label><label className="checkbox-row"><input type="checkbox" disabled={isSubmitting} checked={form.is_active} onChange={(event) => setForm({ ...form, is_active: event.target.checked })} />{t('Активно')}</label><div className="form-actions"><button disabled={isSubmitting} type="submit">{t('Сохранить')}</button><button type="button" className="secondary-button" disabled={isSubmitting} onClick={() => setIsOpen(false)}>{t('Отмена')}</button></div></form></Modal>}
    {deleteTarget && <DeleteConfirmModal entityName={t('марку масла')} itemName={deleteTarget.name} onCancel={() => setDeleteTarget(null)} onConfirm={async () => { if (await remove(deleteTarget.id)) setDeleteTarget(null) }} />}
  </DashboardShell>
}
