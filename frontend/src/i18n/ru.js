import { serverMessages } from './serverMessages.js'
import { systemMessages } from './systemMessages.js'

export const ruMessages = {
  ...Object.fromEntries(Object.entries(systemMessages).map(([source, translations]) => [source, translations[0]])),
  ...Object.fromEntries(Object.entries(serverMessages).map(([source, translations]) => [source, translations[0]])),
  'Failed to fetch': 'Не удалось связаться с сервером.',
  'NetworkError when attempting to fetch resource.': 'Ошибка сети при получении данных.',
}
