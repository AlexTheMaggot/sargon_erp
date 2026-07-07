import { useCallback, useEffect, useState } from 'react'
import { apiRequest, fetchOperationsData } from '../api/client'

const MAX_RECONNECT_ATTEMPTS = 5
const MAX_RECONNECT_DELAY = 10000

function receiptPath(id = '') {
  return `/api/raw-material/receipts/${id ? `${id}/` : ''}`
}

function analysisPath(id) {
  return `/api/laboratory/analyses/${id}/`
}

function buildReceiptPayload(form) {
  const payload = {
    supplier_id: form.supplier_id,
  }

  if (form.can_set_quantity) {
    payload.input_quantity = form.input_quantity
    payload.input_unit = form.input_unit
  }

  return payload
}

function buildAnalysisPayload(form, statusPayload = {}) {
  return {
    density: form.density,
    flash_point_temperature: form.flash_point_temperature,
    current_temperature: form.current_temperature,
    water_percentage: form.water_percentage,
    ...statusPayload,
  }
}

export function useOperationsCrud(token) {
  const [receipts, setReceipts] = useState([])
  const [analyses, setAnalyses] = useState([])
  const [suppliers, setSuppliers] = useState([])
  const [error, setError] = useState('')

  function applyOperationsData(data) {
    setReceipts(data.receipts)
    setAnalyses(data.analyses)
    setSuppliers(data.suppliers)
  }

  const loadOperationsData = useCallback(async function loadOperationsData() {
    applyOperationsData(await fetchOperationsData(token))
  }, [token])

  useEffect(() => {
    let isCancelled = false

    fetchOperationsData(token)
      .then((data) => {
        if (!isCancelled) {
          applyOperationsData(data)
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

  useEffect(() => {
    if (!token) {
      return undefined
    }

    let socket = null
    let reconnectTimer = null
    let isClosed = false
    let hasConnected = false
    let reconnectAttempts = 0

    function scheduleReconnect() {
      reconnectAttempts += 1
      if (reconnectAttempts > MAX_RECONNECT_ATTEMPTS) {
        return
      }

      const reconnectDelay = Math.min(1000 * 2 ** reconnectAttempts, MAX_RECONNECT_DELAY)
      reconnectTimer = window.setTimeout(connect, reconnectDelay)
    }

    function connect() {
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
      const socketUrl = `${protocol}//${window.location.host}/ws/operations/?token=${encodeURIComponent(token)}`
      socket = new WebSocket(socketUrl)

      socket.onopen = () => {
        hasConnected = true
        reconnectAttempts = 0
      }

      socket.onmessage = async () => {
        try {
          await loadOperationsData()
        } catch (loadError) {
          setError(loadError.message)
        }
      }

      socket.onclose = (event) => {
        if (isClosed || event.code === 4401 || event.code === 4403 || !hasConnected) {
          return
        }

        scheduleReconnect()
      }
    }

    connect()

    return () => {
      isClosed = true
      if (reconnectTimer) {
        window.clearTimeout(reconnectTimer)
      }
      if (socket) {
        socket.close()
      }
    }
  }, [loadOperationsData, token])

  async function runOperation(operation, resetForm) {
    setError('')

    try {
      await operation()
      resetForm?.()
      await loadOperationsData()
      return true
    } catch (operationError) {
      setError(operationError.message)
      return false
    }
  }

  async function saveReceipt(event, form, resetForm) {
    event.preventDefault()
    const isEdit = Boolean(form.id)

    return runOperation(
      () => apiRequest(receiptPath(form.id), token, {
        method: isEdit ? 'PATCH' : 'POST',
        body: JSON.stringify(buildReceiptPayload(form)),
      }),
      resetForm,
    )
  }

  async function saveAnalysisStatus(form, resetForm, statusPayload = {}) {
    return runOperation(
      () => apiRequest(analysisPath(form.id), token, {
        method: 'PATCH',
        body: JSON.stringify(buildAnalysisPayload(form, statusPayload)),
      }),
      resetForm,
    )
  }

  async function deleteReceipt(id) {
    return runOperation(() => apiRequest(receiptPath(id), token, { method: 'DELETE' }))
  }

  async function completeReceipt(id) {
    return runOperation(() => apiRequest(receiptPath(id), token, {
      method: 'PATCH',
      body: JSON.stringify({ is_completed: true }),
    }))
  }

  return {
    analyses,
    completeReceipt,
    error,
    receipts,
    suppliers,
    deleteReceipt,
    saveAnalysisStatus,
    saveReceipt,
  }
}
