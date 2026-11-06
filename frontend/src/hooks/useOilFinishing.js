import { useCallback, useEffect, useRef, useState } from 'react'
import { apiRequest } from '../api/client'
import { oilContainerApiPath, oilFinishingForms } from '../constants/oilFinishing'

export function useOilFinishing(token, step, page) {
  const [sources, setSources] = useState([])
  const [destinations, setDestinations] = useState([])
  const [history, setHistory] = useState({ items: [], total: 0, page: 1, page_count: 1 })
  const [error, setError] = useState('')
  const sequence = useRef(0)
  const config = oilFinishingForms[step]
  const url = `/api/processing/oil-movements/${step}/`
  const reload = useCallback(async () => {
    const request = ++sequence.current
    try {
      const [sourceData, destinationData, historyData] = await Promise.all([
        Promise.all(config.sources.map((kind) => apiRequest(oilContainerApiPath(kind), token))),
        Promise.all(config.destinations.map((kind) => apiRequest(oilContainerApiPath(kind), token))),
        apiRequest(`${url}?page=${page}`, token),
      ])
      if (request !== sequence.current) return
      setSources(sourceData.flatMap((data) => data.items))
      setDestinations(destinationData.flatMap((data) => data.items))
      setHistory(historyData)
      setError('')
    } catch (loadError) {
      if (request === sequence.current) setError(loadError.message)
    }
  }, [config, page, token, url])
  useEffect(() => {
    const initialTimer = window.setTimeout(reload, 0)
    const timer = window.setInterval(reload, 15000)
    return () => {
      sequence.current += 1
      window.clearTimeout(initialTimer)
      window.clearInterval(timer)
    }
  }, [reload])

  async function submit(form) {
    try {
      const result = await apiRequest(url, token, { method: 'POST', body: JSON.stringify(form) })
      await reload()
      return result
    } catch (submitError) {
      setError(submitError.message)
      await reload()
      setError(submitError.message)
      return null
    }
  }
  return { sources, destinations, history, error, submit }
}
