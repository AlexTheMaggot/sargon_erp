import { t } from '../../i18n/core'

export function Modal({ children, title, onClose }) {
  return (
    <div className="modal-overlay" role="presentation" onMouseDown={onClose}>
      <div className="modal-card" role="dialog" aria-modal="true" aria-labelledby="modal-title" onMouseDown={(event) => event.stopPropagation()}>
        <div className="modal-header">
          <h3 id="modal-title">{title}</h3>
          <button className="modal-close" type="button" aria-label={t('Закрыть окно')} onClick={onClose}>
            ×
          </button>
        </div>
        {children}
      </div>
    </div>
  )
}

export function DeleteConfirmModal({ entityName, itemName, onCancel, onConfirm }) {
  return (
    <Modal title={t`Удалить ${entityName}?`} onClose={onCancel}>
      <div className="confirm-modal-body">
        <p>{t('Это действие нельзя отменить.')}</p>
        <strong>{itemName}</strong>
      </div>
      <div className="form-actions">
        <button className="danger-button" type="button" onClick={onConfirm}>{t('Удалить')}</button>
        <button className="secondary-button" type="button" onClick={onCancel}>{t('Отмена')}</button>
      </div>
    </Modal>
  )
}
