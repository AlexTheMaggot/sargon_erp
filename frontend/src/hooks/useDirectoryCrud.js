import { useEffect, useState } from 'react'
import { apiRequest, fetchDirectoryData } from '../api/client'

export function useDirectoryCrud(token) {
  const [suppliers, setSuppliers] = useState([])
  const [cities, setCities] = useState([])
  const [error, setError] = useState('')

  function applyDirectoryData(data) {
    setSuppliers(data.suppliers)
    setCities(data.cities)
  }

  async function loadDirectoryData() {
    applyDirectoryData(await fetchDirectoryData(token))
  }

  useEffect(() => {
    let isCancelled = false

    fetchDirectoryData(token)
      .then((data) => {
        if (!isCancelled) {
          applyDirectoryData(data)
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

  async function saveSupplier(event, form, resetForm) {
    event.preventDefault()
    setError('')

    const isEdit = Boolean(form.id)
    const payload = {
      company_name: form.company_name,
      city_id: form.city_id,
      address: form.address,
      phone: form.phone,
    }

    try {
      await apiRequest(`/api/directories/suppliers/${isEdit ? `${form.id}/` : ''}`, token, {
        method: isEdit ? 'PATCH' : 'POST',
        body: JSON.stringify(payload),
      })
      resetForm()
      await loadDirectoryData()
      return true
    } catch (saveError) {
      setError(saveError.message)
      return false
    }
  }

  async function saveCity(event, form, resetForm) {
    event.preventDefault()
    setError('')

    const isEdit = Boolean(form.id)
    const payload = { name: form.name }

    try {
      await apiRequest(`/api/directories/cities/${isEdit ? `${form.id}/` : ''}`, token, {
        method: isEdit ? 'PATCH' : 'POST',
        body: JSON.stringify(payload),
      })
      resetForm()
      await loadDirectoryData()
      return true
    } catch (saveError) {
      setError(saveError.message)
      return false
    }
  }

  async function deleteCity(id) {
    setError('')
    try {
      await apiRequest(`/api/directories/cities/${id}/`, token, { method: 'DELETE' })
      await loadDirectoryData()
      return true
    } catch (deleteError) {
      setError(deleteError.message)
      return false
    }
  }

  async function deleteSupplier(id) {
    setError('')
    try {
      await apiRequest(`/api/directories/suppliers/${id}/`, token, { method: 'DELETE' })
      await loadDirectoryData()
      return true
    } catch (deleteError) {
      setError(deleteError.message)
      return false
    }
  }

  return {
    suppliers,
    cities,
    error,
    saveSupplier,
    saveCity,
    deleteCity,
    deleteSupplier,
  }
}
