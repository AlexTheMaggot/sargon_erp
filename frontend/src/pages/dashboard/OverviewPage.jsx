import { getLocale, localizeStaticData, t } from '../../i18n/core'
import { useLanguage } from '../../i18n/useLanguage'
import { createContext, useContext, useEffect, useMemo, useState } from 'react'
import { apiRequest } from '../../api/client'
import { DashboardShell } from '../../components/Layout/DashboardShell'
import { Modal } from '../../components/Modal/Modal'
import { CANISTER_FLOW_NODES, CANISTER_PRODUCTION_LINES } from '../../constants/canisterProduction'
import { CanisterProduction } from './CanisterProduction'

const OVERVIEW_REFRESH_INTERVAL = 15000

const FLOW_NODES = {
  ...CANISTER_FLOW_NODES,
  reception: {
    name: 'Прием отработки',
    shortName: 'ПР',
    stage: 'Входящий поток',
    status: 'Прием идет',
    statusTone: 'running',
    throughput: '18 000 л/ч',
    currentFlow: '12 450 л',
    description: 'Регистрация и первичный учет принятой отработки.',
    metrics: [
      ['Принято за смену', '12 450 л'],
      ['Машин в очереди', '2'],
      ['Средний прием', '4 150 л'],
    ],
  },
  storageTank: {
    name: 'Приемный бак',
    shortName: 'Б1',
    stage: 'Накопление',
    status: 'Заполняется',
    statusTone: 'running',
    throughput: '16 000 л/ч',
    currentFlow: '36 200 л',
    description: 'Буферное хранение принятой отработки перед первичным прогревом.',
    metrics: [
      ['Текущий объем', '36 200 л'],
      ['Вместимость', '50 000 л'],
      ['Заполнение', '72%'],
    ],
  },
  preheater: {
    name: 'Котел первичного прогрева',
    shortName: 'КП',
    stage: 'Термическая подготовка',
    status: 'В работе',
    statusTone: 'running',
    throughput: '16 000 л/ч',
    currentFlow: '11 800 л',
    description: 'Нагрев сырья перед разделением воды и твердых примесей.',
    metrics: [
      ['В обработке', '11 800 л'],
      ['Температура', '92 °C'],
      ['Загрузка', '74%'],
    ],
  },
  separator: {
    name: 'Сепаратор',
    shortName: 'СЕ',
    stage: 'Разделение',
    status: 'В работе',
    statusTone: 'running',
    throughput: '15 000 л/ч',
    currentFlow: '11 640 л',
    description: 'Отделение воды и механических примесей от подготовленной отработки.',
    metrics: [
      ['Очищено за смену', '11 640 л'],
      ['Выход продукта', '93,5%'],
      ['Текущая загрузка', '78%'],
    ],
  },
  water: {
    name: 'Техническая вода',
    shortName: 'В',
    stage: 'Побочный продукт',
    status: 'Отводится',
    statusTone: 'water',
    throughput: '1 800 л/ч',
    currentFlow: '760 л',
    description: 'Отделенная вода направляется в отдельный контур утилизации.',
    metrics: [
      ['За смену', '760 л'],
      ['Доля потока', '6,1%'],
      ['Состояние линии', 'Норма'],
    ],
  },
  waste: {
    name: 'Механический мусор',
    shortName: 'М',
    stage: 'Отходы',
    status: 'Собирается',
    statusTone: 'waste',
    throughput: '500 л/ч',
    currentFlow: '50 л',
    description: 'Твердые примеси собираются для последующей утилизации.',
    metrics: [
      ['Эквивалент объема', '50 л'],
      ['Доля потока', '0,4%'],
      ['Заполнение сборника', '31%'],
    ],
  },
  chemicalMixer1: {
    name: 'Химический миксер №1',
    shortName: 'Х1',
    stage: 'Химическая подготовка',
    status: 'В работе',
    statusTone: 'running',
    throughput: '8 000 л/ч',
    currentFlow: '5 900 л',
    description: 'Смешивание очищенной отработки с технологическими реагентами.',
    metrics: [
      ['Текущая партия', '5 900 л'],
      ['Время цикла', '42 мин'],
      ['Готовность', '68%'],
    ],
  },
  chemicalMixer2: {
    name: 'Химический миксер №2',
    shortName: 'Х2',
    stage: 'Химическая подготовка',
    status: 'Готов',
    statusTone: 'ready',
    throughput: '8 000 л/ч',
    currentFlow: '0 л',
    description: 'Резервная линия смешивания с возможностью подачи в любой цех.',
    metrics: [
      ['Текущая партия', '0 л'],
      ['Последняя партия', '5 740 л'],
      ['Готовность', '100%'],
    ],
  },
  workshop1: {
    name: 'Цех переработки №1',
    shortName: 'Ц1',
    stage: 'Реакторная обработка',
    status: 'В работе',
    statusTone: 'running',
    throughput: '9 000 л/ч',
    currentFlow: '5 900 л',
    description: 'Основная переработка подготовленного продукта с гибкой маршрутизацией выхода.',
    metrics: [
      ['В обработке', '5 900 л'],
      ['Время до выпуска', '1 ч 18 мин'],
      ['Загрузка', '66%'],
    ],
  },
  workshop2: {
    name: 'Цех переработки №2',
    shortName: 'Ц2',
    stage: 'Реакторная обработка',
    status: 'Ожидает',
    statusTone: 'ready',
    throughput: '9 000 л/ч',
    currentFlow: '0 л',
    description: 'Параллельная линия переработки, принимающая сырье из любого химического миксера.',
    metrics: [
      ['В обработке', '0 л'],
      ['Последняя партия', '5 620 л'],
      ['Готовность', '100%'],
    ],
  },
  rawDieselTank: {
    name: 'Бак сырой солярки',
    shortName: 'СД',
    stage: 'Промежуточное хранение',
    status: 'Накапливается',
    statusTone: 'running',
    throughput: '10 000 л/ч',
    currentFlow: '21 600 л',
    description: 'Накопление сырой солярки перед поочередной сорбентной очисткой.',
    metrics: [
      ['Текущий объем', '21 600 л'],
      ['Вместимость', '35 000 л'],
      ['Заполнение', '62%'],
    ],
  },
  rawSpindleTank: {
    name: 'Бак сырой веретенки',
    shortName: 'СВ',
    stage: 'Промежуточное хранение',
    status: 'Подает в линию',
    statusTone: 'running',
    throughput: '10 000 л/ч',
    currentFlow: '14 900 л',
    description: 'Накопление сырой веретенки и подача в общую линию очистки.',
    metrics: [
      ['Текущий объем', '14 900 л'],
      ['Вместимость', '30 000 л'],
      ['Заполнение', '50%'],
    ],
  },
  sorbentSystem: {
    name: 'Сорбент-система',
    shortName: 'СС',
    stage: 'Тонкая очистка',
    status: 'Веретенка в работе',
    statusTone: 'running',
    throughput: '9 500 л/ч',
    currentFlow: '7 200 л',
    description: 'Общая линия сорбентной очистки. Солярка и веретенка обрабатываются только по очереди.',
    metrics: [
      ['Текущая партия', 'Веретенка'],
      ['В обработке', '7 200 л'],
      ['Чистота на выходе', '98,7%'],
    ],
  },
  sorbentTank: {
    name: 'Бак сорбента',
    shortName: 'БС',
    stage: 'Замкнутый контур',
    status: 'Циркуляция',
    statusTone: 'sorbent',
    throughput: '2 400 л/ч',
    currentFlow: '1 850 л',
    description: 'Сорбент циркулирует между накопительным баком и системой очистки.',
    metrics: [
      ['В контуре', '1 850 л'],
      ['Ресурс сорбента', '76%'],
      ['Циклов с замены', '14'],
    ],
  },
  finishingMixer: {
    name: 'Финишный миксер',
    shortName: 'ФМ',
    stage: 'Выравнивание состава',
    status: 'В работе',
    statusTone: 'running',
    throughput: '9 500 л/ч',
    currentFlow: '7 050 л',
    description: 'Финальное смешивание очищенного продукта перед фильтрацией.',
    metrics: [
      ['В обработке', '7 050 л'],
      ['Время цикла', '28 мин'],
      ['Однородность', '99,1%'],
    ],
  },
  filter: {
    name: 'Финишный фильтр',
    shortName: 'Ф',
    stage: 'Контрольная фильтрация',
    status: 'В работе',
    statusTone: 'running',
    throughput: '9 000 л/ч',
    currentFlow: '6 980 л',
    description: 'Контрольная фильтрация перед распределением по бакам готовой продукции.',
    metrics: [
      ['Отфильтровано', '6 980 л'],
      ['Перепад давления', '0,7 бар'],
      ['Ресурс фильтра', '82%'],
    ],
  },
  finishedSpindleTank: {
    name: 'Бак готовой веретенки',
    shortName: 'ГВ',
    stage: 'Готовая продукция',
    status: 'Заполняется',
    statusTone: 'finished',
    throughput: '8 000 л/ч',
    currentFlow: '18 400 л',
    description: 'Хранение готовой веретенки после полного цикла очистки.',
    metrics: [
      ['Текущий объем', '18 400 л'],
      ['Вместимость', '30 000 л'],
      ['Готово к отгрузке', '12 000 л'],
    ],
  },
  finishedDieselTank: {
    name: 'Бак готовой солярки',
    shortName: 'ГС',
    stage: 'Готовая продукция',
    status: 'Ожидает продукт',
    statusTone: 'finished',
    throughput: '8 000 л/ч',
    currentFlow: '24 700 л',
    description: 'Хранение готовой солярки после полного цикла очистки.',
    metrics: [
      ['Текущий объем', '24 700 л'],
      ['Вместимость', '35 000 л'],
      ['Готово к отгрузке', '20 500 л'],
    ],
  },
  polypropyleneFeed: {
    name: 'Узел подачи полипропилена',
    shortName: 'ПП',
    stage: 'Загуститель',
    status: 'Готов к подаче',
    statusTone: 'material',
    throughput: '450 кг/ч',
    currentFlow: '1 240 кг',
    description: 'Хранение и дозированная подача полипропиленового загустителя в реактор концентрата.',
    metrics: [
      ['Остаток', '1 240 кг'],
      ['Расход за смену', '310 кг'],
      ['Запас', '4 смены'],
    ],
  },
  concentrateReactor: {
    name: 'Реактор концентрата',
    shortName: 'РК',
    stage: 'Приготовление концентрата',
    status: 'В работе',
    statusTone: 'running',
    throughput: '4 500 л/ч',
    currentFlow: '3 200 л',
    description: 'Смешивание готовой веретенки с полипропиленовым загустителем для получения концентрата.',
    metrics: [
      ['Текущая партия', '3 200 л'],
      ['Температура', '138 °C'],
      ['Готовность', '64%'],
    ],
  },
  additiveStation: {
    name: 'Станция дозирования присадок',
    shortName: 'ПР',
    stage: 'Пакет присадок',
    status: 'Готова',
    statusTone: 'material',
    throughput: '320 кг/ч',
    currentFlow: '920 кг',
    description: 'Раздельное хранение и точное дозирование функциональных присадок в блендинговые смесители.',
    metrics: [
      ['Суммарный остаток', '920 кг'],
      ['Активных рецептур', '4'],
      ['Точность дозирования', '99,6%'],
    ],
  },
  blender1: {
    name: 'Блендинговый смеситель №1',
    shortName: 'Б1',
    stage: 'Смешивание масел',
    status: 'Трансмиссионное',
    statusTone: 'running',
    throughput: '5 000 л/ч',
    currentFlow: '4 200 л',
    description: 'Смешивание основы, концентрата и присадок по рецептуре трансмиссионного масла.',
    metrics: [
      ['Текущая партия', '4 200 л'],
      ['Рецептура', 'ТМ-5'],
      ['Готовность', '72%'],
    ],
  },
  blender2: {
    name: 'Блендинговый смеситель №2',
    shortName: 'Б2',
    stage: 'Смешивание масел',
    status: 'Гидравлическое',
    statusTone: 'running',
    throughput: '5 000 л/ч',
    currentFlow: '3 650 л',
    description: 'Смешивание основы, концентрата и присадок по рецептуре гидравлического масла.',
    metrics: [
      ['Текущая партия', '3 650 л'],
      ['Рецептура', 'ВМГЗ'],
      ['Готовность', '48%'],
    ],
  },
  blender3: {
    name: 'Блендинговый смеситель №3',
    shortName: 'Б3',
    stage: 'Смешивание масел',
    status: 'Готов',
    statusTone: 'ready',
    throughput: '5 000 л/ч',
    currentFlow: '0 л',
    description: 'Универсальный резервный смеситель для производства масла по выбранной рецептуре.',
    metrics: [
      ['Текущая партия', '0 л'],
      ['Последняя рецептура', 'И-40А'],
      ['Готовность', '100%'],
    ],
  },
  transmissionOilTank: {
    name: 'Бак трансмиссионного масла',
    shortName: 'ТМ',
    stage: 'Готовое масло',
    status: 'ТМ-5',
    statusTone: 'oil',
    throughput: '6 000 л/ч',
    currentFlow: '16 800 л',
    description: 'Бак закреплен за хранением готового трансмиссионного масла.',
    metrics: [
      ['Текущий объем', '16 800 л'],
      ['Вместимость', '25 000 л'],
      ['Марка', 'ТМ-5'],
    ],
  },
  hydraulicOilTank: {
    name: 'Бак гидравлического масла',
    shortName: 'ГМ',
    stage: 'Готовое масло',
    status: 'ВМГЗ',
    statusTone: 'oil',
    throughput: '6 000 л/ч',
    currentFlow: '12 400 л',
    description: 'Бак закреплен за хранением готового гидравлического масла.',
    metrics: [
      ['Текущий объем', '12 400 л'],
      ['Вместимость', '20 000 л'],
      ['Марка', 'ВМГЗ'],
    ],
  },
  industrialOilTank: {
    name: 'Бак индустриального масла',
    shortName: 'ИМ',
    stage: 'Готовое масло',
    status: 'И-40А',
    statusTone: 'oil',
    throughput: '6 000 л/ч',
    currentFlow: '9 750 л',
    description: 'Бак закреплен за хранением готового индустриального масла.',
    metrics: [
      ['Текущий объем', '9 750 л'],
      ['Вместимость', '20 000 л'],
      ['Марка', 'И-40А'],
    ],
  },
  motorOilTank: {
    name: 'Бак моторного масла',
    shortName: 'ММ',
    stage: 'Готовое масло',
    status: 'М-10Г2К',
    statusTone: 'oil',
    throughput: '6 000 л/ч',
    currentFlow: '7 300 л',
    description: 'Бак закреплен за хранением готового моторного масла.',
    metrics: [
      ['Текущий объем', '7 300 л'],
      ['Вместимость', '20 000 л'],
      ['Марка', 'М-10Г2К'],
    ],
  },
  fillingLine: {
    name: 'Участок розлива',
    shortName: 'РЗ',
    stage: 'Фасовка продукции',
    status: 'В работе',
    statusTone: 'oil',
    throughput: '4 000 л/ч',
    currentFlow: '2 850 л',
    description: 'Общая линия розлива готовых масел из выбранного продуктового бака.',
    metrics: [
      ['Розлито за смену', '2 850 л'],
      ['Текущая тара', '20 л'],
      ['Производительность', '78%'],
    ],
  },
}

const FlowNodesContext = createContext(FLOW_NODES)

function formatLiveVolume(value) {
  return t`${Number(value || 0).toLocaleString(getLocale(), { minimumFractionDigits: 3, maximumFractionDigits: 3 })} л`
}

function formatLiveDateTime(value) {
  if (!value) {
    return t('Движений пока нет')
  }
  return new Intl.DateTimeFormat(getLocale(), {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(value))
}

function buildOverviewContainerNode(baseNode, container, defaultName) {
  if (!container) {
    return {
      ...baseNode,
      name: defaultName,
      status: t('Не настроен'),
      statusTone: 'ready',
      currentFlow: t('0,000 л'),
      throughput: t('0,000 л'),
      capacityCaption: t('вместимость'),
      throughputLabel: t('Вместимость'),
      metrics: [
        [t('Текущий объём'), t('0,000 л')],
        [t('Состояние'), t('Нет активной ёмкости')],
      ],
      isLive: true,
    }
  }

  const hasVolume = Number(container.current_volume_liters) > 0
  return {
    ...baseNode,
    name: t(container.name),
    status: hasVolume ? t('Загружен') : t('Ожидает загрузки'),
    statusTone: hasVolume ? 'running' : 'ready',
    currentFlow: formatLiveVolume(container.current_volume_liters),
    throughput: formatLiveVolume(container.capacity_liters),
    capacityCaption: t('вместимость'),
    throughputLabel: t('Вместимость'),
    metrics: [
      [t('Текущий объём'), formatLiveVolume(container.current_volume_liters)],
      [t('Свободно'), formatLiveVolume(container.free_volume_liters)],
      [t('Заполнение'), `${container.fill_percentage}%`],
      [t('Последняя загрузка'), formatLiveDateTime(container.last_loading_at)],
    ],
    isLive: true,
  }
}

function buildOverviewTankSummaryNode(baseNode, summary, singularName, pluralName) {
  const hasVolume = Number(summary?.current_volume_liters) > 0
  const activeCount = Number(summary?.active_count || 0)
  return {
    ...baseNode,
    name: activeCount === 1 ? singularName : pluralName,
    status: activeCount === 0 ? t('Не настроен') : hasVolume ? t('Накапливается') : t('Ожидает загрузки'),
    statusTone: hasVolume ? 'running' : 'ready',
    currentFlow: formatLiveVolume(summary?.current_volume_liters),
    throughput: formatLiveVolume(summary?.capacity_liters),
    capacityCaption: t('вместимость'),
    throughputLabel: t('Общая вместимость'),
    metrics: [
      [t('Текущий объём'), formatLiveVolume(summary?.current_volume_liters)],
      [t('Свободно'), formatLiveVolume(summary?.free_volume_liters)],
      [t('Заполнение'), `${summary?.fill_percentage || '0.00'}%`],
      [t('Активных баков'), String(activeCount)],
      [t('Последняя загрузка'), formatLiveDateTime(summary?.last_loading_at)],
    ],
    isLive: true,
  }
}

function ProcessNode({ nodeId, selectedNodeId, onSelect, compact = false }) {
  const node = useContext(FlowNodesContext)[nodeId]

  return (
    <button
      className={`process-node process-node--${node.statusTone} ${compact ? 'process-node--compact' : ''} ${selectedNodeId === nodeId ? 'selected' : ''}`}
      type="button"
      aria-pressed={selectedNodeId === nodeId}
      onClick={() => onSelect(nodeId)}
    >
      <span className="process-node-topline">
        <span className="process-node-icon">{node.shortName}</span>
        <span className="process-node-status"><i />{node.status}</span>
      </span>
      <span className="process-node-stage">{node.stage}</span>
      <strong>{node.name}</strong>
      <span className="process-node-reading">{node.currentFlow}</span>
      <span className="process-node-capacity">{node.capacityCaption ? `${node.capacityCaption} ${node.throughput}` : t`до ${node.throughput}`}</span>
    </button>
  )
}

function FlowArrow({ direction = 'right' }) {
  return (
    <div className={`process-arrow process-arrow--${direction}`} aria-hidden="true">
      <div className="process-arrow-line" />
    </div>
  )
}

function ProcessOutlet({ nodeId, selectedNodeId, onSelect }) {
  const node = useContext(FlowNodesContext)[nodeId]

  return (
    <button
      className={`process-outlet process-outlet--${node.statusTone} ${selectedNodeId === nodeId ? 'selected' : ''}`}
      type="button"
      aria-pressed={selectedNodeId === nodeId}
      onClick={() => onSelect(nodeId)}
    >
      <span>{node.name}</span>
      <strong>{node.currentFlow}</strong>
    </button>
  )
}

function CompactNodeGroup({ nodeIds, selectedNodeId, onSelect }) {
  return (
    <div className="compact-node-group">
      {nodeIds.map((nodeId) => (
        <ProcessNode compact key={nodeId} nodeId={nodeId} selectedNodeId={selectedNodeId} onSelect={onSelect} />
      ))}
    </div>
  )
}

function OilRoutingMatrix({ mixerCount = 3, tankCount = 4 }) {
  const inputs = Array.from({ length: mixerCount }, (_, index) => (index + 0.5) * 300 / mixerCount)
  const outputs = Array.from({ length: tankCount }, (_, index) => (index + 0.5) * 300 / tankCount)
  return (
    <div className="oil-routing-matrix" aria-label={t('Любой смеситель может подавать масло в любой продуктовый бак')}>
      <svg viewBox="0 0 100 300" preserveAspectRatio="none" aria-hidden="true">
        <defs>
          <marker id="oil-route-arrow" markerHeight="6" markerWidth="6" orient="auto" refX="5" refY="3">
            <path d="M0 0 L6 3 L0 6 Z" />
          </marker>
        </defs>
        {inputs.map((position) => <path key={`input-${position}`} d={`M3 ${position} C32 ${position} 36 150 52 150`} />)}
        {outputs.map((position) => <path key={`output-${position}`} d={`M52 150 C68 150 72 ${position} 97 ${position}`} markerEnd="url(#oil-route-arrow)" />)}
        {inputs.map((position) => <circle key={position} cx="3" cy={position} r="3" />)}
        <circle cx="52" cy="150" r="4" />
      </svg>
    </div>
  )
}

function OilTankMerge({ tankCount = 4 }) {
  const inputs = Array.from({ length: tankCount }, (_, index) => (index + 0.5) * 300 / tankCount)
  return (
    <div className="oil-tank-merge" aria-hidden="true">
      <svg viewBox="0 0 70 300" preserveAspectRatio="none">
        <defs>
          <marker id="oil-merge-arrow" markerHeight="6" markerWidth="6" orient="auto" refX="5" refY="3">
            <path d="M0 0 L6 3 L0 6 Z" />
          </marker>
        </defs>
        {inputs.map((position) => <path key={`input-${position}`} d={`M3 ${position} C28 ${position} 26 150 45 150`} />)}
        <path d="M45 150 H67" markerEnd="url(#oil-merge-arrow)" />
        {inputs.map((position) => <circle key={position} cx="3" cy={position} r="3" />)}
      </svg>
    </div>
  )
}

function ProcessDetails({ nodeId }) {
  const node = useContext(FlowNodesContext)[nodeId]
  if (!node) return <p className="empty-state">{t('Этап больше недоступен. Обновите список оборудования.')}</p>

  return (
    <aside className="process-details" aria-live="polite">
      <div className="process-details-heading">
        <span className={`process-node-icon process-node-icon--${node.statusTone}`}>{node.shortName}</span>
        <div>
          <p>{node.stage}</p>
          <h2>{node.name}</h2>
        </div>
        <span className={`process-detail-status process-detail-status--${node.statusTone}`}>{node.status}</span>
      </div>
      <p className="process-details-description">{node.description}</p>
      <dl>
        <div>
          <dt>{node.throughputLabel || t('Пропускная способность')}</dt>
          <dd>{node.throughput}</dd>
        </div>
        {node.metrics.map(([label, value]) => (
          <div key={label}>
            <dt>{label}</dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>
      <p className="process-data-note">{node.dataNote || (node.isLive ? t('Актуальные данные производственного учёта') : t('Демонстрационные данные · узел подготовлен для подключения к API'))}</p>
    </aside>
  )
}

function buildPackagingOverviewNodes(nodes, summary) {
  if (!summary) return {}
  const result = {}
  const kilograms = (value) => `${Number(value).toLocaleString(getLocale(), { maximumFractionDigits: 2 })} ${t('кг')}`
  const pieces = (value) => `${Number(value).toLocaleString(getLocale())} ${t('шт.')}`
  for (const line of CANISTER_PRODUCTION_LINES) {
    const state = summary[line.id]
    if (!state) continue
    for (const [nodeId, role] of [[line.granulesId, 'granules'], [line.dyeId, 'dye']]) {
      const material = state.materials[role]
      result[nodeId] = {
        ...nodes[nodeId], isLive: true, stage: t('Остаток в производстве'), status: t('Учёт сырья'),
        currentFlow: kilograms(material.available_quantity),
        metrics: [[t('Загружено'), kilograms(material.loaded_quantity)], [t('Использовано'), kilograms(material.used_quantity)], [t('Доступно'), kilograms(material.available_quantity)]],
        dataNote: t('Материалы на производственном участке, не остаток склада.'),
      }
    }
    const counts = state.output_totals
    result[line.productionId] = {
      ...nodes[line.productionId], isLive: true, status: t('Учёт выпуска'),
      currentFlow: pieces(counts.good + counts.deviation + counts.reject),
      metrics: [[t('Годные'), pieces(counts.good)], ...(line.id === 'canisters' ? [[t('С отклонениями'), pieces(counts.deviation)]] : []), [t('Брак'), pieces(counts.reject)]],
      dataNote: t('Зарегистрированный выпуск. Это не складской остаток готовой продукции.'),
    }
    const dispositions = line.id === 'canisters' ? ['good', 'deviation', 'reject'] : ['good', 'reject']
    line.outputIds.forEach((nodeId, index) => {
      result[nodeId] = {
        ...nodes[nodeId], isLive: true, stage: t('Результат выпуска'), status: t('Учёт выпуска'),
        currentFlow: pieces(counts[dispositions[index]]), metrics: [[t('Всего зарегистрировано'), pieces(counts[dispositions[index]])]],
        dataNote: t('Зарегистрированный выпуск. Оприходование на склад и измельчение пока не подключены.'),
      }
    })
  }
  return result
}

function buildOilFinishingNodes(nodes, summary, sorbentCycle) {
  if (!summary) return {}
  const result = {}
  for (const [nodeId, kind, singular, plural] of [
    ['sorbentSystem', 'sorption_system', 'Сорбент-система', 'Сорбент-системы'],
    ['finishingMixer', 'finishing_mixer', 'Финишный миксер', 'Финишные миксеры'],
    ['filter', 'finishing_filter', 'Финишный фильтр', 'Финишные фильтры'],
    ['finishedDieselTank', 'finished_diesel_tank', 'Бак готовой солярки', 'Баки готовой солярки'],
    ['finishedSpindleTank', 'finished_spindle_tank', 'Бак готовой веретенки', 'Баки готовой веретенки'],
  ]) {
    const state = summary[kind]
    const items = state?.items || []
    const lastLoading = items.map((item) => item.last_loading_at).filter(Boolean).sort().at(-1)
    const node = buildOverviewTankSummaryNode(nodes[nodeId], { ...state, last_loading_at: lastLoading }, t(singular), t(plural))
    const products = [...new Set(items.map((item) => item.oil_product).filter(Boolean))]
    node.metrics = node.metrics.map(([label, value]) => [label === t('Активных баков') ? t('Активных ёмкостей') : label, value])
    if (products.length) node.metrics.push([t('Продукт'), products.map((product) => t(product === 'diesel' ? 'Солярка' : 'Веретенка')).join(', ')])
    node.metrics.push(...items.map((item) => [t(item.name), formatLiveVolume(item.current_volume_liters)]))
    result[nodeId] = node
  }
  for (const nodeId of ['water', 'waste']) {
    const state = summary.separator_outputs?.[nodeId]
    result[nodeId] = {
      ...nodes[nodeId], isLive: true, status: t('Учёт отгрузок'),
      currentFlow: formatLiveVolume(state?.today_liters),
      throughput: formatLiveVolume(state?.total_liters), capacityCaption: t('всего отгружено'),
      throughputLabel: t('Всего отгружено'),
      metrics: [[t('Отгружено сегодня'), formatLiveVolume(state?.today_liters)]],
      dataNote: t('Отгрузки сепаратора за вычетом компенсированных движений. Это не остаток в накопителе.'),
    }
  }
  const kilograms = (value) => value == null ? '—' : `${Number(value).toLocaleString(getLocale(), { maximumFractionDigits: 2 })} ${t('кг')}`
  result.sorbentTank = {
    ...nodes.sorbentTank, isLive: true, status: t('Замкнутый контур'),
    currentFlow: kilograms(sorbentCycle?.tank_kg), throughput: kilograms(sorbentCycle?.total_kg),
    capacityCaption: t('всего в контуре'), throughputLabel: t('Всего в контуре'),
    metrics: [[t('В баке сорбента'), kilograms(sorbentCycle?.tank_kg)], [t('В сорбент-системах'), kilograms(sorbentCycle?.in_system_kg)], [t('На прогреве и очистке'), kilograms(sorbentCycle?.regeneration_kg)]],
    dataNote: t('Очищенный сорбент возвращается в бак. Склад списывается только при пополнении новым сорбентом.'),
  }
  result.sorbentSystem.metrics.push([t('В сорбент-системах'), kilograms(sorbentCycle?.in_system_kg)])
  return result
}

function buildManufacturingNodes(nodes, summary) {
  if (!summary) return {}
  const result = {}
  const makeVessel = (base, equipment, name) => ({
    ...base, name: equipment ? t(equipment.name) : t(name), isLive: true,
    status: equipment?.active_batch ? t('Открыта партия') : equipment ? t('Ожидает загрузки') : t('Не настроен'),
    statusTone: equipment?.active_batch ? 'running' : 'ready',
    currentFlow: formatLiveVolume(equipment?.active_batch?.input_liters),
    throughput: formatLiveVolume(equipment?.capacity_liters), capacityCaption: t('вместимость'), throughputLabel: t('Вместимость'),
    metrics: [
      [t('Загружено жидких компонентов'), formatLiveVolume(equipment?.active_batch?.input_liters)],
      [t('Перелито по замеру'), formatLiveVolume(equipment?.active_batch?.output_liters)],
      [t('Марка масла'), equipment?.active_batch?.grade_name || '—'],
    ],
    dataNote: t('Показана загрузка открытой партии, не расчётный остаток готовой смеси. Фактический выход учитывается при переливе.'),
  })
  const reactors = summary.concentrate_reactor || []
  result.concentrateReactor = makeVessel(nodes.concentrateReactor, reactors[0], 'Реактор концентрата')
  if (reactors.length > 1) {
    result.concentrateReactor.name = t('Реакторы концентрата')
    result.concentrateReactor.currentFlow = formatLiveVolume(reactors.reduce((total, item) => total + Number(item.active_batch?.input_liters || 0), 0))
    result.concentrateReactor.throughput = formatLiveVolume(reactors.reduce((total, item) => total + Number(item.capacity_liters), 0))
    result.concentrateReactor.status = reactors.some((item) => item.active_batch) ? t('Открыта партия') : t('Ожидает загрузки')
    result.concentrateReactor.statusTone = reactors.some((item) => item.active_batch) ? 'running' : 'ready'
    result.concentrateReactor.metrics = reactors.map((item) => [t(item.name), item.active_batch ? `${item.active_batch.number} · ${formatLiveVolume(item.active_batch.input_liters)}` : t('Нет открытой партии')])
  }
  for (const [index, equipment] of (summary.oil_blender || []).entries()) {
    result[`liveBlender${equipment.id}`] = {
      ...makeVessel(nodes[`blender${Math.min(index + 1, 3)}`], equipment, 'Блендинговый смеситель'),
      shortName: String(index + 1),
      description: t('Смешивание веретенки и концентрата для выбранной марки масла. Присадки пока не учитываются.'),
    }
  }
  for (const nodeId of ['blender1', 'blender2', 'blender3']) {
    result[nodeId] = {
      ...makeVessel(nodes[nodeId], null, 'Блендинговый смеситель'),
      description: t('Смешивание веретенки и концентрата для выбранной марки масла. Присадки пока не учитываются.'),
    }
  }
  const tankTemplates = ['transmissionOilTank', 'hydraulicOilTank', 'industrialOilTank', 'motorOilTank']
  for (const [index, tank] of (summary.tanks || []).entries()) {
    result[`liveOilTank${tank.id}`] = {
      ...buildOverviewContainerNode(nodes[tankTemplates[index % 4]], tank, 'Бак товарного масла'),
      shortName: String(index + 1),
      description: t('Хранение готового масла выбранной марки. Смешивание разных марок запрещено.'),
      metrics: [[t('Марка масла'), tank.grade_name], [t('Текущий объём'), formatLiveVolume(tank.current_volume_liters)], [t('Свободно'), formatLiveVolume(tank.free_volume_liters)]],
    }
  }
  for (const [index, nodeId] of tankTemplates.entries()) {
    result[nodeId] = {
      ...buildOverviewContainerNode(nodes[nodeId], null, t('Бак товарного масла')),
      shortName: String(index + 1),
      description: t('Хранение готового масла выбранной марки. Смешивание разных марок запрещено.'),
    }
  }
  result.polypropyleneFeed = {
    ...nodes.polypropyleneFeed, isLive: true, status: t('Складской остаток'),
    currentFlow: `${Number(summary.polypropylene_kg).toLocaleString(getLocale())} ${t('кг')}`,
    throughput: '—', capacityCaption: t('склад'), throughputLabel: t('Дозирование'),
    metrics: [], dataNote: t('Полипропилен списывается со склада одновременно с загрузкой веретенки в реактор.'),
  }
  result.additiveStation = {
    ...nodes.additiveStation, status: t('Учёт не ведётся'), currentFlow: '—', throughput: '—', metrics: [],
    dataNote: t('Присадки пока не учитываются и не списываются со склада.'),
  }
  result.fillingLine = {
    ...nodes.fillingLine, isLive: true, status: t('Учёт розлива'),
    currentFlow: formatLiveVolume(summary.filled_today_liters),
    throughput: formatLiveVolume(summary.filled_total_liters), capacityCaption: t('всего'), throughputLabel: t('Всего розлито'),
    metrics: [[t('Розлито сегодня'), formatLiveVolume(summary.filled_today_liters)]],
    dataNote: t('Масло списывается из бака. Тара и складской приход фасованной продукции не учитываются.'),
  }
  return result
}

export function OverviewPage({ onLogout, token, user }) {
  const language = useLanguage()
  const [activeTab, setActiveTab] = useState('recycling')
  const [selectedNodeId, setSelectedNodeIdState] = useState('reception')
  const [detailsNodeId, setDetailsNodeId] = useState(null)
  const [overviewData, setOverviewData] = useState(null)
  const [overviewError, setOverviewError] = useState('')

  useEffect(() => {
    let isCancelled = false

    async function loadOverview() {
      try {
        const data = await apiRequest('/api/dashboard/overview/', token)
        if (!isCancelled) {
          setOverviewData(data)
          setOverviewError('')
        }
      } catch (loadError) {
        if (!isCancelled) {
          setOverviewError(loadError.message)
        }
      }
    }

    loadOverview()
    const refreshTimer = window.setInterval(loadOverview, OVERVIEW_REFRESH_INTERVAL)
    return () => {
      isCancelled = true
      window.clearInterval(refreshTimer)
    }
  }, [token])

  const flowNodes = useMemo(() => {
    const nodes = localizeStaticData(FLOW_NODES, language)
    if (!overviewData) {
      const liveNodeIds = ['reception', 'storageTank', 'preheater', 'separator', 'water', 'waste',
        'chemicalMixer1', 'chemicalMixer2', 'workshop1', 'workshop2', 'rawDieselTank', 'rawSpindleTank',
        'sorbentSystem', 'sorbentTank', 'finishingMixer', 'filter', 'finishedDieselTank', 'finishedSpindleTank',
        'polypropyleneFeed', 'concentrateReactor', 'additiveStation', 'blender1', 'blender2', 'blender3',
        'transmissionOilTank', 'hydraulicOilTank', 'industrialOilTank', 'motorOilTank', 'fillingLine']
      return { ...nodes, ...Object.fromEntries(liveNodeIds.map((nodeId) => [nodeId, {
        ...nodes[nodeId], status: overviewError ? t('Нет данных') : t('Загрузка...'),
        currentFlow: '—', throughput: '—', metrics: [], dataNote: t('Актуальные показатели ещё не получены.'),
      }])) }
    }

    const reception = overviewData.reception
    const tanks = overviewData.receiving_tanks
    const boilers = overviewData.preheating_boilers
    const separators = overviewData.separators
    const chemicalMixers = overviewData.chemical_mixers?.items || []
    const processingWorkshops = overviewData.processing_workshops?.items || []
    const rawDieselTanks = overviewData.raw_diesel_tanks
    const rawSpindleTanks = overviewData.raw_spindle_tanks
    return {
      ...nodes,
      ...buildPackagingOverviewNodes(nodes, overviewData.packaging_production),
      ...buildOilFinishingNodes(nodes, overviewData.oil_finishing, overviewData.sorbent_cycle),
      ...buildManufacturingNodes(nodes, overviewData.oil_manufacturing),
      reception: {
        ...nodes.reception,
        status: reception.open_receipt_count > 0 ? t('Прием идет') : t('Нет активных приемов'),
        statusTone: reception.open_receipt_count > 0 ? 'running' : 'ready',
        currentFlow: formatLiveVolume(reception.accepted_today_liters),
        throughput: t`${reception.completed_today_count} завершено`,
        capacityCaption: t('сегодня'),
        throughputLabel: t('Завершено сегодня'),
        metrics: [
          [t('Принято сегодня'), formatLiveVolume(reception.accepted_today_liters)],
          [t('Открытых приемов'), String(reception.open_receipt_count)],
          [t('Средний прием'), formatLiveVolume(reception.average_receipt_liters)],
        ],
        isLive: true,
      },
      storageTank: {
        ...nodes.storageTank,
        name: tanks.active_count === 1 ? t('Приемный бак') : t('Приемные баки'),
        status: Number(tanks.current_volume_liters) > 0 ? t('Накапливается') : t('Пусто'),
        statusTone: Number(tanks.current_volume_liters) > 0 ? 'running' : 'ready',
        currentFlow: formatLiveVolume(tanks.current_volume_liters),
        throughput: formatLiveVolume(tanks.capacity_liters),
        capacityCaption: t('вместимость'),
        throughputLabel: t('Общая вместимость'),
        metrics: [
          [t('Текущий объем'), formatLiveVolume(tanks.current_volume_liters)],
          [t('Свободно'), formatLiveVolume(tanks.free_volume_liters)],
          [t('Заполнение'), `${tanks.fill_percentage}%`],
          [t('Активных баков'), String(tanks.active_count)],
          [t('Последнее движение'), formatLiveDateTime(tanks.last_movement_at)],
        ],
        isLive: true,
      },
      preheater: {
        ...nodes.preheater,
        name: boilers.active_count === 1 ? t('Котел первичного прогрева') : t('Котлы первичного прогрева'),
        status: Number(boilers.current_volume_liters) > 0 ? t('Загружен') : t('Ожидает загрузки'),
        statusTone: Number(boilers.current_volume_liters) > 0 ? 'running' : 'ready',
        currentFlow: formatLiveVolume(boilers.current_volume_liters),
        throughput: formatLiveVolume(boilers.capacity_liters),
        capacityCaption: t('вместимость'),
        throughputLabel: t('Общая вместимость'),
        metrics: [
          [t('Текущий объем'), formatLiveVolume(boilers.current_volume_liters)],
          [t('Свободно'), formatLiveVolume(boilers.free_volume_liters)],
          [t('Заполнение'), `${boilers.fill_percentage}%`],
          [t('Активных котлов'), String(boilers.active_count)],
          [t('Последняя загрузка'), formatLiveDateTime(boilers.last_loading_at)],
        ],
        isLive: true,
      },
      separator: {
        ...nodes.separator,
        name: separators.active_count === 1 ? t('Сепаратор') : t('Сепараторы'),
        status: Number(separators.current_volume_liters) > 0 ? t('Загружен') : t('Ожидает загрузки'),
        statusTone: Number(separators.current_volume_liters) > 0 ? 'running' : 'ready',
        currentFlow: formatLiveVolume(separators.current_volume_liters),
        throughput: formatLiveVolume(separators.capacity_liters),
        capacityCaption: t('вместимость'),
        throughputLabel: t('Общая вместимость'),
        metrics: [
          [t('Текущий объем'), formatLiveVolume(separators.current_volume_liters)],
          [t('Свободно'), formatLiveVolume(separators.free_volume_liters)],
          [t('Заполнение'), `${separators.fill_percentage}%`],
          [t('Активных сепараторов'), String(separators.active_count)],
          [t('Последняя загрузка'), formatLiveDateTime(separators.last_loading_at)],
        ],
        isLive: true,
      },
      chemicalMixer1: buildOverviewContainerNode(nodes.chemicalMixer1, chemicalMixers[0], t('Химический миксер №1')),
      chemicalMixer2: buildOverviewContainerNode(nodes.chemicalMixer2, chemicalMixers[1], t('Химический миксер №2')),
      workshop1: buildOverviewContainerNode(nodes.workshop1, processingWorkshops[0], t('Цех переработки №1')),
      workshop2: buildOverviewContainerNode(nodes.workshop2, processingWorkshops[1], t('Цех переработки №2')),
      rawDieselTank: buildOverviewTankSummaryNode(nodes.rawDieselTank, rawDieselTanks, t('Бак сырой солярки'), t('Баки сырой солярки')),
      rawSpindleTank: buildOverviewTankSummaryNode(nodes.rawSpindleTank, rawSpindleTanks, t('Бак сырой веретенки'), t('Баки сырой веретенки')),
    }
  }, [overviewData, overviewError, language])

  const selectTab = (tabId) => {
    setActiveTab(tabId)
    setSelectedNodeIdState({ recycling: 'reception', 'oil-production': 'finishedSpindleTank', 'canister-production': 'canisterGranules' }[tabId])
    setDetailsNodeId(null)
  }

  const setSelectedNodeId = (nodeId) => {
    setSelectedNodeIdState(nodeId)
    setDetailsNodeId(nodeId)
  }

  return (
    <DashboardShell title={t('Обзор производства')} onLogout={onLogout} user={user}>
      <FlowNodesContext.Provider value={flowNodes}>
      <section className="process-overview">
        <div className="process-tabs" role="tablist" aria-label={t('Производственные схемы')}>
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === 'recycling'}
            aria-controls="recycling-process-panel"
            className={activeTab === 'recycling' ? 'process-tab process-tab--active' : 'process-tab'}
            onClick={() => selectTab('recycling')}
          >{t('Переработка отработанного масла')}</button>
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === 'oil-production'}
            aria-controls="oil-production-panel"
            className={activeTab === 'oil-production' ? 'process-tab process-tab--active' : 'process-tab'}
            onClick={() => selectTab('oil-production')}
          >{t('Производство масла')}</button>
          <button
            id="canister-production-tab"
            type="button"
            role="tab"
            aria-selected={activeTab === 'canister-production'}
            aria-controls="canister-production-panel"
            className={activeTab === 'canister-production' ? 'process-tab process-tab--active' : 'process-tab'}
            onClick={() => selectTab('canister-production')}
          >{t('Производство канистр')}</button>
        </div>

        {activeTab === 'recycling' && (
          <div id="recycling-process-panel" role="tabpanel">
            <header className="process-overview-header">
              <div>
                <p className="auth-eyebrow">{t('Технологическая линия')}</p>
                <h1>{t('Переработка отработанного масла')}</h1>
                <p>{t('Реальный учёт движений от приёма до готовых баков и замкнутого контура сорбента. Технологические параметры пока не учитываются.')}</p>
              </div>
              <div className="process-summary">
                <span><i className="summary-indicator" />{t('Учёт подключён')}</span>
                <strong>{overviewData ? formatLiveVolume(overviewData.reception.accepted_today_liters) : t('Загрузка...')}</strong>
                <small>{t('принято сегодня')}</small>
              </div>
            </header>

            {overviewError && <p className="process-live-error">{t('Не удалось обновить реальные показатели: ')}{t(overviewError)}</p>}

            <div className="process-legend" aria-label={t('Легенда схемы')}>
              <span><i className="legend-line legend-line--product" />{t('Основной продукт')}</span>
              <span><i className="legend-line legend-line--water" />{t('Вода')}</span>
              <span><i className="legend-line legend-line--waste" />{t('Мусор')}</span>
              <span><i className="legend-line legend-line--sorbent" />{t('Сорбент')}</span>
              <span><i className="legend-status legend-status--running" />{t('В работе')}</span>
              <span><i className="legend-status legend-status--ready" />{t('Готов / ожидает')}</span>
              <small>{t('Жидкие продукты — литры, твердые компоненты — килограммы')}</small>
            </div>

            <div className="process-scroll-hint">
              <span>{t('Нажмите на этап, чтобы посмотреть показатели')}</span>
              <span>{t('Направление потока показано змейкой ↓')}</span>
            </div>

            <div className="process-snake">
          <div className="snake-row snake-row--forward">
            <ProcessNode compact nodeId="reception" selectedNodeId={selectedNodeId} onSelect={setSelectedNodeId} />
            <FlowArrow />
            <ProcessNode compact nodeId="storageTank" selectedNodeId={selectedNodeId} onSelect={setSelectedNodeId} />
            <FlowArrow />
            <ProcessNode compact nodeId="preheater" selectedNodeId={selectedNodeId} onSelect={setSelectedNodeId} />
            <FlowArrow />
            <div className="snake-separator">
              <ProcessNode compact nodeId="separator" selectedNodeId={selectedNodeId} onSelect={setSelectedNodeId} />
              <div className="separator-outlets">
                <ProcessOutlet nodeId="water" selectedNodeId={selectedNodeId} onSelect={setSelectedNodeId} />
                <ProcessOutlet nodeId="waste" selectedNodeId={selectedNodeId} onSelect={setSelectedNodeId} />
              </div>
            </div>
          </div>

          <div className="snake-turn snake-turn--right">
            <i />
          </div>

          <div className="snake-row snake-row--reverse">
            <div className="snake-sorbent-inline">
              <span>{t('↔ замкнутый контур сорбента')}</span>
              <ProcessNode compact nodeId="sorbentTank" selectedNodeId={selectedNodeId} onSelect={setSelectedNodeId} />
              <ProcessNode compact nodeId="sorbentSystem" selectedNodeId={selectedNodeId} onSelect={setSelectedNodeId} />
            </div>
            <FlowArrow direction="left" />
            <CompactNodeGroup nodeIds={['rawDieselTank', 'rawSpindleTank']} selectedNodeId={selectedNodeId} onSelect={setSelectedNodeId} />
            <FlowArrow direction="left" />
            <CompactNodeGroup nodeIds={['workshop1', 'workshop2']} selectedNodeId={selectedNodeId} onSelect={setSelectedNodeId} />
            <FlowArrow direction="left" />
            <CompactNodeGroup nodeIds={['chemicalMixer1', 'chemicalMixer2']} selectedNodeId={selectedNodeId} onSelect={setSelectedNodeId} />
          </div>

          <div className="snake-turn snake-turn--left">
            <i />
          </div>

          <div className="snake-row snake-row--forward snake-row--final">
            <ProcessNode compact nodeId="finishingMixer" selectedNodeId={selectedNodeId} onSelect={setSelectedNodeId} />
            <FlowArrow />
            <ProcessNode compact nodeId="filter" selectedNodeId={selectedNodeId} onSelect={setSelectedNodeId} />
            <FlowArrow />
            <CompactNodeGroup nodeIds={['finishedSpindleTank', 'finishedDieselTank']} selectedNodeId={selectedNodeId} onSelect={setSelectedNodeId} />
          </div>
            </div>
          </div>
        )}

        {activeTab === 'oil-production' && (
        <section id="oil-production-panel" className="oil-production-section" role="tabpanel">
          {overviewError && <p className="process-live-error" role="alert">{t('Не удалось обновить реальные показатели: ')}{t(overviewError)}</p>}
          <header className="oil-production-header">
            <div>
              <p className="auth-eyebrow">{t('Дополнительная производственная линия')}</p>
              <h2>{t('Производство масел')}</h2>
              <p>{t('Изготовление товарных масел из готовой веретенки, концентрата и пакетов присадок.')}</p>
            </div>
            <div className="oil-production-summary">
              <span><i />{t('Учёт подключён')}</span>
              <strong>{formatLiveVolume((overviewData?.oil_manufacturing?.oil_blender || []).reduce((total, equipment) => total + Number(equipment.active_batch?.input_liters || 0), 0))}</strong>
              <small>{t('загружено в открытые партии')}</small>
            </div>
          </header>

          <div className="oil-production-legend">
            <span><i className="legend-line legend-line--product" />{t('Веретенка и концентрат')}</span>
            <span><i className="legend-line legend-line--material" />{t('Загуститель и присадки')}</span>
            <span><i className="legend-line legend-line--oil" />{t('Готовые масла')}</span>
            <small>{t('Жидкие продукты — литры, твердые компоненты — килограммы')}</small>
          </div>

          <div className="oil-production-map">
            <div className="oil-stage oil-preparation-stage">
              <span className="oil-stage-title">{t('Приготовление концентрата')}</span>
              <div className="oil-preparation-inputs">
                <ProcessNode compact nodeId="finishedSpindleTank" selectedNodeId={selectedNodeId} onSelect={setSelectedNodeId} />
                <ProcessNode compact nodeId="polypropyleneFeed" selectedNodeId={selectedNodeId} onSelect={setSelectedNodeId} />
              </div>
              <div className="oil-input-merge" aria-hidden="true"><i /><i /><b /></div>
              <ProcessNode compact nodeId="concentrateReactor" selectedNodeId={selectedNodeId} onSelect={setSelectedNodeId} />
            </div>

            <FlowArrow />

            <div className="oil-stage oil-blending-stage">
              <span className="oil-stage-title">{t('Блендинговые смесители')}</span>
              <div className="oil-blending-feeds">
                <ProcessOutlet nodeId="finishedSpindleTank" selectedNodeId={selectedNodeId} onSelect={setSelectedNodeId} />
                <ProcessOutlet nodeId="additiveStation" selectedNodeId={selectedNodeId} onSelect={setSelectedNodeId} />
              </div>
              <div className="oil-blenders">
                {(overviewData?.oil_manufacturing?.oil_blender?.length ? overviewData.oil_manufacturing.oil_blender.map((item) => `liveBlender${item.id}`) : ['blender1', 'blender2', 'blender3']).map((nodeId) => (
                  <ProcessNode compact key={nodeId} nodeId={nodeId} selectedNodeId={selectedNodeId} onSelect={setSelectedNodeId} />
                ))}
              </div>
            </div>

            <OilRoutingMatrix mixerCount={overviewData?.oil_manufacturing?.oil_blender?.length || 3} tankCount={overviewData?.oil_manufacturing?.tanks?.length || 4} />

            <div className="oil-stage oil-product-tanks">
              <span className="oil-stage-title">{t('Баки готовых масел')}</span>
              <div>
                {(overviewData?.oil_manufacturing?.tanks?.length ? overviewData.oil_manufacturing.tanks.map((item) => `liveOilTank${item.id}`) : ['transmissionOilTank', 'hydraulicOilTank', 'industrialOilTank', 'motorOilTank']).map((nodeId) => (
                  <ProcessNode compact key={nodeId} nodeId={nodeId} selectedNodeId={selectedNodeId} onSelect={setSelectedNodeId} />
                ))}
              </div>
            </div>

            <OilTankMerge tankCount={overviewData?.oil_manufacturing?.tanks?.length || 4} />

            <div className="oil-stage oil-filling-stage">
              <span className="oil-stage-title">{t('Общий розлив')}</span>
              <ProcessNode compact nodeId="fillingLine" selectedNodeId={selectedNodeId} onSelect={setSelectedNodeId} />
            </div>
          </div>
        </section>
        )}

        {activeTab === 'canister-production' && (
          <CanisterProduction
            renderNode={(nodeId) => <ProcessNode compact nodeId={nodeId} selectedNodeId={selectedNodeId} onSelect={setSelectedNodeId} />}
          />
        )}

        {detailsNodeId && (
          <Modal title={t('Информация об этапе')} onClose={() => setDetailsNodeId(null)}>
            <ProcessDetails nodeId={detailsNodeId} />
          </Modal>
        )}
      </section>
      </FlowNodesContext.Provider>
    </DashboardShell>
  )
}
