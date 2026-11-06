from django.db import migrations


def seed_modules(apps, schema_editor):
    Module = apps.get_model('api', 'Module')
    Permission = apps.get_model('api', 'Permission')
    AccessGroup = apps.get_model('api', 'AccessGroup')
    GroupModuleAccess = apps.get_model('api', 'GroupModuleAccess')
    permissions = [Permission.objects.get_or_create(code=code, defaults={'name': name})[0] for code, name in (
        ('view', 'Просмотр'), ('create', 'Создание'),
    )]
    admin_group = AccessGroup.objects.filter(name='Администраторы').first()
    for code, name in (
        ('sorption-loading', 'Загрузка масла в сорбент-систему'),
        ('finishing-mixer-loading', 'Загрузка финишного миксера'),
        ('finishing-filter-loading', 'Загрузка финишного фильтра'),
        ('finished-product-loading', 'Загрузка бака готовой продукции'),
    ):
        module, created = Module.objects.get_or_create(code=code, defaults={
            'name': name, 'default_path': f'/processing/{code}', 'is_active': True,
            'description': 'Учёт перемещения масла по общей линии финишной очистки.',
        })
        if created and admin_group:
            access, _ = GroupModuleAccess.objects.get_or_create(group=admin_group, module=module)
            access.permissions.add(*permissions)


class Migration(migrations.Migration):
    dependencies = [('api', '0036_oil_finishing_line')]
    operations = [migrations.RunPython(seed_modules, migrations.RunPython.noop)]
