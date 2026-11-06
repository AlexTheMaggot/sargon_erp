export const oilContainerConfig = {
  concentrate_reactor: { path: 'concentrate-reactors', title: 'Реакторы концентрата', manufacturing: true },
  oil_blender: { path: 'oil-blenders', title: 'Блендинговые смесители', manufacturing: true },
  finished_oil_tank: { path: 'finished-oil-tanks', title: 'Баки товарных масел', manufacturing: true },
  sorption_system: { path: 'sorption-systems', title: 'Сорбент-системы' },
  finishing_mixer: { path: 'finishing-mixers', title: 'Финишные миксеры' },
  finishing_filter: { path: 'finishing-filters', title: 'Финишные фильтры' },
  finished_diesel_tank: { path: 'finished-diesel-tanks', title: 'Баки готовой солярки' },
  finished_spindle_tank: { path: 'finished-spindle-tanks', title: 'Баки готовой веретенки' },
}

export const oilFinishingForms = {
  'sorption-loading': {
    title: 'Загрузка масла в сорбент-систему',
    sources: ['raw_diesel_tank', 'raw_spindle_tank'],
    destinations: ['sorption_system'], movementType: 'raw_to_sorption',
  },
  'finishing-mixer-loading': {
    title: 'Загрузка финишного миксера',
    sources: ['sorption_system'], destinations: ['finishing_mixer'], movementType: 'sorption_to_mixer',
  },
  'finishing-filter-loading': {
    title: 'Загрузка финишного фильтра',
    sources: ['finishing_mixer'], destinations: ['finishing_filter'], movementType: 'mixer_to_filter',
  },
  'finished-product-loading': {
    title: 'Загрузка бака готовой продукции',
    sources: ['finishing_filter'], destinations: ['finished_diesel_tank', 'finished_spindle_tank'], movementType: 'filter_to_finished_tank',
  },
}

export function oilContainerApiPath(kind) {
  if (kind === 'raw_diesel_tank') return '/api/processing/raw-diesel-tanks/'
  if (kind === 'raw_spindle_tank') return '/api/processing/raw-spindle-tanks/'
  const prefix = oilContainerConfig[kind].manufacturing ? '/api/oil-production/containers' : '/api/processing/oil-containers'
  return `${prefix}/${oilContainerConfig[kind].path}/`
}
