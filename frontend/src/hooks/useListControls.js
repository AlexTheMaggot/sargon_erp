import { useMemo, useState } from 'react'

const DEFAULT_PAGE_SIZE = 10

function normalizeSearchText(value) {
  return String(value ?? '').toLowerCase().trim()
}

export function useListControls(items, getSearchText, pageSize = DEFAULT_PAGE_SIZE) {
  const [searchQuery, setSearchQuery] = useState('')
  const [currentPage, setCurrentPage] = useState(1)
  const normalizedQuery = normalizeSearchText(searchQuery)

  const filteredItems = useMemo(() => {
    if (!normalizedQuery) {
      return items
    }

    return items.filter((item) => normalizeSearchText(getSearchText(item)).includes(normalizedQuery))
  }, [getSearchText, items, normalizedQuery])

  const pageCount = Math.max(1, Math.ceil(filteredItems.length / pageSize))
  const safeCurrentPage = Math.min(currentPage, pageCount)

  const paginatedItems = useMemo(() => {
    const startIndex = (safeCurrentPage - 1) * pageSize
    return filteredItems.slice(startIndex, startIndex + pageSize)
  }, [filteredItems, pageSize, safeCurrentPage])

  function handleSearchChange(nextQuery) {
    setSearchQuery(nextQuery)
    setCurrentPage(1)
  }

  function handlePageChange(nextPage) {
    setCurrentPage(Math.min(Math.max(nextPage, 1), pageCount))
  }

  return {
    currentPage: safeCurrentPage,
    filteredCount: filteredItems.length,
    pageCount,
    paginatedItems,
    searchQuery,
    setCurrentPage: handlePageChange,
    setSearchQuery: handleSearchChange,
    totalCount: items.length,
  }
}
