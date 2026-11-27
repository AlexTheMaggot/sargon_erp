export const bentoniteLoadingTarget = 'bentonite_filter'
export const bentoniteLoadingPath = '/processing/bentonite-loading'
export const chemicalMixerReagents = {
  path: '/processing/chemical-mixer-reagents',
  moduleCode: 'chemical-mixer-reagents',
  title: 'Реагенты в химический миксер',
  targets: ['chemical_acid', 'chemical_bentonite'],
}

export const productionMaterialOptions = [
  { code: '', label: 'Не используется в производственной загрузке' },
  { code: 'granules', label: 'Гранулы' },
  { code: 'dye', label: 'Краситель' },
  { code: 'polypropylene', label: 'Полипропилен' },
  { code: 'bentonite', label: 'Бентонит' },
  { code: 'acid', label: 'Кислота' },
]

export const productionLoadingConfig = {
  canisters: { title: 'Загрузка производства канистр', moduleCode: 'canister-loading' },
  caps: { title: 'Загрузка производства крышек', moduleCode: 'cap-loading' },
  [bentoniteLoadingTarget]: { title: 'Загрузка бентонита', moduleCode: 'bentonite-loading' },
  chemical_acid: { title: 'Загрузка кислоты в химический миксер', reagent: 'Кислота', moduleCode: chemicalMixerReagents.moduleCode },
  chemical_bentonite: { title: 'Загрузка бентонита в химический миксер', reagent: 'Бентонит', moduleCode: chemicalMixerReagents.moduleCode },
}

export const productionProductOptions = [
  { code: '', label: 'Не является выпускаемой упаковкой' },
  { code: 'canisters', label: 'Канистры' },
  { code: 'caps', label: 'Крышки' },
]

export const productionOutputConfig = {
  canisters: { title: 'Выпуск канистр', moduleCode: 'canister-output' },
  caps: { title: 'Выпуск крышек', moduleCode: 'cap-output' },
}

export const outputDispositionOptions = [
  { code: 'good', label: 'Годные' },
  { code: 'deviation', label: 'С отклонениями' },
  { code: 'reject', label: 'Брак' },
]
