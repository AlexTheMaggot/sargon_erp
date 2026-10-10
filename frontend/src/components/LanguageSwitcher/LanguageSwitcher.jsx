import { languages, setLanguage, t } from '../../i18n/core'
import { useLanguage } from '../../i18n/useLanguage'
import './LanguageSwitcher.css'

export function LanguageSwitcher() {
  const language = useLanguage()
  return (
    <label className="language-switcher">
      <span>{t('Язык интерфейса')}</span>
      <select aria-label={t('Язык интерфейса')} value={language} onChange={(event) => setLanguage(event.target.value)}>
        {languages.map((item) => <option key={item.code} value={item.code} lang={item.code}>{item.label}</option>)}
      </select>
    </label>
  )
}
