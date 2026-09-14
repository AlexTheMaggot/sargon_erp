import { useCallback, useEffect, useState } from 'react'
import { apiRequest } from '../api/client'

const containerPaths = {
  receiving_tank: '/api/processing/receiving-tanks/',
  preheating_boiler: '/api/processing/preheating-boilers/',
  separator: '/api/processing/separators/',
  chemical_mixer: '/api/processing/chemical-mixers/',
  processing_workshop: '/api/processing/workshops/',
  raw_diesel_tank: '/api/processing/raw-diesel-tanks/',
  raw_spindle_tank: '/api/processing/raw-spindle-tanks/',
}

const allContainerKinds = Object.keys(containerPaths)

export function useProcessingCrud(token, { containerKinds = allContainerKinds, loadJournal = false } = {}) {
  const [receivingTanks, setReceivingTanks] = useState([])
  const [boilers, setBoilers] = useState([])
  const [separators, setSeparators] = useState([])
  const [chemicalMixers, setChemicalMixers] = useState([])
  const [processingWorkshops, setProcessingWorkshops] = useState([])
  const [rawDieselTanks, setRawDieselTanks] = useState([])
  const [rawSpindleTanks, setRawSpindleTanks] = useState([])
  const [journal, setJournal] = useState({ items: [], total: 0, page: 1, page_count: 1 })
  const [error, setError] = useState('')
  const containerKindsKey = [...containerKinds].sort().join(',')

  const loadContainers = useCallback(async () => {
    const requestedKinds = containerKindsKey ? containerKindsKey.split(',') : []
    const responses = await Promise.all(requestedKinds.map(async (kind) => [
      kind,
      await apiRequest(containerPaths[kind], token),
    ]))
    const dataByKind = Object.fromEntries(responses)

    if (dataByKind.receiving_tank) setReceivingTanks(dataByKind.receiving_tank.items)
    if (dataByKind.preheating_boiler) setBoilers(dataByKind.preheating_boiler.items)
    if (dataByKind.separator) setSeparators(dataByKind.separator.items)
    if (dataByKind.chemical_mixer) setChemicalMixers(dataByKind.chemical_mixer.items)
    if (dataByKind.processing_workshop) setProcessingWorkshops(dataByKind.processing_workshop.items)
    if (dataByKind.raw_diesel_tank) setRawDieselTanks(dataByKind.raw_diesel_tank.items)
    if (dataByKind.raw_spindle_tank) setRawSpindleTanks(dataByKind.raw_spindle_tank.items)
  }, [containerKindsKey, token])

  const fetchJournal = useCallback(async (filters = {}, page = 1) => {
    const searchParams = new URLSearchParams({ page: String(page), page_size: '10' })
    Object.entries(filters).forEach(([key, value]) => {
      if (value !== '' && value !== null && value !== undefined) {
        searchParams.set(key, value)
      }
    })
    const data = await apiRequest(`/api/processing/journal/?${searchParams}`, token)
    setJournal(data)
    return data
  }, [token])

  useEffect(() => {
    let isCancelled = false

    async function loadInitialContainers() {
      try {
        await loadContainers()
      } catch (loadError) {
        if (!isCancelled) {
          setError(loadError.message)
        }
      }
    }

    loadInitialContainers()
    return () => {
      isCancelled = true
    }
  }, [loadContainers])

  useEffect(() => {
    let isCancelled = false

    async function loadInitialJournal() {
      if (!loadJournal) {
        return
      }
      try {
        await fetchJournal()
      } catch (loadError) {
        if (!isCancelled) {
          setError(loadError.message)
        }
      }
    }

    loadInitialJournal()
    return () => {
      isCancelled = true
    }
  }, [fetchJournal, loadJournal])

  async function runOperation(operation, reloadJournal = false) {
    setError('')
    try {
      const result = await operation()
      await loadContainers()
      if (reloadJournal || loadJournal) {
        await fetchJournal()
      }
      return result || true
    } catch (operationError) {
      setError(operationError.message)
      return false
    }
  }

  function saveContainer(event, form) {
    event.preventDefault()
    const isEdit = Boolean(form.id)
    const path = isEdit ? `/api/processing/containers/${form.id}/` : containerPaths[form.kind]
    return runOperation(() => apiRequest(path, token, {
      method: isEdit ? 'PATCH' : 'POST',
      body: JSON.stringify({
        number: form.number,
        capacity_liters: form.capacity_liters,
        is_active: form.is_active,
      }),
    }))
  }

  function deleteContainer(id) {
    return runOperation(() => apiRequest(`/api/processing/containers/${id}/`, token, { method: 'DELETE' }))
  }

  function createTankToBoilerMovement(form) {
    return runOperation(() => apiRequest('/api/processing/movements/tank-to-boiler/', token, {
      method: 'POST',
      body: JSON.stringify(form),
    }))
  }

  function createBoilerToSeparatorMovement(form) {
    return runOperation(() => apiRequest('/api/processing/movements/boiler-to-separator/', token, {
      method: 'POST',
      body: JSON.stringify(form),
    }))
  }

  function createSeparatorOutputMovement(form) {
    return runOperation(() => apiRequest('/api/processing/movements/separator-output/', token, {
      method: 'POST',
      body: JSON.stringify(form),
    }))
  }

  function createChemicalMixerLoading(form) {
    return runOperation(() => apiRequest('/api/processing/movements/separator-to-chemical-mixer/', token, {
      method: 'POST',
      body: JSON.stringify(form),
    }))
  }

  function createWorkshopLoading(form) {
    return runOperation(() => apiRequest('/api/processing/movements/chemical-mixer-to-workshop/', token, {
      method: 'POST',
      body: JSON.stringify(form),
    }))
  }

  function createRawDieselTankLoading(form) {
    return runOperation(() => apiRequest('/api/processing/movements/workshop-to-raw-diesel-tank/', token, {
      method: 'POST',
      body: JSON.stringify(form),
    }))
  }

  function createRawSpindleTankLoading(form) {
    return runOperation(() => apiRequest('/api/processing/movements/workshop-to-raw-spindle-tank/', token, {
      method: 'POST',
      body: JSON.stringify(form),
    }))
  }

  function compensateMovement(movementId, reason) {
    return runOperation(() => apiRequest(`/api/processing/movements/${movementId}/compensate/`, token, {
      method: 'POST',
      body: JSON.stringify({ reason }),
    }), true)
  }

  return {
    boilers,
    chemicalMixers,
    compensateMovement,
    createBoilerToSeparatorMovement,
    createChemicalMixerLoading,
    createRawDieselTankLoading,
    createRawSpindleTankLoading,
    createSeparatorOutputMovement,
    createTankToBoilerMovement,
    createWorkshopLoading,
    deleteContainer,
    error,
    fetchJournal,
    journal,
    processingWorkshops,
    rawDieselTanks,
    rawSpindleTanks,
    receivingTanks,
    separators,
    saveContainer,
  }
}
