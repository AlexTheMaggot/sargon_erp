import { oilFinishingForms } from './oilFinishing.js'
import { oilManufacturingConfig } from './oilManufacturing.js'
import { workshopTankTransfers } from './workshopTankTransfers.js'
import { receiverModule, receiverPath } from './reactorReceivers.js'
import { chemicalMixerDischarges } from './chemicalMixerDischarges.js'
import { bentoniteLoadingPath, bentoniteLoadingTarget, chemicalMixerReagents, productionLoadingConfig } from './productionLoading.js'

function oilTransferOperation(moduleCode, group, icon, description) {
  return {
    path: `/processing/${moduleCode}`, label: oilFinishingForms[moduleCode].title, moduleCode,
    group, icon, description,
  }
}

export const recyclingOperations = [
  { path: '/processing/boiler-loading', label: 'Загрузка котла отработки', moduleCode: 'boiler-loading', group: 'preparation', icon: 'boiler', description: 'Передать масло из приёмного бака в котёл прогрева.' },
  { path: '/processing/workshop-loading', label: 'Загрузка реактора переработки', moduleCode: 'workshop-loading', group: 'reactor', icon: 'factory', description: 'Передать прогретое масло из котла в реактор переработки.' },
  { path: receiverPath, label: 'Ресиверы реактора', moduleCode: receiverModule, group: 'receivers', icon: 'tank', description: 'Отметить открытие и закрытие ресиверов и перейти к сливу.' },
  ...workshopTankTransfers.map((operation) => ({ ...operation, group: operation.receiver ? 'receivers' : 'reactor', icon: 'tank' })),
  { ...chemicalMixerReagents, label: chemicalMixerReagents.title, group: 'chemical', icon: 'supply',
    description: 'Раздельное списание кислоты и бентонита в химический миксер.' },
  oilTransferOperation('chemical-mixer-loading', 'chemical', 'mixer', 'Передать сырую солярку или веретенку из бака в химический миксер.'),
  { ...chemicalMixerDischarges, group: 'chemical', icon: 'tank' },
  oilTransferOperation('finishing-mixer-loading', 'finishing', 'mixer', 'Передать масло из химического миксера в песочный миксер.'),
  oilTransferOperation('finished-product-loading', 'finishing', 'tank', 'Перелить масло из песочного миксера в готовый бак через общий фильтр.'),
  { path: bentoniteLoadingPath, label: productionLoadingConfig[bentoniteLoadingTarget].title,
    moduleCode: productionLoadingConfig[bentoniteLoadingTarget].moduleCode, group: 'finishing', icon: 'filter',
    description: 'Списать бентонит со склада и записать загрузку финишного фильтра.' },
]

export const oilOperations = Object.entries(oilManufacturingConfig).map(([code, config]) => ({
  path: `/oil-production/${code}`, label: config.title, moduleCode: code, group: 'oil',
  ...({
    'concentrate-loading': { icon: 'boiler', description: 'Загрузить веретенку и складской полипропилен в реактор.' },
    'oil-blending': { icon: 'mixer', description: 'Соединить основу и концентрат для выбранной марки масла.' },
    'oil-tank-loading': { icon: 'tank', description: 'Зафиксировать фактический перелив масла в бак нужной марки.' },
    'oil-filling': { icon: 'filling', description: 'Зарегистрировать розлив готового масла в литрах.' },
  })[code],
}))

export const packagingOperations = [
  { path: '/production/canister-loading', label: 'Загрузка производства канистр', moduleCode: 'canister-loading', group: 'canisters', icon: 'supply', description: 'Передать гранулы и краситель со склада на линию канистр.' },
  { path: '/production/canister-output', label: 'Выпуск канистр', moduleCode: 'canister-output', group: 'canisters', icon: 'canister', description: 'Записать годные канистры, отклонения и брак.' },
  { path: '/production/cap-loading', label: 'Загрузка производства крышек', moduleCode: 'cap-loading', group: 'caps', icon: 'supply', description: 'Передать гранулы и краситель со склада на линию крышек.' },
  { path: '/production/cap-output', label: 'Выпуск крышек', moduleCode: 'cap-output', group: 'caps', icon: 'cap', description: 'Записать годные крышки и брак.' },
]

export const productionSections = [
  { id: 'recycling', title: 'Переработка масла', icon: 'cycle', tone: 'emerald', description: 'Прогрев, разделение, переработка и очистка масла.', operations: recyclingOperations,
    groups: [
      { id: 'preparation', title: 'Подготовка сырья' },
      { id: 'reactor', title: 'Реактор' },
      { id: 'receivers', title: 'Ресиверы' },
      { id: 'chemical', title: 'Химический миксер' },
      { id: 'finishing', title: 'Финишная очистка' },
    ] },
  { id: 'oils', title: 'Производство масла', icon: 'oil', tone: 'teal', description: 'Приготовление концентрата, смешивание, продуктовые баки и розлив.', operations: oilOperations,
    groups: [{ id: 'oil', title: 'Операции с товарным маслом' }] },
  { id: 'packaging', title: 'Производство канистр', icon: 'canister', tone: 'gold', description: 'Две отдельные линии: канистры и крышки. Загрузка материалов и регистрация выпуска.', operations: packagingOperations,
    groups: [{ id: 'canisters', title: 'Канистры' }, { id: 'caps', title: 'Крышки' }] },
]

export function canViewProductionOperation(user, operation) {
  return Boolean(user?.is_admin || user?.access?.[operation.moduleCode]?.includes('view'))
}

export function usesProductionWorkspace(user) {
  return Boolean(!user?.is_admin && user?.access?.['production-workspace']?.includes('view'))
}

export function productionSectionForPath(path) {
  return productionSections.find((section) => section.operations.some((operation) => operation.path === path))
}
