import { useEffect, useState } from 'react'
import { apiRequest } from '../api/client'

async function fetchKnowledgeData(token) {
  const [categories, articles] = await Promise.all([
    apiRequest('/api/knowledge/categories/', token),
    apiRequest('/api/knowledge/articles/', token),
  ])
  return { categories: categories.items, articles: articles.items }
}

export function useKnowledgeBase(token) {
  const [data, setData] = useState({ categories: [], articles: [] })
  const [isLoading, setIsLoading] = useState(true)
  const [isSaving, setIsSaving] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    let isCancelled = false
    fetchKnowledgeData(token)
      .then((result) => { if (!isCancelled) setData(result) })
      .catch((loadError) => { if (!isCancelled) setError(loadError.message) })
      .finally(() => { if (!isCancelled) setIsLoading(false) })
    return () => { isCancelled = true }
  }, [token])

  async function saveEntity(entity, form) {
    setIsSaving(true)
    setError('')
    const { id, ...payload } = form
    try {
      const result = await apiRequest(`/api/knowledge/${entity}/${id ? `${id}/` : ''}`, token, {
        method: id ? 'PATCH' : 'POST',
        body: JSON.stringify(payload),
      })
      setData((current) => ({
        ...current,
        [entity]: id
          ? current[entity].map((item) => item.id === id ? result : item)
          : [...current[entity], result],
      }))
      if (entity === 'categories') {
        setData((current) => ({
          ...current,
          articles: current.articles.map((article) => article.category_id === result.id ? { ...article, category: result } : article),
        }))
      }
      return result
    } catch (saveError) {
      setError(saveError.message)
      return null
    } finally {
      setIsSaving(false)
    }
  }

  async function deleteEntity(entity, id) {
    setIsSaving(true)
    setError('')
    try {
      await apiRequest(`/api/knowledge/${entity}/${id}/`, token, { method: 'DELETE' })
      setData((current) => ({ ...current, [entity]: current[entity].filter((item) => item.id !== id) }))
      return true
    } catch (deleteError) {
      setError(deleteError.message)
      return false
    } finally {
      setIsSaving(false)
    }
  }

  return { ...data, isLoading, isSaving, error, clearError: () => setError(''), saveEntity, deleteEntity }
}
