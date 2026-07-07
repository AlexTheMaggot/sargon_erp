export function ListControls({
  currentPage,
  filteredCount,
  onPageChange,
  onSearchChange,
  pageCount,
  searchPlaceholder = 'Слепой поиск',
  searchQuery,
  totalCount,
}) {
  return (
    <div className="list-controls">
      <label className="list-search">
        <span>{searchPlaceholder}</span>
        <input
          placeholder="Введите текст для поиска"
          type="search"
          value={searchQuery}
          onChange={(event) => onSearchChange(event.target.value)}
        />
      </label>

      <div className="list-pagination">
        <span>{filteredCount} из {totalCount}</span>
        <div className="pagination-actions">
          <button
            className="secondary-button"
            disabled={currentPage <= 1}
            type="button"
            onClick={() => onPageChange(currentPage - 1)}
          >
            Назад
          </button>
          <strong>{currentPage} / {pageCount}</strong>
          <button
            className="secondary-button"
            disabled={currentPage >= pageCount}
            type="button"
            onClick={() => onPageChange(currentPage + 1)}
          >
            Вперёд
          </button>
        </div>
      </div>
    </div>
  )
}
