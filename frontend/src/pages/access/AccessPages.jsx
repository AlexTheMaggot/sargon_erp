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
    item.group?.name,
    item.is_active ? 'активен' : 'выключен',
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
    <DashboardShell title="Пользователи" onLogout={onLogout} user={user}>
      <AccessPageHeader
        title="Пользователи"
        description="Создание пользователей и привязка каждого пользователя только к одной группе."
      />

      {error && <p className="access-error">{error}</p>}

      <section className="access-grid">
        <article className="access-card">
          <div className="panel-heading">
            <div>
              <p className="auth-eyebrow">Пользователи</p>
              <h3>Список пользователей</h3>
            </div>
            <button type="button" onClick={openCreateModal}>Создать</button>
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
                <div><strong>{item.username}</strong><span>{item.group?.name || 'Без группы'}</span></div>
                <div className="row-actions">
                  <button type="button" onClick={() => openEditModal(item)}>Изменить</button>
                  <button className="danger-button" type="button" onClick={() => setDeleteTarget(item)}>Удалить</button>
                </div>
              </div>
            ))}
            {!userControls.filteredCount && <p className="empty-state">По вашему запросу ничего не найдено.</p>}
          </div>
        </article>
      </section>

      {isFormOpen && (
        <AccessModal title={userForm.id ? 'Редактировать пользователя' : 'Новый пользователь'} onClose={() => setIsFormOpen(false)}>
          <form className="crud-form" onSubmit={handleUserSubmit}>
            <input placeholder="Логин" value={userForm.username} onChange={(event) => setUserForm({ ...userForm, username: event.target.value })} />
            <input placeholder={userForm.id ? 'Новый пароль, если нужно' : 'Пароль'} type="password" value={userForm.password} onChange={(event) => setUserForm({ ...userForm, password: event.target.value })} />
            <input placeholder="Имя" value={userForm.first_name} onChange={(event) => setUserForm({ ...userForm, first_name: event.target.value })} />
            <input placeholder="Фамилия" value={userForm.last_name} onChange={(event) => setUserForm({ ...userForm, last_name: event.target.value })} />
            <input placeholder="Email" value={userForm.email} onChange={(event) => setUserForm({ ...userForm, email: event.target.value })} />
            <select value={userForm.group_id || ''} onChange={(event) => setUserForm({ ...userForm, group_id: event.target.value ? Number(event.target.value) : '' })}>
              <option value="">Без группы</option>
              {groups.map((group) => <option key={group.id} value={group.id}>{group.name}</option>)}
            </select>
            <label className="inline-check">
              <input type="checkbox" checked={userForm.is_active} onChange={(event) => setUserForm({ ...userForm, is_active: event.target.checked })} />
              Активен
            </label>
            <div className="form-actions">
              <button type="submit">{userForm.id ? 'Сохранить' : 'Создать'}</button>
              <button className="secondary-button" type="button" onClick={() => setIsFormOpen(false)}>Отмена</button>
            </div>
          </form>
        </AccessModal>
      )}

      {deleteTarget && (
        <DeleteConfirmModal
          entityName="пользователя"
          itemName={deleteTarget.username}
          onCancel={() => setDeleteTarget(null)}
          onConfirm={handleUserDelete}
        />
      )}
    </DashboardShell>
  )
}

export function AccessGroupsPage({ onLogout, token, user }) {
  const { groups, modules, error, saveEntity, deleteEntity } = useAccessCrud(token)
  const groupControls = useListControls(groups, (item) => [
    item.name,
    item.description,
    item.modules.map((moduleItem) => moduleItem.name).join(' '),
  ].join(' '))
  const [groupForm, setGroupForm] = useState(emptyGroupForm)
  const [isFormOpen, setIsFormOpen] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState(null)

  function openCreateModal() {
    setGroupForm(emptyGroupForm)
    setIsFormOpen(true)
  }

  function openEditModal(item) {
    setGroupForm({ id: item.id, name: item.name, description: item.description, module_ids: item.module_ids })
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

  return (
    <DashboardShell title="Группы" onLogout={onLogout} user={user}>
      <AccessPageHeader
        title="Группы"
        description="Группы связаны с модулями через Many To Many и определяют доступ пользователей."
      />

      {error && <p className="access-error">{error}</p>}

      <section className="access-grid">

        <article className="access-card">
          <div className="panel-heading">
            <div>
              <p className="auth-eyebrow">Группы</p>
              <h3>Список групп</h3>
            </div>
            <button type="button" onClick={openCreateModal}>Создать</button>
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
                <div><strong>{item.name}</strong><span>{item.modules.map((moduleItem) => moduleItem.name).join(', ') || 'Без модулей'}</span></div>
                <div className="row-actions">
                  <button type="button" onClick={() => openEditModal(item)}>Изменить</button>
                  <button className="danger-button" type="button" onClick={() => setDeleteTarget(item)}>Удалить</button>
                </div>
              </div>
            ))}
            {!groupControls.filteredCount && <p className="empty-state">По вашему запросу ничего не найдено.</p>}
          </div>
        </article>
      </section>

      {isFormOpen && (
        <AccessModal title={groupForm.id ? 'Редактировать группу' : 'Новая группа'} onClose={() => setIsFormOpen(false)}>
          <form className="crud-form" onSubmit={handleGroupSubmit}>
            <input placeholder="Название группы" value={groupForm.name} onChange={(event) => setGroupForm({ ...groupForm, name: event.target.value })} />
            <textarea placeholder="Описание" value={groupForm.description} onChange={(event) => setGroupForm({ ...groupForm, description: event.target.value })} />
            <select multiple value={groupForm.module_ids.map(String)} onChange={(event) => setGroupForm({ ...groupForm, module_ids: Array.from(event.target.selectedOptions).map((option) => Number(option.value)) })}>
              {modules.map((moduleItem) => <option key={moduleItem.id} value={moduleItem.id}>{moduleItem.name}</option>)}
            </select>
            <div className="form-actions">
              <button type="submit">{groupForm.id ? 'Сохранить' : 'Создать'}</button>
              <button className="secondary-button" type="button" onClick={() => setIsFormOpen(false)}>Отмена</button>
            </div>
          </form>
        </AccessModal>
      )}

      {deleteTarget && (
        <DeleteConfirmModal
          entityName="группу"
          itemName={deleteTarget.name}
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
    item.name,
    item.description,
    item.is_active ? 'активен' : 'выключен',
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
    <DashboardShell title="Модули" onLogout={onLogout} user={user}>
      <AccessPageHeader
        title="Модули"
        description="Справочник функциональных модулей, которые подключаются к группам доступа."
      />

      {error && <p className="access-error">{error}</p>}

      <section className="access-grid">

        <article className="access-card">
          <div className="panel-heading">
            <div>
              <p className="auth-eyebrow">Модули</p>
              <h3>Список модулей</h3>
            </div>
            <button type="button" onClick={openCreateModal}>Создать</button>
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
                <div><strong>{item.name}</strong><span>{item.code} · {item.is_active ? 'активен' : 'выключен'}</span></div>
                <div className="row-actions">
                  <button type="button" onClick={() => openEditModal(item)}>Изменить</button>
                  <button className="danger-button" type="button" onClick={() => setDeleteTarget(item)}>Удалить</button>
                </div>
              </div>
            ))}
            {!moduleControls.filteredCount && <p className="empty-state">По вашему запросу ничего не найдено.</p>}
          </div>
        </article>
      </section>

      {isFormOpen && (
        <AccessModal title={moduleForm.id ? 'Редактировать модуль' : 'Новый модуль'} onClose={() => setIsFormOpen(false)}>
          <form className="crud-form" onSubmit={handleModuleSubmit}>
            <input placeholder="Код" value={moduleForm.code} onChange={(event) => setModuleForm({ ...moduleForm, code: event.target.value })} />
            <input placeholder="Название" value={moduleForm.name} onChange={(event) => setModuleForm({ ...moduleForm, name: event.target.value })} />
            <textarea placeholder="Описание" value={moduleForm.description} onChange={(event) => setModuleForm({ ...moduleForm, description: event.target.value })} />
            <label className="inline-check">
              <input type="checkbox" checked={moduleForm.is_active} onChange={(event) => setModuleForm({ ...moduleForm, is_active: event.target.checked })} />
              Активен
            </label>
            <div className="form-actions">
              <button type="submit">{moduleForm.id ? 'Сохранить' : 'Создать'}</button>
              <button className="secondary-button" type="button" onClick={() => setIsFormOpen(false)}>Отмена</button>
            </div>
          </form>
        </AccessModal>
      )}

      {deleteTarget && (
        <DeleteConfirmModal
          entityName="модуль"
          itemName={deleteTarget.name}
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
    item.name,
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
    <DashboardShell title="Разрешения" onLogout={onLogout} user={user}>
      <AccessPageHeader
        title="Разрешения"
        description="Справочник разрешений для дальнейшего расширения модели контроля доступа."
      />

      {error && <p className="access-error">{error}</p>}

      <section className="access-grid">

        <article className="access-card">
          <div className="panel-heading">
            <div>
              <p className="auth-eyebrow">Разрешения</p>
              <h3>Список разрешений</h3>
            </div>
            <button type="button" onClick={openCreateModal}>Создать</button>
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
                <div><strong>{item.name}</strong><span>{item.code}</span></div>
                <div className="row-actions">
                  <button type="button" onClick={() => openEditModal(item)}>Изменить</button>
                  <button className="danger-button" type="button" onClick={() => setDeleteTarget(item)}>Удалить</button>
                </div>
              </div>
            ))}
            {!permissionControls.filteredCount && <p className="empty-state">По вашему запросу ничего не найдено.</p>}
          </div>
        </article>
      </section>

      {isFormOpen && (
        <AccessModal title={permissionForm.id ? 'Редактировать разрешение' : 'Новое разрешение'} onClose={() => setIsFormOpen(false)}>
          <form className="crud-form" onSubmit={handlePermissionSubmit}>
            <input placeholder="Код" value={permissionForm.code} onChange={(event) => setPermissionForm({ ...permissionForm, code: event.target.value })} />
            <input placeholder="Название" value={permissionForm.name} onChange={(event) => setPermissionForm({ ...permissionForm, name: event.target.value })} />
            <textarea placeholder="Описание" value={permissionForm.description} onChange={(event) => setPermissionForm({ ...permissionForm, description: event.target.value })} />
            <div className="form-actions">
              <button type="submit">{permissionForm.id ? 'Сохранить' : 'Создать'}</button>
              <button className="secondary-button" type="button" onClick={() => setIsFormOpen(false)}>Отмена</button>
            </div>
          </form>
        </AccessModal>
      )}

      {deleteTarget && (
        <DeleteConfirmModal
          entityName="разрешение"
          itemName={deleteTarget.name}
          onCancel={() => setDeleteTarget(null)}
          onConfirm={handlePermissionDelete}
        />
      )}
    </DashboardShell>
  )
}
