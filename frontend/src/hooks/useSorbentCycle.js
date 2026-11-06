import { useEffect, useRef, useState } from 'react'
import { apiRequest } from '../api/client'

const path = '/api/processing/sorbent-cycle/'

export function useSorbentCycle(token) {
  const [data, setData] = useState(null)
  const [loadError, setLoadError] = useState('')
  const [actionError, setActionError] = useState('')
  const [revision, setRevision] = useState(0)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const pending = useRef(false)

  useEffect(() => {
    let active = true
    let loading = false
    const refresh = async () => {
      if (loading) return
      loading = true
      try {
        const result = await apiRequest(path, token)
        if (active) {
          setData(result)
          setLoadError('')
        }
      } catch (error) {
        if (active) setLoadError(error.message)
      } finally {
        loading = false
      }
    }
    refresh()
    const timer = window.setInterval(refresh, 15000)
    window.addEventListener('focus', refresh)
    return () => {
      active = false
      window.clearInterval(timer)
      window.removeEventListener('focus', refresh)
    }
  }, [token, revision])

  async function perform(url, body) {
    if (pending.current) return null
    pending.current = true
    setIsSubmitting(true)
    setActionError('')
    try {
      const result = await apiRequest(url, token, { method: 'POST', body: JSON.stringify(body) })
      setRevision((current) => current + 1)
      return result
    } catch (error) {
      setActionError(error.message)
      return null
    } finally {
      pending.current = false
      setIsSubmitting(false)
    }
  }

  return { data, error: actionError || loadError, isSubmitting,
    submit: (body) => perform(path, body),
    reverse: (id, body) => perform(`${path}${id}/reverse/`, body),
  }
}
