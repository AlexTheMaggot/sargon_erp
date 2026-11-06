export const oilManufacturingConfig = {
  'concentrate-loading': { title: 'Приготовление концентрата', batch: true },
  'oil-blending': { title: 'Загрузка блендингового смесителя', batch: true },
  'oil-tank-loading': { title: 'Перелив масла в продуктовый бак', batch: false },
  'oil-filling': { title: 'Розлив товарного масла', batch: false },
}

export const oilManufacturingMovements = {
  spindle_to_concentrate: 'Загрузка реактора концентрата',
  spindle_to_blender: 'Загрузка основы в смеситель',
  concentrate_to_blender: 'Передача концентрата в смеситель',
  blender_to_oil_tank: 'Перелив товарного масла в бак',
  oil_filling: 'Розлив товарного масла',
}
