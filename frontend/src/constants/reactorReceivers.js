export const receiverModule = 'reactor-receivers'
export const receiverPath = '/processing/reactor-receivers'
export const receiverApi = '/api/processing/receiver-runs/'

export const receiverStatuses = {
  open: 'Открыт',
  waiting: 'Готов к сливу',
  drained: 'Пуст',
}

export const receiverProduct = (number) => number === 1 ? 'Сырая солярка' : 'Сырая веретенка'
