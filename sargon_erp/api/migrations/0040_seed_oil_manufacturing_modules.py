from django.db import migrations


def seed_modules(apps, schema_editor):
    Module = apps.get_model('api', 'Module')
    Permission = apps.get_model('api', 'Permission')
    AccessGroup = apps.get_model('api', 'AccessGroup')
    GroupModuleAccess = apps.get_model('api', 'GroupModuleAccess')
    permissions = list(Permission.objects.filter(code__in=['view', 'create']))
    groups = list(AccessGroup.objects.filter(name__in=['Администраторы', 'Начальник смены']))
    for code, name in (
        ('concentrate-loading', 'Приготовление концентрата'),
        ('oil-blending', 'Загрузка блендингового смесителя'),
        ('oil-tank-loading', 'Перелив масла в продуктовый бак'),
        ('oil-filling', 'Розлив товарного масла'),
    ):
        module, created = Module.objects.get_or_create(code=code, defaults={
            'name': name, 'default_path': f'/oil-production/{code}', 'is_active': True,
            'description': 'Учёт загрузок и фактических переливов при производстве товарных масел.',
        })
        if created:
            for group in groups:
                access, _ = GroupModuleAccess.objects.get_or_create(group=group, module=module)
                access.permissions.add(*permissions)


class Migration(migrations.Migration):
    dependencies = [('api', '0039_commodity_oil_manufacturing')]
    operations = [migrations.RunPython(seed_modules, migrations.RunPython.noop)]
