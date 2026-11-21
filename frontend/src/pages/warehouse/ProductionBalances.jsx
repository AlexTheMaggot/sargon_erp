import { formatNumber, t } from '../../i18n/core'

export function ProductionBalances({ balances = [] }) {
  return <section className="access-grid"><article className="access-card">
    <h3>{t('Материалы на участке')}</h3>
    <p>{t('Загружено со склада, использовано в зарегистрированном выпуске и доступно для следующего выпуска.')}</p>
    <div className="entity-list">
      {balances.map((balance) => <div className="entity-row" key={balance.item.id}>
        <div><strong>{balance.item.name}</strong>
          <span>{t('Загружено: ')}{formatNumber(balance.loaded_quantity)} {t('кг')}</span>
          <span>{t('Использовано: ')}{formatNumber(balance.used_quantity)} {t('кг')}</span>
        </div>
        <div className="warehouse-balance-values"><strong>{t('Доступно: ')}{formatNumber(balance.available_quantity)} {t('кг')}</strong>
          <span>{t('Стоимость остатка: ')}{formatNumber(balance.available_cost, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} {t('сум')}</span>
        </div>
      </div>)}
      {!balances.length && <p className="empty-state">{t('На участок ещё не передавали материалы.')}</p>}
    </div>
  </article></section>
}
