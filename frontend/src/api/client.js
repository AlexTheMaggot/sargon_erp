export async function apiRequest(path, token, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: buildHeaders(token, options.headers),
  })

  const data = await parseResponseJson(response)
  if (!response.ok) {
    throw new Error(data.detail || 'Ошибка запроса')
  }

  return data
}

function buildHeaders(token, headers = {}) {
  return {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...headers,
  }
}

async function parseResponseJson(response) {
  const text = await response.text()
  if (!text) {
    return {}
  }

  try {
    return JSON.parse(text)
  } catch {
    return {}
  }
}

export async function fetchAccessData(token) {
  const [usersData, groupsData, modulesData, permissionsData] = await Promise.all([
    apiRequest('/api/access/users/', token),
    apiRequest('/api/access/groups/', token),
    apiRequest('/api/access/modules/', token),
    apiRequest('/api/access/permissions/', token),
  ])

  return {
    users: usersData.items,
    groups: groupsData.items,
    modules: modulesData.items,
    permissions: permissionsData.items,
  }
}

export async function fetchDirectoryData(token) {
  const [suppliersData, citiesData] = await Promise.all([
    apiRequest('/api/directories/suppliers/', token),
    apiRequest('/api/directories/cities/', token),
  ])

  return {
    suppliers: suppliersData.items,
    cities: citiesData.items,
  }
}

export async function fetchOperationsData(token) {
  const [receiptsResult, analysesResult, suppliersResult] = await Promise.allSettled([
    apiRequest('/api/raw-material/receipts/', token),
    apiRequest('/api/laboratory/analyses/', token),
    apiRequest('/api/directories/suppliers/', token),
  ])

  return {
    receipts: receiptsResult.status === 'fulfilled' ? receiptsResult.value.items : [],
    analyses: analysesResult.status === 'fulfilled' ? analysesResult.value.items : [],
    suppliers: suppliersResult.status === 'fulfilled' ? suppliersResult.value.items : [],
  }
}
