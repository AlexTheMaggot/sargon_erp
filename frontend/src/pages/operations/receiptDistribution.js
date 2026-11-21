const MAX_VOLUME = 99999999999999n

function scaledDecimal(value, precision) {
  const text = String(value ?? '').trim()
  if (!/^(?:\d+(?:\.\d*)?|\.\d+)$/.test(text) || text.length > 30) return null
  const [whole, fraction = ''] = text.split('.')
  if (fraction.slice(precision).replace(/0/g, '')) return null
  return BigInt(whole || '0') * 10n ** BigInt(precision) + BigInt(fraction.slice(0, precision).padEnd(precision, '0'))
}

export function volumeUnits(value) {
  const volume = scaledDecimal(value, 3)
  return volume !== null && volume <= MAX_VOLUME ? volume : null
}

export function batchVolumeUnits(batch) {
  const quantity = volumeUnits(batch.input_quantity)
  if (quantity === null || quantity <= 0n) return null
  if (batch.input_unit === 'liters') return quantity
  if (batch.input_unit !== 'kilograms') return null
  const density = scaledDecimal(batch.analysis_density, 4)
  if (density === null || density <= 0n) return null
  const numerator = quantity * 10000n
  const volume = (numerator * 2n + density) / (density * 2n)
  return volume > 0n && volume <= MAX_VOLUME ? volume : null
}

export function calculateReceiptDistribution(batches, distributions, tanks) {
  const tankMap = new Map(tanks.map((tank) => [String(tank.id), tank]))
  const tankTotals = new Map()
  const batchStates = {}
  let totalVolume = 0n
  for (const batch of batches.filter((item) => item.is_analysis_approved && !item.is_distributed)) {
    const volume = batchVolumeUnits(batch)
    const rows = distributions[batch.id] || []
    const selectedTanks = new Set()
    let distributed = 0n
    let issue = ''
    for (const row of rows) {
      const amount = volumeUnits(row.volume_liters)
      const tankId = String(row.tank_id)
      if (amount !== null) distributed += amount
      if (!tankMap.has(tankId) || amount === null || amount <= 0n) issue ||= 'row'
      if (selectedTanks.has(tankId)) issue = 'duplicate'
      selectedTanks.add(tankId)
      if (amount !== null) tankTotals.set(tankId, (tankTotals.get(tankId) || 0n) + amount)
    }
    if (volume !== null) totalVolume += volume
    batchStates[batch.id] = {
      volume, distributed, remaining: volume === null ? null : volume - distributed, issue,
      isComplete: volume !== null && rows.length > 0 && !issue && volume === distributed,
    }
  }
  const overflowingTanks = tanks.filter((tank) => {
    const free = volumeUnits(tank.free_volume_liters)
    const requested = tankTotals.get(String(tank.id)) || 0n
    return requested > 0n && (free === null || requested > free)
  })
  const hasFinalDecisions = batches.length > 0 && batches.every((batch) => batch.is_analysis_approved || batch.is_analysis_rejected)
  return {
    batchStates, overflowingTanks, hasFinalDecisions,
    isComplete: hasFinalDecisions && totalVolume <= MAX_VOLUME && !overflowingTanks.length
      && Object.values(batchStates).every((batch) => batch.isComplete),
  }
}
