import { useEffect, useState } from 'react'
import { apiRequest } from '../api/client'

export function useLoginOptions() {
  const [logins, setLogins] = useState([])
  const [error, setError] = useState('')

  useEffect(() => {
    const controller = new AbortController()
    apiRequest('/api/auth/login-options/', null, { cache: 'no-store', signal: controller.signal })
      .then((data) => {
        if (!Array.isArray(data.items) || !data.items.every((login) => typeof login === 'string')) throw new Error('Invalid login options')
        if (!controller.signal.aborted) setLogins(data.items)
      })
      .catch(() => {
        if (!controller.signal.aborted) setError('Не удалось загрузить список логинов. Введите логин вручную.')
      })
    return () => controller.abort()
  }, [])

  return { logins, error }
}
