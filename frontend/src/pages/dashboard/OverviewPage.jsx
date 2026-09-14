import { createContext, useContext, useEffect, useMemo, useState } from 'react'
import { apiRequest } from '../../api/client'
import { DashboardShell } from '../../components/Layout/DashboardShell'
import { Modal } from '../../components/Modal/Modal'

const OVERVIEW_REFRESH_INTERVAL = 15000

const FLOW_NODES = {
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
  return `${Number(value || 0).toLocaleString('ru-RU', { minimumFractionDigits: 3, maximumFractionDigits: 3 })} л`
}

function formatLiveDateTime(value) {
  if (!value) {
    return 'Движений пока нет'
  }
  return new Intl.DateTimeFormat('ru-RU', {
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
      status: 'Не настроен',
      statusTone: 'ready',
      currentFlow: '0,000 л',
      throughput: '0,000 л',
      capacityCaption: 'вместимость',
      throughputLabel: 'Вместимость',
      metrics: [
        ['Текущий объём', '0,000 л'],
        ['Состояние', 'Нет активной ёмкости'],
      ],
      isLive: true,
    }
  }

  const hasVolume = Number(container.current_volume_liters) > 0
  return {
    ...baseNode,
    name: container.name,
    status: hasVolume ? 'Загружен' : 'Ожидает загрузки',
    statusTone: hasVolume ? 'running' : 'ready',
    currentFlow: formatLiveVolume(container.current_volume_liters),
    throughput: formatLiveVolume(container.capacity_liters),
    capacityCaption: 'вместимость',
    throughputLabel: 'Вместимость',
    metrics: [
      ['Текущий объём', formatLiveVolume(container.current_volume_liters)],
      ['Свободно', formatLiveVolume(container.free_volume_liters)],
      ['Заполнение', `${container.fill_percentage}%`],
      ['Последняя загрузка', formatLiveDateTime(container.last_loading_at)],
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
    status: activeCount === 0 ? 'Не настроен' : hasVolume ? 'Накапливается' : 'Ожидает загрузки',
    statusTone: hasVolume ? 'running' : 'ready',
    currentFlow: formatLiveVolume(summary?.current_volume_liters),
    throughput: formatLiveVolume(summary?.capacity_liters),
    capacityCaption: 'вместимость',
    throughputLabel: 'Общая вместимость',
    metrics: [
      ['Текущий объём', formatLiveVolume(summary?.current_volume_liters)],
      ['Свободно', formatLiveVolume(summary?.free_volume_liters)],
      ['Заполнение', `${summary?.fill_percentage || '0.00'}%`],
      ['Активных баков', String(activeCount)],
      ['Последняя загрузка', formatLiveDateTime(summary?.last_loading_at)],
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
      <span className="process-node-capacity">{node.capacityCaption || 'до'} {node.throughput}</span>
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

function OilRoutingMatrix() {
  return (
    <div className="oil-routing-matrix" aria-label="Любой смеситель может подавать масло в любой продуктовый бак">
      <svg viewBox="0 0 100 300" preserveAspectRatio="none" aria-hidden="true">
        <defs>
          <marker id="oil-route-arrow" markerHeight="6" markerWidth="6" orient="auto" refX="5" refY="3">
            <path d="M0 0 L6 3 L0 6 Z" />
          </marker>
        </defs>
        <path d="M3 55 C32 55 36 150 52 150" />
        <path d="M3 150 H52" />
        <path d="M3 245 C32 245 36 150 52 150" />
        <path d="M52 150 C68 150 72 45 97 45" markerEnd="url(#oil-route-arrow)" />
        <path d="M52 150 C68 150 72 115 97 115" markerEnd="url(#oil-route-arrow)" />
        <path d="M52 150 C68 150 72 185 97 185" markerEnd="url(#oil-route-arrow)" />
        <path d="M52 150 C68 150 72 255 97 255" markerEnd="url(#oil-route-arrow)" />
        <circle cx="3" cy="55" r="3" />
        <circle cx="3" cy="150" r="3" />
        <circle cx="3" cy="245" r="3" />
        <circle cx="52" cy="150" r="4" />
      </svg>
    </div>
  )
}

function OilTankMerge() {
  return (
    <div className="oil-tank-merge" aria-hidden="true">
      <svg viewBox="0 0 70 300" preserveAspectRatio="none">
        <defs>
          <marker id="oil-merge-arrow" markerHeight="6" markerWidth="6" orient="auto" refX="5" refY="3">
            <path d="M0 0 L6 3 L0 6 Z" />
          </marker>
        </defs>
        <path d="M3 55 C28 55 26 150 45 150" />
        <path d="M3 115 C28 115 26 150 45 150" />
        <path d="M3 185 C28 185 26 150 45 150" />
        <path d="M3 245 C28 245 26 150 45 150" />
        <path d="M45 150 H67" markerEnd="url(#oil-merge-arrow)" />
        <circle cx="3" cy="55" r="3" />
        <circle cx="3" cy="115" r="3" />
        <circle cx="3" cy="185" r="3" />
        <circle cx="3" cy="245" r="3" />
      </svg>
    </div>
  )
}

function ProcessDetails({ nodeId }) {
  const node = useContext(FlowNodesContext)[nodeId]

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
          <dt>{node.throughputLabel || 'Пропускная способность'}</dt>
          <dd>{node.throughput}</dd>
        </div>
        {node.metrics.map(([label, value]) => (
          <div key={label}>
            <dt>{label}</dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>
      <p className="process-data-note">{node.isLive ? 'Актуальные данные производственного учёта' : 'Демонстрационные данные · узел подготовлен для подключения к API'}</p>
    </aside>
  )
}

export function OverviewPage({ onLogout, token, user }) {
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
    if (!overviewData) {
      return FLOW_NODES
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
      ...FLOW_NODES,
      reception: {
        ...FLOW_NODES.reception,
        status: reception.open_receipt_count > 0 ? 'Прием идет' : 'Нет активных приемов',
        statusTone: reception.open_receipt_count > 0 ? 'running' : 'ready',
        currentFlow: formatLiveVolume(reception.accepted_today_liters),
        throughput: `${reception.completed_today_count} завершено`,
        capacityCaption: 'сегодня',
        throughputLabel: 'Завершено сегодня',
        metrics: [
          ['Принято сегодня', formatLiveVolume(reception.accepted_today_liters)],
          ['Открытых приемов', String(reception.open_receipt_count)],
          ['Средний прием', formatLiveVolume(reception.average_receipt_liters)],
        ],
        isLive: true,
      },
      storageTank: {
        ...FLOW_NODES.storageTank,
        name: tanks.active_count === 1 ? 'Приемный бак' : 'Приемные баки',
        status: Number(tanks.current_volume_liters) > 0 ? 'Накапливается' : 'Пусто',
        statusTone: Number(tanks.current_volume_liters) > 0 ? 'running' : 'ready',
        currentFlow: formatLiveVolume(tanks.current_volume_liters),
        throughput: formatLiveVolume(tanks.capacity_liters),
        capacityCaption: 'вместимость',
        throughputLabel: 'Общая вместимость',
        metrics: [
          ['Текущий объем', formatLiveVolume(tanks.current_volume_liters)],
          ['Свободно', formatLiveVolume(tanks.free_volume_liters)],
          ['Заполнение', `${tanks.fill_percentage}%`],
          ['Активных баков', String(tanks.active_count)],
          ['Последнее движение', formatLiveDateTime(tanks.last_movement_at)],
        ],
        isLive: true,
      },
      preheater: {
        ...FLOW_NODES.preheater,
        name: boilers.active_count === 1 ? 'Котел первичного прогрева' : 'Котлы первичного прогрева',
        status: Number(boilers.current_volume_liters) > 0 ? 'Загружен' : 'Ожидает загрузки',
        statusTone: Number(boilers.current_volume_liters) > 0 ? 'running' : 'ready',
        currentFlow: formatLiveVolume(boilers.current_volume_liters),
        throughput: formatLiveVolume(boilers.capacity_liters),
        capacityCaption: 'вместимость',
        throughputLabel: 'Общая вместимость',
        metrics: [
          ['Текущий объем', formatLiveVolume(boilers.current_volume_liters)],
          ['Свободно', formatLiveVolume(boilers.free_volume_liters)],
          ['Заполнение', `${boilers.fill_percentage}%`],
          ['Активных котлов', String(boilers.active_count)],
          ['Последняя загрузка', formatLiveDateTime(boilers.last_loading_at)],
        ],
        isLive: true,
      },
      separator: {
        ...FLOW_NODES.separator,
        name: separators.active_count === 1 ? 'Сепаратор' : 'Сепараторы',
        status: Number(separators.current_volume_liters) > 0 ? 'Загружен' : 'Ожидает загрузки',
        statusTone: Number(separators.current_volume_liters) > 0 ? 'running' : 'ready',
        currentFlow: formatLiveVolume(separators.current_volume_liters),
        throughput: formatLiveVolume(separators.capacity_liters),
        capacityCaption: 'вместимость',
        throughputLabel: 'Общая вместимость',
        metrics: [
          ['Текущий объем', formatLiveVolume(separators.current_volume_liters)],
          ['Свободно', formatLiveVolume(separators.free_volume_liters)],
          ['Заполнение', `${separators.fill_percentage}%`],
          ['Активных сепараторов', String(separators.active_count)],
          ['Последняя загрузка', formatLiveDateTime(separators.last_loading_at)],
        ],
        isLive: true,
      },
      chemicalMixer1: buildOverviewContainerNode(FLOW_NODES.chemicalMixer1, chemicalMixers[0], 'Химический миксер №1'),
      chemicalMixer2: buildOverviewContainerNode(FLOW_NODES.chemicalMixer2, chemicalMixers[1], 'Химический миксер №2'),
      workshop1: buildOverviewContainerNode(FLOW_NODES.workshop1, processingWorkshops[0], 'Цех переработки №1'),
      workshop2: buildOverviewContainerNode(FLOW_NODES.workshop2, processingWorkshops[1], 'Цех переработки №2'),
      rawDieselTank: buildOverviewTankSummaryNode(FLOW_NODES.rawDieselTank, rawDieselTanks, 'Бак сырой солярки', 'Баки сырой солярки'),
      rawSpindleTank: buildOverviewTankSummaryNode(FLOW_NODES.rawSpindleTank, rawSpindleTanks, 'Бак сырой веретенки', 'Баки сырой веретенки'),
    }
  }, [overviewData])

  const selectTab = (tabId) => {
    setActiveTab(tabId)
    setSelectedNodeIdState(tabId === 'recycling' ? 'reception' : 'finishedSpindleTank')
    setDetailsNodeId(null)
  }

  const setSelectedNodeId = (nodeId) => {
    setSelectedNodeIdState(nodeId)
    setDetailsNodeId(nodeId)
  }

  return (
    <DashboardShell title="Обзор производства" onLogout={onLogout} user={user}>
      <FlowNodesContext.Provider value={flowNodes}>
      <section className="process-overview">
        <div className="process-tabs" role="tablist" aria-label="Производственные схемы">
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === 'recycling'}
            aria-controls="recycling-process-panel"
            className={activeTab === 'recycling' ? 'process-tab process-tab--active' : 'process-tab'}
            onClick={() => selectTab('recycling')}
          >
            Переработка отработанного масла
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === 'oil-production'}
            aria-controls="oil-production-panel"
            className={activeTab === 'oil-production' ? 'process-tab process-tab--active' : 'process-tab'}
            onClick={() => selectTab('oil-production')}
          >
            Производство масла
          </button>
        </div>

        {activeTab === 'recycling' && (
          <div id="recycling-process-panel" role="tabpanel">
            <header className="process-overview-header">
              <div>
                <p className="auth-eyebrow">Технологическая линия</p>
                <h1>Переработка отработанного масла</h1>
                <p>Реальный учёт подключён к этапам от приёма до баков сырой продукции; последующие узлы пока остаются демонстрационными.</p>
              </div>
              <div className="process-summary">
                <span><i className="summary-indicator" />Учёт подключён</span>
                <strong>{overviewData ? formatLiveVolume(overviewData.reception.accepted_today_liters) : 'Загрузка...'}</strong>
                <small>принято сегодня</small>
              </div>
            </header>

            {overviewError && <p className="process-live-error">Не удалось обновить реальные показатели: {overviewError}</p>}

            <div className="process-legend" aria-label="Легенда схемы">
              <span><i className="legend-line legend-line--product" />Основной продукт</span>
              <span><i className="legend-line legend-line--water" />Вода</span>
              <span><i className="legend-line legend-line--waste" />Мусор</span>
              <span><i className="legend-line legend-line--sorbent" />Сорбент</span>
              <span><i className="legend-status legend-status--running" />В работе</span>
              <span><i className="legend-status legend-status--ready" />Готов / ожидает</span>
              <small>Все объемы указаны в литрах</small>
            </div>

            <div className="process-scroll-hint">
              <span>Нажмите на этап, чтобы посмотреть показатели</span>
              <span>Направление потока показано змейкой ↓</span>
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
              <span>↔ замкнутый контур сорбента</span>
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
          <header className="oil-production-header">
            <div>
              <p className="auth-eyebrow">Дополнительная производственная линия</p>
              <h2>Производство масел</h2>
              <p>Изготовление товарных масел из готовой веретенки, концентрата и пакетов присадок.</p>
            </div>
            <div className="oil-production-summary">
              <span><i />Блендинг выполняется</span>
              <strong>7 850 л</strong>
              <small>в работе на трех смесителях</small>
            </div>
          </header>

          <div className="oil-production-legend">
            <span><i className="legend-line legend-line--product" />Веретенка и концентрат</span>
            <span><i className="legend-line legend-line--material" />Загуститель и присадки</span>
            <span><i className="legend-line legend-line--oil" />Готовые масла</span>
            <small>Жидкие продукты — литры, твердые компоненты — килограммы</small>
          </div>

          <div className="oil-production-map">
            <div className="oil-stage oil-preparation-stage">
              <span className="oil-stage-title">Приготовление концентрата</span>
              <div className="oil-preparation-inputs">
                <ProcessNode compact nodeId="finishedSpindleTank" selectedNodeId={selectedNodeId} onSelect={setSelectedNodeId} />
                <ProcessNode compact nodeId="polypropyleneFeed" selectedNodeId={selectedNodeId} onSelect={setSelectedNodeId} />
              </div>
              <div className="oil-input-merge" aria-hidden="true"><i /><i /><b /></div>
              <ProcessNode compact nodeId="concentrateReactor" selectedNodeId={selectedNodeId} onSelect={setSelectedNodeId} />
            </div>

            <FlowArrow />

            <div className="oil-stage oil-blending-stage">
              <span className="oil-stage-title">Блендинговые смесители</span>
              <div className="oil-blending-feeds">
                <ProcessOutlet nodeId="finishedSpindleTank" selectedNodeId={selectedNodeId} onSelect={setSelectedNodeId} />
                <ProcessOutlet nodeId="additiveStation" selectedNodeId={selectedNodeId} onSelect={setSelectedNodeId} />
              </div>
              <div className="oil-blenders">
                {['blender1', 'blender2', 'blender3'].map((nodeId) => (
                  <ProcessNode compact key={nodeId} nodeId={nodeId} selectedNodeId={selectedNodeId} onSelect={setSelectedNodeId} />
                ))}
              </div>
            </div>

            <OilRoutingMatrix />

            <div className="oil-stage oil-product-tanks">
              <span className="oil-stage-title">Баки готовых масел</span>
              <div>
                {['transmissionOilTank', 'hydraulicOilTank', 'industrialOilTank', 'motorOilTank'].map((nodeId) => (
                  <ProcessNode compact key={nodeId} nodeId={nodeId} selectedNodeId={selectedNodeId} onSelect={setSelectedNodeId} />
                ))}
              </div>
            </div>

            <OilTankMerge />

            <div className="oil-stage oil-filling-stage">
              <span className="oil-stage-title">Общий розлив</span>
              <ProcessNode compact nodeId="fillingLine" selectedNodeId={selectedNodeId} onSelect={setSelectedNodeId} />
            </div>
          </div>
        </section>
        )}

        {detailsNodeId && (
          <Modal title="Информация об этапе" onClose={() => setDetailsNodeId(null)}>
            <ProcessDetails nodeId={detailsNodeId} />
          </Modal>
        )}
      </section>
      </FlowNodesContext.Provider>
    </DashboardShell>
  )
}
