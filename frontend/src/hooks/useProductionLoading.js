import { useCallback, useEffect, useState } from 'react'
import { apiRequest } from '../api/client'

export function useProductionLoading(token, target, workflow = 'loadings') {
  const [reference, setReference] = useState({ warehouses: [], materials: [], products: [], production_balances: [], production_sources: [] })
  const [documents, setDocuments] = useState([])
  const [loadError, setLoadError] = useState('')
  const [actionError, setActionError] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [revision, setRevision] = useState(0)
  const path = `/api/warehouse/production-${workflow}/${target}/`

  useEffect(() => {
    let active = true
    let loading = false
    const refresh = async () => {
      if (loading) return
      loading = true
      try {
        const [nextReference, result] = await Promise.all([
          apiRequest(`${path}reference-data/`, token),
          apiRequest(path, token),
        ])
        if (active) {
          setReference(nextReference)
          setDocuments(result.items)
          setLoadError('')
        }
      } catch (error) {
        if (active) setLoadError(error.message)
      } finally {
        loading = false
      }
    }
    refresh()
    const interval = window.setInterval(refresh, 15000)
    window.addEventListener('focus', refresh)
    return () => {
      active = false
      window.clearInterval(interval)
      window.removeEventListener('focus', refresh)
    }
  }, [path, revision, token])

  const reload = useCallback(() => setRevision((value) => value + 1), [])

  async function perform(url, payload) {
    if (isSubmitting) return null
    setIsSubmitting(true)
    setActionError('')
    try {
      const result = await apiRequest(url, token, { method: 'POST', body: JSON.stringify(payload) })
      reload()
      return result
    } catch (error) {
      setActionError(error.message)
      return null
    } finally {
      setIsSubmitting(false)
    }
  }

  return {
    ...reference, documents, error: actionError || loadError, isSubmitting,
    submit: (payload) => perform(path, payload),
    cancel: (documentId) => perform(workflow === 'outputs' ? `${path}${documentId}/cancel/` : `/api/warehouse/documents/${documentId}/cancel/`, {}),
  }
}
