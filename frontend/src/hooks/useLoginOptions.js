import { useEffect, useState } from 'react'
import { apiRequest } from '../api/client'

const initialOptions = { logins: [], error: '', isLoading: true }

export function useLoginOptions() {
  const [options, setOptions] = useState(initialOptions)
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    apiRequest('/api/auth/login-options/', null, { cache: 'no-store', signal: controller.signal })
      .then((data) => {
        if (!Array.isArray(data.items) || !data.items.every((login) => typeof login === 'string')) throw new Error('Invalid login options')
        if (!controller.signal.aborted) setOptions({ logins: data.items, error: '', isLoading: false })
      })
      .catch(() => {
        if (!controller.signal.aborted) {
          setOptions({ logins: [], error: 'Не удалось загрузить список логинов.', isLoading: false })
        }
      })
    return () => controller.abort()
  }, [attempt])

  function retry() {
    setOptions(initialOptions)
    setAttempt((value) => value + 1)
  }

  return { ...options, retry }
}
