import { useCallback, useEffect, useRef, useState } from 'react'
import { apiRequest } from '../api/client'

export function useOilManufacturing(token, step) {
  const [data, setData] = useState({ items: [] })
  const [error, setError] = useState('')
  const sequence = useRef(0)
  const url = `/api/oil-production/operations/${step}/`
  const reload = useCallback(async () => {
    const request = ++sequence.current
    try {
      const result = await apiRequest(url, token)
      if (request === sequence.current) {
        setData(result)
        setError('')
      }
    } catch (loadError) {
      if (request === sequence.current) setError(loadError.message)
    }
  }, [token, url])
  useEffect(() => {
    const initial = window.setTimeout(reload, 0)
    const timer = window.setInterval(reload, 15000)
    return () => {
      sequence.current += 1
      window.clearTimeout(initial)
      window.clearInterval(timer)
    }
  }, [reload])
  async function perform(path, payload) {
    try {
      const result = await apiRequest(path, token, { method: 'POST', body: JSON.stringify(payload) })
      await reload()
      return result
    } catch (actionError) {
      await reload()
      setError(actionError.message)
      return null
    }
  }
  return {
    data, error,
    submit: (payload) => perform(url, payload),
    complete: (id) => perform(`/api/oil-production/batches/${id}/complete/`, { equipment_empty: true }),
    cancel: (id, reason) => perform(`/api/oil-production/batches/${id}/cancel/`, { reason }),
  }
}
