from django.db import migrations


WAREHOUSE_PERMISSIONS = (
    ('receipt', 'Поступление'),
    ('issue', 'Внутренний расход'),
    ('transfer', 'Перемещение'),
    ('transfer-confirm', 'Подтверждение перемещения'),
    ('inventory', 'Инвентаризация'),
)

WAREHOUSE_MODULES = (
    (
        'warehouse-accounting',
        'Складской учёт',
        'Поступление, расход, перемещение, инвентаризация и остатки.',
        '/warehouse/overview',
    ),
    (
        'warehouse-settings',
        'Настройки склада',
        'Склады, категории, единицы измерения и номенклатура.',
        '/warehouse/settings/items',
    ),
)


def seed_warehouse_accounting(apps, schema_editor):
    AccessGroup = apps.get_model('api', 'AccessGroup')
    GroupModuleAccess = apps.get_model('api', 'GroupModuleAccess')
    InventoryCategory = apps.get_model('api', 'InventoryCategory')
    Module = apps.get_model('api', 'Module')
    Permission = apps.get_model('api', 'Permission')
    UnitOfMeasure = apps.get_model('api', 'UnitOfMeasure')

    for name in ('Сырьё', 'Запчасти', 'Готовая продукция'):
        InventoryCategory.objects.update_or_create(name=name, defaults={'is_active': True})

    for name, symbol, decimal_places in (
        ('Штука', 'шт', 0),
        ('Килограмм', 'кг', 2),
        ('Литр', 'л', 2),
    ):
        UnitOfMeasure.objects.update_or_create(
            symbol=symbol,
            defaults={'name': name, 'decimal_places': decimal_places, 'is_active': True},
        )

    permissions = {}
    for code, name in WAREHOUSE_PERMISSIONS:
        permission, _ = Permission.objects.update_or_create(code=code, defaults={'name': name})
        permissions[code] = permission

    view_permission, _ = Permission.objects.update_or_create(code='view', defaults={'name': 'Просмотр'})
    standard_permissions = {}
    for code, name in (
        ('create', 'Создание'),
        ('update', 'Изменение'),
        ('delete', 'Удаление'),
    ):
        permission, _ = Permission.objects.update_or_create(code=code, defaults={'name': name})
        standard_permissions[code] = permission

    modules = {}
    for code, name, description, default_path in WAREHOUSE_MODULES:
        module, _ = Module.objects.update_or_create(
            code=code,
            defaults={
                'name': name,
                'description': description,
                'default_path': default_path,
                'is_active': True,
            },
        )
        modules[code] = module

    admin_group = AccessGroup.objects.filter(name='Администраторы').first()
    if admin_group:
        accounting_access, _ = GroupModuleAccess.objects.get_or_create(
            group=admin_group,
            module=modules['warehouse-accounting'],
        )
        accounting_access.permissions.set([view_permission, *permissions.values()])

        settings_access, _ = GroupModuleAccess.objects.get_or_create(
            group=admin_group,
            module=modules['warehouse-settings'],
        )
        settings_access.permissions.set([view_permission, *standard_permissions.values()])


def remove_warehouse_accounting(apps, schema_editor):
    Module = apps.get_model('api', 'Module')
    Module.objects.filter(code__in=[item[0] for item in WAREHOUSE_MODULES]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0028_inventorycategory_unitofmeasure_warehouse_and_more'),
    ]

    operations = [
        migrations.RunPython(seed_warehouse_accounting, remove_warehouse_accounting),
    ]
