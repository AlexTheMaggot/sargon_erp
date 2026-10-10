import { uzMessages, uzMonths } from './uz.js'
import { ruMessages } from './ru.js'

export const LANGUAGE_STORAGE_KEY = 'shenoll_language'
export const languages = [
  { code: 'ru', label: 'Русский', locale: 'ru-RU' },
  { code: 'uz', label: 'O‘zbekcha', locale: 'uz-Latn-UZ' },
]

const listeners = new Set()
let language = readSavedLanguage()
const templateCache = new Map()
const reverseUzMessages = Object.fromEntries(Object.entries(uzMessages).map(([source, translated]) => [translated, source]))
const uzQuantityUnits = { 'л/ч': 'l/soat', 'кг/ч': 'kg/soat', 'л': 'l', 'кг': 'kg', 'мин': 'daq', 'смены': 'smena', 'бар': 'bar' }
const ruQuantityUnits = Object.fromEntries(Object.entries(uzQuantityUnits).map(([source, translated]) => [translated, source]))

function readSavedLanguage() {
  try {
    return globalThis.localStorage?.getItem(LANGUAGE_STORAGE_KEY) === 'uz' ? 'uz' : 'ru'
  } catch {
    return 'ru'
  }
}

export function getLanguage() {
  return language
}

export function getLocale() {
  return languages.find((item) => item.code === language).locale
}

export function subscribeLanguage(listener) {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

export function setLanguage(nextLanguage) {
  if (!languages.some((item) => item.code === nextLanguage)) return
  try {
    globalThis.localStorage?.setItem(LANGUAGE_STORAGE_KEY, nextLanguage)
  } catch {
    applyLanguage(nextLanguage)
    return
  }
  applyLanguage(nextLanguage)
}

function applyLanguage(nextLanguage) {
  if (typeof document !== 'undefined') document.documentElement.lang = nextLanguage === 'uz' ? 'uz-Latn' : 'ru'
  if (language === nextLanguage) return
  language = nextLanguage
  listeners.forEach((listener) => listener())
}

function templatePattern(source) {
  if (!templateCache.has(source)) {
    const pieces = source.split(/(\{\d+\})/)
    const indexes = []
    const pattern = pieces.map((piece) => {
      if (/^\{\d+\}$/.test(piece)) {
        indexes.push(Number(piece.slice(1, -1)))
        return '(.*?)'
      }
      return piece.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
    }).join('')
    templateCache.set(source, { pattern: new RegExp(`^${pattern}$`, 's'), indexes })
  }
  return templateCache.get(source)
}

function translateSource(source, messages) {
  if (Object.hasOwn(messages, source)) return messages[source]
  const units = messages === uzMessages ? uzQuantityUnits : messages === reverseUzMessages ? ruQuantityUnits : null
  const quantity = units ? source.match(/^(\d[\d\s,.]*) (\S+)$/) : null
  if (quantity && Object.hasOwn(units, quantity[2])) return `${quantity[1]} ${units[quantity[2]]}`
  for (const [template, translation] of Object.entries(messages)) {
    if (!/\{\d+\}/.test(template)) continue
    const { pattern, indexes } = templatePattern(template)
    const match = source.match(pattern)
    if (match) {
      const captures = Object.fromEntries(indexes.map((index, position) => [index, match[position + 1]]))
      return translation.replace(/\{(\d+)\}/g, (_, index) => translateSource(captures[index] ?? '', messages))
    }
  }
  return source
}

function translate(message, values, selectedLanguage) {
  const isTemplate = Array.isArray(message) && Object.hasOwn(message, 'raw')
  const source = isTemplate
    ? message.map((piece, index) => piece + (index < values.length ? `{${index}}` : '')).join('')
    : String(message ?? '')
  const trimmed = source.trim()
  const messages = selectedLanguage === 'uz' ? uzMessages : ruMessages
  const canonical = selectedLanguage === 'ru' ? translateSource(trimmed, reverseUzMessages) : trimmed
  const translated = translateSource(canonical, messages)
  const result = isTemplate
    ? translated.replace(/\{(\d+)\}/g, (_, index) => String(values[Number(index)] ?? ''))
    : translated
  return source.slice(0, source.indexOf(trimmed)) + result + source.slice(source.indexOf(trimmed) + trimmed.length)
}

export function t(message, ...values) {
  return translate(message, values, language)
}

export function localizeStaticData(value, selectedLanguage = language) {
  if (typeof value === 'string') return translate(value, [], selectedLanguage)
  if (Array.isArray(value)) return value.map((item) => localizeStaticData(item, selectedLanguage))
  if (value && typeof value === 'object') {
    return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, localizeStaticData(item, selectedLanguage)]))
  }
  return value
}

export function formatNumber(value, options = {}) {
  return new Intl.NumberFormat(getLocale(), options).format(Number(value))
}

export function formatLongDate(value) {
  const date = new Date(value)
  if (language === 'ru') return new Intl.DateTimeFormat(getLocale(), { day: 'numeric', month: 'long', year: 'numeric' }).format(date)
  const parts = Object.fromEntries(new Intl.DateTimeFormat('en', { day: 'numeric', month: 'numeric', year: 'numeric' }).formatToParts(date).map((part) => [part.type, part.value]))
  return `${parts.day}-${uzMonths[Number(parts.month) - 1]}, ${parts.year}`
}

applyLanguage(language)
if (typeof window !== 'undefined') {
  window.addEventListener('storage', (event) => {
    if (event.key === LANGUAGE_STORAGE_KEY || event.key === null) applyLanguage(readSavedLanguage())
  })
}
