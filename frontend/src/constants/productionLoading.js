export const bentoniteLoadingTarget = 'bentonite_filter'
export const bentoniteLoadingPath = '/processing/bentonite-loading'

export const productionMaterialOptions = [
  { code: '', label: 'Не используется в производственной загрузке' },
  { code: 'granules', label: 'Гранулы' },
  { code: 'dye', label: 'Краситель' },
  { code: 'polypropylene', label: 'Полипропилен' },
  { code: 'bentonite', label: 'Бентонит' },
]

export const productionLoadingConfig = {
  canisters: { title: 'Загрузка производства канистр', moduleCode: 'canister-loading' },
  caps: { title: 'Загрузка производства крышек', moduleCode: 'cap-loading' },
  [bentoniteLoadingTarget]: { title: 'Загрузка бентонита', moduleCode: 'bentonite-loading' },
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
