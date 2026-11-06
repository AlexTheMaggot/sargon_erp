import { languages, setLanguage, t } from '../../i18n/core'
import { useLanguage } from '../../i18n/useLanguage'
import russianFlag from '../../assets/flags/ru.svg?no-inline'
import uzbekFlag from '../../assets/flags/uz.svg?no-inline'
import './LanguageSwitcher.css'

const languageFlags = { ru: russianFlag, uz: uzbekFlag }

export function LanguageSwitcher({ variant = 'select' }) {
  const language = useLanguage()
  if (variant === 'flags') {
    return (
      <div className="language-switcher language-switcher--flags" role="group" aria-label={t('Язык интерфейса')}>
        {languages.map((item) => (
          <button
            key={item.code}
            className="language-flag-button"
            type="button"
            lang={item.code}
            aria-label={t(item.label)}
            aria-pressed={language === item.code}
            title={t(item.label)}
            onClick={() => setLanguage(item.code)}
          >
            <img src={languageFlags[item.code]} alt="" aria-hidden="true" width="30" height="20" />
          </button>
        ))}
      </div>
    )
  }
  return (
    <label className="language-switcher">
      <span>{t('Язык интерфейса')}</span>
      <select aria-label={t('Язык интерфейса')} value={language} onChange={(event) => setLanguage(event.target.value)}>
        {languages.map((item) => <option key={item.code} value={item.code} lang={item.code}>{item.label}</option>)}
      </select>
    </label>
  )
}
