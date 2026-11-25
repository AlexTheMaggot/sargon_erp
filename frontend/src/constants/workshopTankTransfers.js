export const workshopTankTransfers = [
  {
    kind: 'raw_diesel_tank', path: '/processing/raw-diesel-tank-loading', moduleCode: 'raw-diesel-tank-loading',
    endpoint: 'workshop-to-raw-diesel-tank', movementType: 'receiver_to_raw_diesel_tank', receiver: true,
    label: 'Слив солярки из ресивера', tankLabel: 'Бак сырой солярки', productName: 'Сырая солярка',
    description: 'Полностью слить ресивер №1 в бак сырой солярки.',
  },
  {
    kind: 'raw_spindle_tank', path: '/processing/raw-spindle-tank-loading', moduleCode: 'raw-spindle-tank-loading',
    endpoint: 'workshop-to-raw-spindle-tank', movementType: 'receiver_to_raw_spindle_tank', receiver: true,
    label: 'Слив веретенки из ресивера', tankLabel: 'Бак сырой веретенки', productName: 'Сырая веретенка',
    description: 'Полностью слить выбранный ресивер №2, №3 или №4 в бак сырой веретенки.',
  },
  {
    kind: 'nigrol_tank', path: '/processing/nigrol-loading', moduleCode: 'nigrol-loading',
    endpoint: 'workshop-to-nigrol-tank', movementType: 'reactor_to_nigrol_tank',
    label: 'Отгрузка нигрола', tankLabel: 'Бак нигрола', productName: 'Нигрол',
    description: 'Отгрузить нигрол напрямую из реактора в отдельный бак.',
  },
]
