export const oilContainerConfig = {
  concentrate_reactor: { path: 'concentrate-reactors', title: 'Реакторы концентрата', manufacturing: true },
  oil_blender: { path: 'oil-blenders', title: 'Блендинговые смесители', manufacturing: true },
  finished_oil_tank: { path: 'finished-oil-tanks', title: 'Баки товарных масел', manufacturing: true },
  finishing_mixer: { path: 'finishing-mixers', title: 'Песочные миксеры' },
  finishing_filter: { path: 'finishing-filters', title: 'Финишные фильтры' },
  finished_diesel_tank: { path: 'finished-diesel-tanks', title: 'Баки готовой солярки' },
  finished_spindle_tank: { path: 'finished-spindle-tanks', title: 'Баки готовой веретенки' },
}

export const oilFinishingForms = {
  'chemical-mixer-loading': {
    title: 'Загрузка химического миксера',
    sources: ['raw_diesel_tank', 'raw_spindle_tank'], destinations: ['chemical_mixer'], movementType: 'raw_to_chemical_mixer',
  },
  'finishing-mixer-loading': {
    title: 'Загрузка песочного миксера',
    sources: ['chemical_mixer'], destinations: ['finishing_mixer'], movementType: 'chemical_to_finishing_mixer',
  },
  'finished-product-loading': {
    title: 'Перелив через финишный фильтр',
    sources: ['finishing_mixer'], destinations: ['finished_diesel_tank', 'finished_spindle_tank'], movementType: 'mixer_to_finished_tank',
    viaFilter: true,
  },
}

export function oilContainerApiPath(kind) {
  if (kind === 'chemical_mixer') return '/api/processing/chemical-mixers/'
  if (kind === 'raw_diesel_tank') return '/api/processing/raw-diesel-tanks/'
  if (kind === 'raw_spindle_tank') return '/api/processing/raw-spindle-tanks/'
  const prefix = oilContainerConfig[kind].manufacturing ? '/api/oil-production/containers' : '/api/processing/oil-containers'
  return `${prefix}/${oilContainerConfig[kind].path}/`
}
