import { useCallback, useEffect, useState } from 'react'
import { apiRequest, fetchOperationsData } from '../api/client'

const MAX_RECONNECT_ATTEMPTS = 5
const MAX_RECONNECT_DELAY = 10000
const OPERATIONS_REFRESH_INTERVAL = 15000

function receiptPath(id = '') {
  return `/api/raw-material/receipts/${id ? `${id}/` : ''}`
}

function receiptBatchesPath(receiptId) {
  return `/api/raw-material/receipts/${receiptId}/batches/`
}

function batchPath(id) {
  return `/api/raw-material/batches/${id}/`
}

function analysisPath(id) {
  return `/api/laboratory/analyses/${id}/`
}

function buildReceiptPayload(form) {
  return {
    supplier_id: form.supplier_id,
  }
}

function buildBatchPayload(batch) {
  return {
    input_quantity: batch.input_quantity,
    input_unit: batch.input_unit,
  }
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

export function useOperationsCrud(token, { onReceiptCreated } = {}) {
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

    const refreshTimer = window.setInterval(() => {
      loadOperationsData().catch((loadError) => {
        setError(loadError.message)
      })
    }, OPERATIONS_REFRESH_INTERVAL)

    return () => {
      window.clearInterval(refreshTimer)
    }
  }, [loadOperationsData, token])

  useEffect(() => {
    if (!token) {
      return undefined
    }

    let socket = null
    let reconnectTimer = null
    let isClosed = false
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
        reconnectAttempts = 0
      }

      socket.onmessage = async (message) => {
        try {
          const payload = JSON.parse(message.data)
          if (payload.event === 'receipt_created' || payload.event === 'batch_created') {
            onReceiptCreated?.(payload)
          }
          await loadOperationsData()
        } catch (loadError) {
          setError(loadError.message)
        }
      }

      socket.onclose = (event) => {
        if (isClosed || event.code === 4401 || event.code === 4403) {
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
  }, [loadOperationsData, onReceiptCreated, token])

  async function runOperation(operation, resetForm) {
    setError('')

    try {
      const result = await operation()
      resetForm?.()
      await loadOperationsData()
      return result || true
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

  async function addReceiptBatch(receiptId) {
    return runOperation(() => apiRequest(receiptBatchesPath(receiptId), token, { method: 'POST' }))
  }

  async function saveReceiptBatch(batch) {
    return runOperation(() => apiRequest(batchPath(batch.id), token, {
      method: 'PATCH',
      body: JSON.stringify(buildBatchPayload(batch)),
    }))
  }

  async function deleteReceiptBatch(id) {
    return runOperation(() => apiRequest(batchPath(id), token, { method: 'DELETE' }))
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
    addReceiptBatch,
    analyses,
    completeReceipt,
    deleteReceiptBatch,
    error,
    receipts,
    suppliers,
    deleteReceipt,
    saveAnalysisStatus,
    saveReceiptBatch,
    saveReceipt,
  }
}
