import { t } from '../../i18n/core'
import { useState } from 'react'
import { DashboardShell } from '../../components/Layout/DashboardShell'
import { ListControls } from '../../components/ListControls/ListControls'
import { DeleteConfirmModal, Modal as AccessModal } from '../../components/Modal/Modal'
import { emptyGroupForm, emptyModuleForm, emptyPermissionForm, emptyUserForm } from '../../constants/forms'
import { useAccessCrud } from '../../hooks/useAccessCrud'
import { useListControls } from '../../hooks/useListControls'

function AccessPageHeader({ description, title }) {
  return (
    <section className="page-title access-page-title">
      <p className="auth-eyebrow">RBAC</p>
      <h1>{title}</h1>
      <p>{description}</p>
    </section>
  )
}

export function AccessUsersPage({ onLogout, token, user }) {
  const { users, groups, error, saveEntity, deleteEntity } = useAccessCrud(token)
  const userControls = useListControls(users, (item) => [
    item.username,
    item.first_name,
    item.last_name,
    item.email,
    t(item.group?.name),
    item.is_active ? t('активен') : t('выключен'),
  ].join(' '))
  const [userForm, setUserForm] = useState(emptyUserForm)
  const [isFormOpen, setIsFormOpen] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState(null)

  function openCreateModal() {
    setUserForm(emptyUserForm)
    setIsFormOpen(true)
  }

  function openEditModal(item) {
    setUserForm({ ...emptyUserForm, ...item, group_id: item.group_id || '', password: '' })
    setIsFormOpen(true)
  }

  async function handleUserSubmit(event) {
    const isSaved = await saveEntity(event, 'users', userForm, () => setUserForm(emptyUserForm))
    if (isSaved) {
      setIsFormOpen(false)
    }
  }

  async function handleUserDelete() {
    const isDeleted = await deleteEntity('users', deleteTarget.id)
    if (isDeleted) {
      setDeleteTarget(null)
    }
  }

  return (
    <DashboardShell title={t('Пользователи')} onLogout={onLogout} user={user}>
      <AccessPageHeader
        title={t('Пользователи')}
        description={t('Создание пользователей и привязка каждого пользователя только к одной группе.')}
      />

      {error && <p className="access-error">{t(error)}</p>}

      <section className="access-grid">
        <article className="access-card">
          <div className="panel-heading">
            <div>
              <p className="auth-eyebrow">{t('Пользователи')}</p>
              <h3>{t('Список пользователей')}</h3>
            </div>
            <button type="button" onClick={openCreateModal}>{t('Создать')}</button>
          </div>
          <ListControls
            currentPage={userControls.currentPage}
            filteredCount={userControls.filteredCount}
            onPageChange={userControls.setCurrentPage}
            onSearchChange={userControls.setSearchQuery}
            pageCount={userControls.pageCount}
            searchQuery={userControls.searchQuery}
            totalCount={userControls.totalCount}
          />
          <div className="entity-list">
            {userControls.paginatedItems.map((item) => (
              <div className="entity-row" key={item.id}>
                <div><strong>{item.username}</strong><span>{t(item.group?.name) || t('Без группы')}</span></div>
                <div className="row-actions">
                  <button type="button" onClick={() => openEditModal(item)}>{t('Изменить')}</button>
                  <button className="danger-button" type="button" onClick={() => setDeleteTarget(item)}>{t('Удалить')}</button>
                </div>
              </div>
            ))}
            {!userControls.filteredCount && <p className="empty-state">{t('По вашему запросу ничего не найдено.')}</p>}
          </div>
        </article>
      </section>

      {isFormOpen && (
        <AccessModal title={userForm.id ? t('Редактировать пользователя') : t('Новый пользователь')} onClose={() => setIsFormOpen(false)}>
          <form className="crud-form" onSubmit={handleUserSubmit}>
            <input placeholder={t('Логин')} value={userForm.username} onChange={(event) => setUserForm({ ...userForm, username: event.target.value })} />
            <input placeholder={userForm.id ? t('Новый пароль, если нужно') : t('Пароль')} type="password" value={userForm.password} onChange={(event) => setUserForm({ ...userForm, password: event.target.value })} />
            <input placeholder={t('Имя')} value={userForm.first_name} onChange={(event) => setUserForm({ ...userForm, first_name: event.target.value })} />
            <input placeholder={t('Фамилия')} value={userForm.last_name} onChange={(event) => setUserForm({ ...userForm, last_name: event.target.value })} />
            <input placeholder={t('Электронная почта')} value={userForm.email} onChange={(event) => setUserForm({ ...userForm, email: event.target.value })} />
            <select value={userForm.group_id || ''} onChange={(event) => setUserForm({ ...userForm, group_id: event.target.value ? Number(event.target.value) : '' })}>
              <option value="">{t('Без группы')}</option>
              {groups.map((group) => <option key={group.id} value={group.id}>{t(group.name)}</option>)}
            </select>
            <label className="inline-check">
              <input type="checkbox" checked={userForm.is_active} onChange={(event) => setUserForm({ ...userForm, is_active: event.target.checked })} />{t('Активен')}</label>
            <div className="form-actions">
              <button type="submit">{userForm.id ? t('Сохранить') : t('Создать')}</button>
              <button className="secondary-button" type="button" onClick={() => setIsFormOpen(false)}>{t('Отмена')}</button>
            </div>
          </form>
        </AccessModal>
      )}

      {deleteTarget && (
        <DeleteConfirmModal
          entityName={t('пользователя')}
          itemName={deleteTarget.username}
          onCancel={() => setDeleteTarget(null)}
          onConfirm={handleUserDelete}
        />
      )}
    </DashboardShell>
  )
}

export function AccessGroupsPage({ onLogout, token, user }) {
  const { groups, modules, permissions, error, saveEntity, deleteEntity } = useAccessCrud(token)
  const groupControls = useListControls(groups, (item) => [
    t(item.name),
    item.description,
    item.modules.map((moduleItem) => t(moduleItem.name)).join(' '),
  ].join(' '))
  const [groupForm, setGroupForm] = useState(emptyGroupForm)
  const [isFormOpen, setIsFormOpen] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState(null)

  function openCreateModal() {
    setGroupForm(emptyGroupForm)
    setIsFormOpen(true)
  }

  function openEditModal(item) {
    setGroupForm({
      id: item.id,
      name: item.name,
      description: item.description,
      module_ids: item.module_ids,
      module_permissions: Object.fromEntries(
        item.modules.map((moduleItem) => [moduleItem.id, moduleItem.permissions.map((permission) => permission.id)]),
      ),
      start_module_id: item.start_module_id || '',
    })
    setIsFormOpen(true)
  }

  async function handleGroupSubmit(event) {
    const isSaved = await saveEntity(event, 'groups', groupForm, () => setGroupForm(emptyGroupForm))
    if (isSaved) {
      setIsFormOpen(false)
    }
  }

  async function handleGroupDelete() {
    const isDeleted = await deleteEntity('groups', deleteTarget.id)
    if (isDeleted) {
      setDeleteTarget(null)
    }
  }

  function handleGroupModulesChange(event) {
    const moduleIds = Array.from(event.target.selectedOptions).map((option) => Number(option.value))
    const hasStartModule = moduleIds.map(String).includes(String(groupForm.start_module_id))
    const viewPermission = permissions.find((permission) => permission.code === 'view')
    const modulePermissions = Object.fromEntries(moduleIds.map((moduleId) => [
      moduleId,
      groupForm.module_permissions[moduleId] || (viewPermission ? [viewPermission.id] : []),
    ]))
    setGroupForm({
      ...groupForm,
      module_ids: moduleIds,
      module_permissions: modulePermissions,
      start_module_id: hasStartModule ? groupForm.start_module_id : '',
    })
  }

  function availablePermissions(moduleItem) {
    const permissionCodes = moduleItem.code === 'warehouse-accounting'
      ? ['view', 'receipt', 'issue', 'transfer', 'transfer-confirm', 'inventory']
      : moduleItem.code === 'laboratory-analysis'
        ? ['view', 'update', 'approve']
        : moduleItem.code === 'dashboard'
          ? ['view']
          : ['view', 'create', 'update', 'delete']
    return permissions.filter((permission) => permissionCodes.includes(permission.code))
  }

  function handlePermissionChange(moduleId, permissionId, isChecked) {
    const currentPermissions = groupForm.module_permissions[moduleId] || []
    setGroupForm({
      ...groupForm,
      module_permissions: {
        ...groupForm.module_permissions,
        [moduleId]: isChecked
          ? [...new Set([...currentPermissions, permissionId])]
          : currentPermissions.filter((id) => id !== permissionId),
      },
    })
  }

  return (
    <DashboardShell title={t('Группы')} onLogout={onLogout} user={user}>
      <AccessPageHeader
        title={t('Группы')}
        description={t('Группы связаны с модулями через Many To Many и определяют доступ пользователей.')}
      />

      {error && <p className="access-error">{t(error)}</p>}

      <section className="access-grid">

        <article className="access-card">
          <div className="panel-heading">
            <div>
              <p className="auth-eyebrow">{t('Группы')}</p>
              <h3>{t('Список групп')}</h3>
            </div>
            <button type="button" onClick={openCreateModal}>{t('Создать')}</button>
          </div>
          <ListControls
            currentPage={groupControls.currentPage}
            filteredCount={groupControls.filteredCount}
            onPageChange={groupControls.setCurrentPage}
            onSearchChange={groupControls.setSearchQuery}
            pageCount={groupControls.pageCount}
            searchQuery={groupControls.searchQuery}
            totalCount={groupControls.totalCount}
          />
          <div className="entity-list">
            {groupControls.paginatedItems.map((item) => (
              <div className="entity-row" key={item.id}>
                <div>
                  <strong>{t(item.name)}</strong>
                  <span>{item.modules.map((moduleItem) => t(moduleItem.name)).join(', ') || t('Без модулей')}</span>
                  <span>{t('Стартовая страница: ')}{t(item.start_module?.name) || t('автоматически')}</span>
                </div>
                <div className="row-actions">
                  <button type="button" onClick={() => openEditModal(item)}>{t('Изменить')}</button>
                  <button className="danger-button" type="button" onClick={() => setDeleteTarget(item)}>{t('Удалить')}</button>
                </div>
              </div>
            ))}
            {!groupControls.filteredCount && <p className="empty-state">{t('По вашему запросу ничего не найдено.')}</p>}
          </div>
        </article>
      </section>

      {isFormOpen && (
        <AccessModal title={groupForm.id ? t('Редактировать группу') : t('Новая группа')} onClose={() => setIsFormOpen(false)}>
          <form className="crud-form" onSubmit={handleGroupSubmit}>
            <input placeholder={t('Название группы')} value={groupForm.name} onChange={(event) => setGroupForm({ ...groupForm, name: event.target.value })} />
            <textarea placeholder={t('Описание')} value={groupForm.description} onChange={(event) => setGroupForm({ ...groupForm, description: event.target.value })} />
            <select multiple value={groupForm.module_ids.map(String)} onChange={handleGroupModulesChange}>
              {modules.map((moduleItem) => <option key={moduleItem.id} value={moduleItem.id}>{t(moduleItem.name)}</option>)}
            </select>
            <div className="module-permission-list">
              {modules
                .filter((moduleItem) => groupForm.module_ids.includes(moduleItem.id))
                .map((moduleItem) => (
                  <fieldset className="module-permission-card" key={moduleItem.id}>
                    <legend>{t(moduleItem.name)}</legend>
                    <div className="permission-checkbox-grid">
                      {availablePermissions(moduleItem).map((permission) => (
                        <label key={permission.id}>
                          <input
                            checked={(groupForm.module_permissions[moduleItem.id] || []).includes(permission.id)}
                            type="checkbox"
                            onChange={(event) => handlePermissionChange(moduleItem.id, permission.id, event.target.checked)}
                          />
                          <span>{t(permission.name)}</span>
                        </label>
                      ))}
                    </div>
                  </fieldset>
                ))}
            </div>
            <select value={groupForm.start_module_id} onChange={(event) => setGroupForm({ ...groupForm, start_module_id: event.target.value })}>
              <option value="">{t('Стартовая страница автоматически')}</option>
              {modules
                .filter((moduleItem) => groupForm.module_ids.map(String).includes(String(moduleItem.id)))
                .map((moduleItem) => <option key={moduleItem.id} value={moduleItem.id}>{t(moduleItem.name)}</option>)}
            </select>
            <div className="form-actions">
              <button type="submit">{groupForm.id ? t('Сохранить') : t('Создать')}</button>
              <button className="secondary-button" type="button" onClick={() => setIsFormOpen(false)}>{t('Отмена')}</button>
            </div>
          </form>
        </AccessModal>
      )}

      {deleteTarget && (
        <DeleteConfirmModal
          entityName={t('группу')}
          itemName={t(deleteTarget.name)}
          onCancel={() => setDeleteTarget(null)}
          onConfirm={handleGroupDelete}
        />
      )}
    </DashboardShell>
  )
}

export function AccessModulesPage({ onLogout, token, user }) {
  const { modules, error, saveEntity, deleteEntity } = useAccessCrud(token)
  const moduleControls = useListControls(modules, (item) => [
    item.code,
    t(item.name),
    item.description,
    item.default_path,
    item.is_active ? t('активен') : t('выключен'),
  ].join(' '))
  const [moduleForm, setModuleForm] = useState(emptyModuleForm)
  const [isFormOpen, setIsFormOpen] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState(null)

  function openCreateModal() {
    setModuleForm(emptyModuleForm)
    setIsFormOpen(true)
  }

  function openEditModal(item) {
    setModuleForm(item)
    setIsFormOpen(true)
  }

  async function handleModuleSubmit(event) {
    const isSaved = await saveEntity(event, 'modules', moduleForm, () => setModuleForm(emptyModuleForm))
    if (isSaved) {
      setIsFormOpen(false)
    }
  }

  async function handleModuleDelete() {
    const isDeleted = await deleteEntity('modules', deleteTarget.id)
    if (isDeleted) {
      setDeleteTarget(null)
    }
  }

  return (
    <DashboardShell title={t('Модули')} onLogout={onLogout} user={user}>
      <AccessPageHeader
        title={t('Модули')}
        description={t('Справочник функциональных модулей, которые подключаются к группам доступа.')}
      />

      {error && <p className="access-error">{t(error)}</p>}

      <section className="access-grid">

        <article className="access-card">
          <div className="panel-heading">
            <div>
              <p className="auth-eyebrow">{t('Модули')}</p>
              <h3>{t('Список модулей')}</h3>
            </div>
            <button type="button" onClick={openCreateModal}>{t('Создать')}</button>
          </div>
          <ListControls
            currentPage={moduleControls.currentPage}
            filteredCount={moduleControls.filteredCount}
            onPageChange={moduleControls.setCurrentPage}
            onSearchChange={moduleControls.setSearchQuery}
            pageCount={moduleControls.pageCount}
            searchQuery={moduleControls.searchQuery}
            totalCount={moduleControls.totalCount}
          />
          <div className="entity-list">
            {moduleControls.paginatedItems.map((item) => (
              <div className="entity-row" key={item.id}>
                <div><strong>{t(item.name)}</strong><span>{item.code} · {item.default_path || t('маршрут не задан')} · {item.is_active ? t('активен') : t('выключен')}</span></div>
                <div className="row-actions">
                  <button type="button" onClick={() => openEditModal(item)}>{t('Изменить')}</button>
                  <button className="danger-button" type="button" onClick={() => setDeleteTarget(item)}>{t('Удалить')}</button>
                </div>
              </div>
            ))}
            {!moduleControls.filteredCount && <p className="empty-state">{t('По вашему запросу ничего не найдено.')}</p>}
          </div>
        </article>
      </section>

      {isFormOpen && (
        <AccessModal title={moduleForm.id ? t('Редактировать модуль') : t('Новый модуль')} onClose={() => setIsFormOpen(false)}>
          <form className="crud-form" onSubmit={handleModuleSubmit}>
            <input placeholder={t('Код')} value={moduleForm.code} onChange={(event) => setModuleForm({ ...moduleForm, code: event.target.value })} />
            <input placeholder={t('Название')} value={moduleForm.name} onChange={(event) => setModuleForm({ ...moduleForm, name: event.target.value })} />
            <input placeholder={t('Стартовый маршрут, например /laboratory/analyses')} value={moduleForm.default_path} onChange={(event) => setModuleForm({ ...moduleForm, default_path: event.target.value })} />
            <textarea placeholder={t('Описание')} value={moduleForm.description} onChange={(event) => setModuleForm({ ...moduleForm, description: event.target.value })} />
            <label className="inline-check">
              <input type="checkbox" checked={moduleForm.is_active} onChange={(event) => setModuleForm({ ...moduleForm, is_active: event.target.checked })} />{t('Активен')}</label>
            <div className="form-actions">
              <button type="submit">{moduleForm.id ? t('Сохранить') : t('Создать')}</button>
              <button className="secondary-button" type="button" onClick={() => setIsFormOpen(false)}>{t('Отмена')}</button>
            </div>
          </form>
        </AccessModal>
      )}

      {deleteTarget && (
        <DeleteConfirmModal
          entityName={t('модуль')}
          itemName={t(deleteTarget.name)}
          onCancel={() => setDeleteTarget(null)}
          onConfirm={handleModuleDelete}
        />
      )}
    </DashboardShell>
  )
}

export function AccessPermissionsPage({ onLogout, token, user }) {
  const { permissions, error, saveEntity, deleteEntity } = useAccessCrud(token)
  const permissionControls = useListControls(permissions, (item) => [
    item.code,
    t(item.name),
    item.description,
  ].join(' '))
  const [permissionForm, setPermissionForm] = useState(emptyPermissionForm)
  const [isFormOpen, setIsFormOpen] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState(null)

  function openCreateModal() {
    setPermissionForm(emptyPermissionForm)
    setIsFormOpen(true)
  }

  function openEditModal(item) {
    setPermissionForm(item)
    setIsFormOpen(true)
  }

  async function handlePermissionSubmit(event) {
    const isSaved = await saveEntity(event, 'permissions', permissionForm, () => setPermissionForm(emptyPermissionForm))
    if (isSaved) {
      setIsFormOpen(false)
    }
  }

  async function handlePermissionDelete() {
    const isDeleted = await deleteEntity('permissions', deleteTarget.id)
    if (isDeleted) {
      setDeleteTarget(null)
    }
  }

  return (
    <DashboardShell title={t('Разрешения')} onLogout={onLogout} user={user}>
      <AccessPageHeader
        title={t('Разрешения')}
        description={t('Справочник разрешений для дальнейшего расширения модели контроля доступа.')}
      />

      {error && <p className="access-error">{t(error)}</p>}

      <section className="access-grid">

        <article className="access-card">
          <div className="panel-heading">
            <div>
              <p className="auth-eyebrow">{t('Разрешения')}</p>
              <h3>{t('Список разрешений')}</h3>
            </div>
            <button type="button" onClick={openCreateModal}>{t('Создать')}</button>
          </div>
          <ListControls
            currentPage={permissionControls.currentPage}
            filteredCount={permissionControls.filteredCount}
            onPageChange={permissionControls.setCurrentPage}
            onSearchChange={permissionControls.setSearchQuery}
            pageCount={permissionControls.pageCount}
            searchQuery={permissionControls.searchQuery}
            totalCount={permissionControls.totalCount}
          />
          <div className="entity-list">
            {permissionControls.paginatedItems.map((item) => (
              <div className="entity-row" key={item.id}>
                <div><strong>{t(item.name)}</strong><span>{item.code}</span></div>
                <div className="row-actions">
                  <button type="button" onClick={() => openEditModal(item)}>{t('Изменить')}</button>
                  <button className="danger-button" type="button" onClick={() => setDeleteTarget(item)}>{t('Удалить')}</button>
                </div>
              </div>
            ))}
            {!permissionControls.filteredCount && <p className="empty-state">{t('По вашему запросу ничего не найдено.')}</p>}
          </div>
        </article>
      </section>

      {isFormOpen && (
        <AccessModal title={permissionForm.id ? t('Редактировать разрешение') : t('Новое разрешение')} onClose={() => setIsFormOpen(false)}>
          <form className="crud-form" onSubmit={handlePermissionSubmit}>
            <input placeholder={t('Код')} value={permissionForm.code} onChange={(event) => setPermissionForm({ ...permissionForm, code: event.target.value })} />
            <input placeholder={t('Название')} value={permissionForm.name} onChange={(event) => setPermissionForm({ ...permissionForm, name: event.target.value })} />
            <textarea placeholder={t('Описание')} value={permissionForm.description} onChange={(event) => setPermissionForm({ ...permissionForm, description: event.target.value })} />
            <div className="form-actions">
              <button type="submit">{permissionForm.id ? t('Сохранить') : t('Создать')}</button>
              <button className="secondary-button" type="button" onClick={() => setIsFormOpen(false)}>{t('Отмена')}</button>
            </div>
          </form>
        </AccessModal>
      )}

      {deleteTarget && (
        <DeleteConfirmModal
          entityName={t('разрешение')}
          itemName={t(deleteTarget.name)}
          onCancel={() => setDeleteTarget(null)}
          onConfirm={handlePermissionDelete}
        />
      )}
    </DashboardShell>
  )
}
