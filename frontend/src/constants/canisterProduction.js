function createNode({ name, shortName, stage, description, unit = 'кг', tone = 'material', metrics = [] }) {
  return {
    name,
    shortName,
    stage,
    description,
    status: 'Схема',
    statusTone: tone,
    currentFlow: '—',
    throughput: unit,
    capacityCaption: 'Единица учёта:',
    throughputLabel: 'Единица учёта',
    metrics,
    dataNote: 'Схема этапа · производственный и складской учёт пока не подключены',
    isLive: false,
  }
}

const granulesConfig = {
  name: 'Гранулы ПЭТ', shortName: 'ГР', stage: 'Сырьё',
  description: 'Первичные гранулы для формования продукции. Учёт сырья — в килограммах.',
}

export const CANISTER_FLOW_NODES = {
  canisterGranules: createNode(granulesConfig),
  capGranules: createNode(granulesConfig),
  canisterDyes: createNode({
    name: 'Красители канистр', shortName: 'КР', stage: 'Отдельные позиции',
    description: 'Красители учитываются отдельными позициями. Для выпуска канистр выбирается конкретный краситель.',
    metrics: [['Номенклатура', 'Отдельные позиции красителей']],
  }),
  canisterRegrind: createNode({
    name: 'Вторсырьё канистр', shortName: 'ВК', stage: 'Раздельное сырьё', tone: 'ready',
    description: 'Поставляемое вторсырьё для канистр и материал после измельчения собственного брака канистр. Вторсырьё крышек сюда не поступает.',
    metrics: [['Поступление материала', 'Поставки и измельчение своего брака'], ['Назначение материала', 'Только канистры']],
  }),
  canisterForming: createNode({
    name: 'Формование канистр', shortName: 'ФК', stage: 'Производство', unit: 'шт.', tone: 'running',
    description: 'Гранулы, выбранный краситель и вторсырьё канистр поступают в производство. Сырьё учитывается в килограммах, выпуск — в штуках.',
    metrics: [['Результаты выпуска', 'Годные, отклонение и брак']],
  }),
  canisterStock: createNode({
    name: 'Годные канистры', shortName: 'ГК', stage: 'На склад', unit: 'шт.', tone: 'finished',
    description: 'Годные канистры поступают на склад как готовая продукция и затем расходуются со склада.',
    metrics: [['Складская позиция', 'Годные канистры']],
  }),
  canisterDeviation: createNode({
    name: 'Канистры с отклонениями', shortName: 'ОК', stage: 'Отдельная складская позиция', unit: 'шт.', tone: 'deviation',
    description: 'Самостоятельная складская позиция со своим остатком и расходом. Это не временный статус и не брак для измельчения.',
    metrics: [['Складская позиция', 'Канистры с отклонениями']],
  }),
  canisterRejects: createNode({
    name: 'Брак канистр', shortName: 'БК', stage: 'Ожидает измельчения', unit: 'шт.', tone: 'defect',
    description: 'Бракованные канистры учитываются отдельно до фактического измельчения. Появление брака само по себе не увеличивает остаток вторсырья.',
    metrics: [['Направление брака', 'Измельчение канистр']],
  }),
  canisterGrinding: createNode({
    name: 'Измельчение канистр', shortName: 'ИК', stage: 'Возврат материала', tone: 'ready',
    description: 'После фактического измельчения брака полученный материал учитывается в килограммах и возвращается только во вторсырьё канистр.',
    metrics: [['Получаемый материал', 'Вторсырьё канистр']],
  }),
  capDyes: createNode({
    name: 'Красители крышек', shortName: 'КР', stage: 'Отдельные позиции',
    description: 'Красители крышек учитываются отдельными позициями. При загрузке выбирается конкретный краситель, а не общий обезличенный материал.',
    metrics: [['Номенклатура', 'Отдельные позиции красителей']],
  }),
  capRegrind: createNode({
    name: 'Вторсырьё крышек', shortName: 'ВКР', stage: 'Раздельное сырьё', tone: 'ready',
    description: 'Поставляемое вторсырьё для крышек и материал после измельчения собственного брака крышек. Не смешивается со вторсырьём канистр.',
    metrics: [['Поступление материала', 'Поставки и измельчение своего брака'], ['Назначение материала', 'Только крышки']],
  }),
  capForming: createNode({
    name: 'Формование крышек', shortName: 'ФКР', stage: 'Производство', unit: 'шт.', tone: 'running',
    description: 'Используются гранулы, выбранный краситель и только вторсырьё крышек. На выходе — годные крышки или брак; категории отклонения нет.',
    metrics: [['Результаты выпуска', 'Годные и брак']],
  }),
  capStock: createNode({
    name: 'Годные крышки', shortName: 'ГКР', stage: 'На склад', unit: 'шт.', tone: 'finished',
    description: 'Годные крышки поступают на склад отдельной позицией готовой продукции и затем расходуются со склада.',
    metrics: [['Складская позиция', 'Годные крышки']],
  }),
  capRejects: createNode({
    name: 'Брак крышек', shortName: 'БКР', stage: 'Ожидает измельчения', unit: 'шт.', tone: 'defect',
    description: 'Бракованные крышки хранятся отдельно до измельчения и не поступают в контур вторсырья канистр.',
    metrics: [['Направление брака', 'Измельчение крышек']],
  }),
  capGrinding: createNode({
    name: 'Измельчение крышек', shortName: 'ИКР', stage: 'Возврат материала', tone: 'ready',
    description: 'Материал после фактического измельчения брака крышек возвращается только во вторсырьё крышек. Учёт результата — в килограммах.',
    metrics: [['Получаемый материал', 'Вторсырьё крышек']],
  }),
}

export const CANISTER_PRODUCTION_LINES = [
  {
    id: 'canisters',
    title: 'Линия канистр',
    description: 'Три результата выпуска: годные канистры, отдельная складская позиция с отклонениями и брак.',
    granulesId: 'canisterGranules',
    dyeId: 'canisterDyes',
    regrindId: 'canisterRegrind',
    productionId: 'canisterForming',
    outputIds: ['canisterStock', 'canisterDeviation', 'canisterRejects'],
    rejectId: 'canisterRejects',
    grinderId: 'canisterGrinding',
    returnLabel: 'Возврат только во вторсырьё канистр',
  },
  {
    id: 'caps',
    title: 'Линия крышек',
    description: 'Два результата выпуска: годные крышки и брак. Отклонение для крышек не предусмотрено.',
    granulesId: 'capGranules',
    dyeId: 'capDyes',
    regrindId: 'capRegrind',
    productionId: 'capForming',
    outputIds: ['capStock', 'capRejects'],
    rejectId: 'capRejects',
    grinderId: 'capGrinding',
    returnLabel: 'Возврат только во вторсырьё крышек',
  },
]
