import { oilContainerConfig } from './oilFinishing'
import { oilOperations, packagingOperations, recyclingOperations } from './productionWorkspace'

export const navItems = [
  { path: '/welcome', label: 'Обзор', moduleCode: 'dashboard' },
  { path: '/production', label: 'Производство', moduleCode: 'production-workspace' },
  { path: '/knowledge', label: 'База знаний', moduleCode: 'knowledge-base' },
  {
    label: 'Переработка',
    children: [
      { path: '/raw-material/receipts', label: 'Прием сырья', moduleCode: 'raw-material-receiving' },
      { path: '/laboratory/analyses', label: 'Лабораторный анализ', moduleCode: 'laboratory-analysis' },
      ...recyclingOperations,
    ],
  },
  {
    label: 'Производство канистр',
    children: packagingOperations,
  },
  {
    label: 'Производство масел',
    children: oilOperations,
  },
  {
    label: 'Склад',
    children: [
      { path: '/warehouse/overview', label: 'Остатки', moduleCode: 'warehouse-accounting' },
      { path: '/warehouse/receipts', label: 'Поступления', moduleCode: 'warehouse-accounting' },
      { path: '/warehouse/issues', label: 'Внутренний расход', moduleCode: 'warehouse-accounting' },
      { path: '/warehouse/transfers', label: 'Перемещения', moduleCode: 'warehouse-accounting' },
      { path: '/warehouse/inventory', label: 'Инвентаризация', moduleCode: 'warehouse-accounting' },
    ],
  },
  {
    label: 'Настройки склада',
    children: [
      { path: '/warehouse/settings/items', label: 'Номенклатура', moduleCode: 'warehouse-settings' },
      { path: '/warehouse/settings/categories', label: 'Категории товаров', moduleCode: 'warehouse-settings' },
      { path: '/warehouse/settings/units', label: 'Единицы измерения', moduleCode: 'warehouse-settings' },
      { path: '/warehouse/settings/warehouses', label: 'Склады', moduleCode: 'warehouse-settings' },
    ],
  },
  {
    label: 'Прочее',
    children: [
      { path: '/processing/receiving-tanks', label: 'Приёмные баки', moduleCode: 'used-oil-processing' },
      { path: '/processing/preheating-boilers', label: 'Котлы первичного прогрева', moduleCode: 'used-oil-processing' },
      { path: '/processing/separators', label: 'Сепараторы', moduleCode: 'used-oil-processing' },
      { path: '/processing/chemical-mixers', label: 'Химические миксеры', moduleCode: 'used-oil-processing' },
      { path: '/processing/workshops', label: 'Цеха переработки', moduleCode: 'used-oil-processing' },
      { path: '/processing/raw-diesel-tanks', label: 'Баки сырой солярки', moduleCode: 'used-oil-processing' },
      { path: '/processing/raw-spindle-tanks', label: 'Баки сырой веретенки', moduleCode: 'used-oil-processing' },
      ...Object.values(oilContainerConfig).map((config) => ({ path: `/processing/${config.path}`, label: config.title, moduleCode: 'used-oil-processing' })),
      { path: '/oil-production/grades', label: 'Марки масел', moduleCode: 'used-oil-processing' },
      { path: '/processing/journal', label: 'Журнал операций', adminOnly: true },
    ],
  },
  {
    label: 'Справочник',
    children: [
      { path: '/directories/cities', label: 'Города', moduleCode: 'access' },
      { path: '/directories/suppliers', label: 'Поставщики', moduleCode: 'suppliers' },
    ],
  },
  {
    label: 'Доступ',
    moduleCode: 'access',
    children: [
      { path: '/access/users', label: 'Пользователи', moduleCode: 'access' },
      { path: '/access/groups', label: 'Группы', moduleCode: 'access' },
      { path: '/access/modules', label: 'Модули', moduleCode: 'access' },
      { path: '/access/permissions', label: 'Разрешения', moduleCode: 'access' },
    ],
  },
]
