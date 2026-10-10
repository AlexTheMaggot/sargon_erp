import { t } from '../../i18n/core'
export function ListControls({
  currentPage,
  filteredCount,
  onPageChange,
  onSearchChange,
  pageCount,
  searchPlaceholder = t('Слепой поиск'),
  searchQuery,
  totalCount,
}) {
  return (
    <div className="list-controls">
      <label className="list-search">
        <span>{searchPlaceholder}</span>
        <input
          placeholder={t('Введите текст для поиска')}
          type="search"
          value={searchQuery}
          onChange={(event) => onSearchChange(event.target.value)}
        />
      </label>

      <div className="list-pagination">
        <span>{t`${filteredCount} из ${totalCount}`}</span>
        <div className="pagination-actions">
          <button
            className="secondary-button"
            disabled={currentPage <= 1}
            type="button"
            onClick={() => onPageChange(currentPage - 1)}
          >{t('Назад')}</button>
          <strong>{currentPage} / {pageCount}</strong>
          <button
            className="secondary-button"
            disabled={currentPage >= pageCount}
            type="button"
            onClick={() => onPageChange(currentPage + 1)}
          >{t('Вперёд')}</button>
        </div>
      </div>
    </div>
  )
}
