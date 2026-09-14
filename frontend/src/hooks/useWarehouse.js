import { useCallback, useEffect, useState } from 'react'
import { apiRequest } from '../api/client'

export function useWarehouseReferenceData(token) {
  const [data, setData] = useState({ warehouses: [], items: [], suppliers: [] })
  const [error, setError] = useState('')

  const reload = useCallback(async () => {
    try {
      setData(await apiRequest('/api/warehouse/reference-data/', token))
      setError('')
    } catch (loadError) {
      setError(loadError.message)
    }
  }, [token])

  useEffect(() => {
    let isCancelled = false
    apiRequest('/api/warehouse/reference-data/', token)
      .then((nextData) => { if (!isCancelled) setData(nextData) })
      .catch((loadError) => { if (!isCancelled) setError(loadError.message) })
    return () => { isCancelled = true }
  }, [token])
  return { ...data, error, reload }
}

export function useWarehouseDocuments(token, documentType) {
  const [documents, setDocuments] = useState([])
  const [error, setError] = useState('')

  const reload = useCallback(async () => {
    try {
      const data = await apiRequest(`/api/warehouse/documents/?type=${documentType}`, token)
      setDocuments(data.items)
      setError('')
    } catch (loadError) {
      setError(loadError.message)
    }
  }, [documentType, token])

  useEffect(() => {
    let isCancelled = false
    apiRequest(`/api/warehouse/documents/?type=${documentType}`, token)
      .then((data) => { if (!isCancelled) setDocuments(data.items) })
      .catch((loadError) => { if (!isCancelled) setError(loadError.message) })
    return () => { isCancelled = true }
  }, [documentType, token])

  async function perform(path, options = {}) {
    setError('')
    try {
      const data = await apiRequest(path, token, options)
      await reload()
      return data
    } catch (actionError) {
      setError(actionError.message)
      return null
    }
  }

  return {
    documents,
    error,
    createDocument: (payload) => perform('/api/warehouse/documents/', { method: 'POST', body: JSON.stringify(payload) }),
    postDocument: (id) => perform(`/api/warehouse/documents/${id}/post/`, { method: 'POST' }),
    decideTransfer: (id, decision) => perform(`/api/warehouse/documents/${id}/transfer-decision/`, { method: 'POST', body: JSON.stringify({ decision }) }),
    cancelDocument: (id) => perform(`/api/warehouse/documents/${id}/cancel/`, { method: 'POST' }),
    deleteDocument: (id) => perform(`/api/warehouse/documents/${id}/`, { method: 'DELETE' }),
  }
}

export function useWarehouseOverview(token) {
  const [overview, setOverview] = useState({ balances: [], total_value: '0.00', warehouse_count: 0, item_count: 0, in_transit_count: 0 })
  const [error, setError] = useState('')

  useEffect(() => {
    apiRequest('/api/warehouse/overview/', token)
      .then(setOverview)
      .catch((loadError) => setError(loadError.message))
  }, [token])

  return { overview, error }
}

export function useWarehouseSettings(token, entity) {
  const [items, setItems] = useState([])
  const [error, setError] = useState('')
  const path = `/api/warehouse/settings/${entity}/`

  const reload = useCallback(async () => {
    try {
      const data = await apiRequest(path, token)
      setItems(data.items)
      setError('')
    } catch (loadError) {
      setError(loadError.message)
    }
  }, [path, token])

  useEffect(() => {
    let isCancelled = false
    apiRequest(path, token)
      .then((data) => { if (!isCancelled) setItems(data.items) })
      .catch((loadError) => { if (!isCancelled) setError(loadError.message) })
    return () => { isCancelled = true }
  }, [path, token])

  async function save(form) {
    const isEdit = Boolean(form.id)
    const payload = { ...form }
    delete payload.id
    try {
      await apiRequest(`${path}${isEdit ? `${form.id}/` : ''}`, token, {
        method: isEdit ? 'PATCH' : 'POST',
        body: JSON.stringify(payload),
      })
      await reload()
      setError('')
      return true
    } catch (saveError) {
      setError(saveError.message)
      return false
    }
  }

  async function remove(id) {
    try {
      await apiRequest(`${path}${id}/`, token, { method: 'DELETE' })
      await reload()
      setError('')
      return true
    } catch (deleteError) {
      setError(deleteError.message)
      return false
    }
  }

  return { items, error, save, remove, reload }
}
