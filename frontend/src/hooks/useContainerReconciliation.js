import { useEffect, useState } from 'react'
import { apiRequest } from '../api/client'
import { reconciliationApi } from '../constants/containerReconciliation'

export function useContainerReconciliation(token, page) {
  const [listing, setListing] = useState(null)
  const [error, setError] = useState('')

  async function loadListing(pageNumber = page) {
    const result = await apiRequest(`${reconciliationApi}?page=${pageNumber}`, token)
    setListing(result)
    return result
  }

  useEffect(() => {
    let cancelled = false
    apiRequest(`${reconciliationApi}?page=${page}`, token)
      .then((result) => { if (!cancelled) setListing(result) })
      .catch((loadError) => { if (!cancelled) setError(loadError.message) })
    return () => { cancelled = true }
  }, [token, page])

  return {
    listing, error, setError, loadListing,
    loadDetail: (id) => apiRequest(`${reconciliationApi}${id}/`, token),
    save: (data) => apiRequest(reconciliationApi, token, { method: 'POST', body: JSON.stringify(data) }),
  }
}
