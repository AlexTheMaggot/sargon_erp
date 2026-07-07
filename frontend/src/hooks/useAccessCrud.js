import { useEffect, useState } from 'react'
import { apiRequest, fetchAccessData } from '../api/client'

export function useAccessCrud(token) {
  const [users, setUsers] = useState([])
  const [groups, setGroups] = useState([])
  const [modules, setModules] = useState([])
  const [permissions, setPermissions] = useState([])
  const [error, setError] = useState('')

  function applyAccessData(data) {
    setUsers(data.users)
    setGroups(data.groups)
    setModules(data.modules)
    setPermissions(data.permissions)
  }

  async function loadAccessData() {
    applyAccessData(await fetchAccessData(token))
  }

  useEffect(() => {
    let isCancelled = false

    fetchAccessData(token)
      .then((data) => {
        if (!isCancelled) {
          applyAccessData(data)
        }
      })
      .catch((loadError) => {
        if (!isCancelled) {
          setError(loadError.message)
        }
      })

    return () => {
      isCancelled = true
    }
  }, [token])

  async function saveEntity(event, entity, form, resetForm) {
    event.preventDefault()
    setError('')

    const isEdit = Boolean(form.id)
    const path = `/api/access/${entity}/${isEdit ? `${form.id}/` : ''}`
    const payload = { ...form }
    delete payload.id

    if (entity === 'users' && !payload.password) {
      delete payload.password
    }

    try {
      await apiRequest(path, token, {
        method: isEdit ? 'PATCH' : 'POST',
        body: JSON.stringify(payload),
      })
      resetForm()
      await loadAccessData()
      return true
    } catch (saveError) {
      setError(saveError.message)
      return false
    }
  }

  async function deleteEntity(entity, id) {
    setError('')
    try {
      await apiRequest(`/api/access/${entity}/${id}/`, token, { method: 'DELETE' })
      await loadAccessData()
      return true
    } catch (deleteError) {
      setError(deleteError.message)
      return false
    }
  }

  return {
    users,
    groups,
    modules,
    permissions,
    error,
    saveEntity,
    deleteEntity,
  }
}
