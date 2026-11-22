import { oilFinishingForms } from './oilFinishing.js'
import { oilManufacturingConfig } from './oilManufacturing.js'

export const recyclingOperations = [
  { path: '/processing/boiler-loading', label: 'Загрузка котла отработки', moduleCode: 'boiler-loading', group: 'preparation', icon: 'boiler', description: 'Передать масло из приёмного бака в котёл прогрева.' },
  { path: '/processing/workshop-loading', label: 'Загрузка в цех переработки', moduleCode: 'workshop-loading', group: 'processing', icon: 'factory', description: 'Передать прогретое масло из котла в цех переработки.' },
  { path: '/processing/raw-diesel-tank-loading', label: 'Загрузка бака сырой солярки', moduleCode: 'raw-diesel-tank-loading', group: 'processing', icon: 'tank', description: 'Перелить сырую солярку из цеха в отдельный бак.' },
  { path: '/processing/raw-spindle-tank-loading', label: 'Загрузка бака сырой веретенки', moduleCode: 'raw-spindle-tank-loading', group: 'processing', icon: 'tank', description: 'Перелить сырую веретенку из цеха в отдельный бак.' },
  ...Object.entries(oilFinishingForms).map(([code, config]) => ({
    path: `/processing/${code}`, label: config.title, moduleCode: code, group: 'finishing',
    ...({
      'chemical-mixer-loading': { icon: 'mixer', description: 'Передать сырую солярку или веретенку из бака в химический миксер.' },
      'finishing-mixer-loading': { icon: 'mixer', description: 'Передать масло из химического миксера в песочный миксер.' },
      'finishing-filter-loading': { icon: 'filter', description: 'Передать масло из песочного миксера на фильтрацию.' },
      'finished-product-loading': { icon: 'tank', description: 'Заполнить бак готовой солярки или веретенки после фильтра.' },
    })[code],
  })),
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
    groups: [{ id: 'preparation', title: 'Подготовка сырья' }, { id: 'processing', title: 'Основная переработка' }, { id: 'finishing', title: 'Финишная очистка' }] },
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
