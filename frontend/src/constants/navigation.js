export const navItems = [
  { path: '/welcome', label: 'Обзор' },
  { path: '/raw-material/receipts', label: 'Прием сырья', moduleCode: 'raw-material-receiving' },
  { path: '/laboratory/analyses', label: 'Лабораторный анализ', moduleCode: 'laboratory-analysis' },
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
