import { t } from '../../i18n/core'
import { CANISTER_PRODUCTION_LINES } from '../../constants/canisterProduction'
import './CanisterProduction.css'

function PackagingConnector({ ports, split = false }) {
  return (
    <div className={`packaging-connector packaging-connector--${ports}${split ? ' packaging-connector--split' : ''}`} aria-hidden="true">
      {Array.from({ length: ports }, (_, index) => <i key={index} />)}
      <b />
    </div>
  )
}

export function CanisterProduction({ renderNode }) {
  return (
    <section id="canister-production-panel" className="packaging-production" role="tabpanel" aria-labelledby="canister-production-tab">
      <header className="oil-production-header packaging-header">
        <div>
          <p className="auth-eyebrow">{t('Производство упаковки')}</p>
          <h2>{t('Производство канистр')}</h2>
          <p>{t('Две производственные линии с раздельными контурами вторсырья.')}</p>
        </div>
        <div className="packaging-mode-badge">{t('Сырьё и выпуск · склад продукции не подключён')}</div>
      </header>

      <div className="oil-production-legend packaging-legend">
        <span><i className="legend-line legend-line--material" />{t('Гранулы и красители')}</span>
        <span><i className="legend-line packaging-legend--finished" />{t('Годная продукция')}</span>
        <span><i className="legend-line packaging-legend--deviation" />{t('Отклонение — отдельная позиция')}</span>
        <span><i className="legend-line packaging-legend--defect" />{t('Брак на измельчение')}</span>
        <span><i className="legend-line packaging-legend--return" />{t('Возврат вторсырья')}</span>
        <small>{t('Сырьё — кг · продукция — шт.')}</small>
      </div>

      <div className="process-scroll-hint">
        <span>{t('Нажмите на этап, чтобы посмотреть показатели')}</span>
        <span>{t('На небольшом экране прокручивайте схему по горизонтали')}</span>
      </div>

      {CANISTER_PRODUCTION_LINES.map((line, index) => (
        <section key={line.id} className={`packaging-line packaging-line--${line.id}`} aria-labelledby={`packaging-${line.id}-title`}>
          <header className="packaging-line-header">
            <span className="packaging-line-number" aria-hidden="true">0{index + 1}</span>
            <div>
              <h3 id={`packaging-${line.id}-title`}>{t(line.title)}</h3>
              <p>{t(line.description)}</p>
            </div>
            <span className="packaging-line-unit">{t('кг → шт. → кг')}</span>
          </header>

          <div className="packaging-map-scroll" role="region" aria-label={t(line.title)} tabIndex={0}>
            <div className={`packaging-line-map packaging-line-map--${line.outputIds.length}`}>
              <div className="packaging-inputs">
                {renderNode(line.granulesId)}
                {renderNode(line.dyeId)}
                {renderNode(line.regrindId)}
              </div>

              <PackagingConnector ports={3} />
              <div className="packaging-forming">{renderNode(line.productionId)}</div>
              <PackagingConnector ports={line.outputIds.length} split />

              <div className="packaging-outputs">
                {line.outputIds.map((nodeId) => <div key={nodeId}>{renderNode(nodeId)}</div>)}
              </div>

              <div className="packaging-reject-route" aria-hidden="true"><i /></div>
              <div className="packaging-grinding">{renderNode(line.grinderId)}</div>

              <div className="packaging-return-route" aria-hidden="true">
                <i className="packaging-return-target"><b /></i>
                <i className="packaging-return-middle" />
                <i className="packaging-return-source" />
              </div>
              <p className="packaging-return-label">{t(line.returnLabel)}</p>
            </div>
          </div>
        </section>
      ))}
    </section>
  )
}
