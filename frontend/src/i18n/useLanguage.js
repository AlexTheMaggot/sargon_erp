import { useSyncExternalStore } from 'react'
import { getLanguage, subscribeLanguage } from './core'

export function useLanguage() {
  return useSyncExternalStore(subscribeLanguage, getLanguage, () => 'ru')
}
