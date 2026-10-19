import { createPortal } from 'react-dom'
import { t } from '../../i18n/core'
import { Modal } from '../Modal/Modal'

export default function InstallAppHelp({ error, onClose }) {
  return createPortal(
    <Modal title={t('Установка SHENOLL')} onClose={onClose}>
      <div className="pwa-install-help">
        {error && <p className="form-error" role="alert">{t(error)}</p>}
        {!window.isSecureContext && <p className="form-error" role="alert">{t('Для установки на устройствах нужен HTTPS с доверенным сертификатом. HTTP подходит только для localhost на самом устройстве.')}</p>}
        <p>{t('После установки запускайте SHENOLL через значок приложения: система откроется в отдельном окне без адресной строки браузера.')}</p>
        <h4>{t('Android и компьютер')}</h4>
        <p>{t('В Chrome или Edge откройте меню браузера и выберите установку приложения. Название пункта зависит от браузера. При наличии значка установки в адресной строке можно нажать на него.')}</p>
        <p>{t('В Safari на Mac выберите «Файл» → «Добавить в Dock», если этот пункт доступен.')}</p>
        <h4>{t('iPhone и iPad')}</h4>
        <p>{t('В Safari нажмите «Поделиться», затем «На экран Домой». Если предлагается настройка «Открывать как веб-приложение», оставьте её включённой.')}</p>
        <p>{t('SHENOLL работает онлайн. Установка не сохраняет документы для работы без связи с сервером.')}</p>
        <div className="form-actions"><button type="button" onClick={onClose}>{t('Понятно')}</button></div>
      </div>
    </Modal>, document.body,
  )
}
