from django.db import migrations


MODULES = (
    ('canister-loading', 'Загрузка производства канистр', '/production/canister-loading'),
    ('cap-loading', 'Загрузка производства крышек', '/production/cap-loading'),
    ('sorbent-loading', 'Загрузка сорбента', '/processing/sorbent-loading'),
)


def seed_modules(apps, schema_editor):
    Module = apps.get_model('api', 'Module')
    Permission = apps.get_model('api', 'Permission')
    AccessGroup = apps.get_model('api', 'AccessGroup')
    GroupModuleAccess = apps.get_model('api', 'GroupModuleAccess')
    permissions = [Permission.objects.get_or_create(code=code, defaults={'name': name})[0] for code, name in (
        ('view', 'Просмотр'), ('create', 'Создание'),
    )]
    admin_group = AccessGroup.objects.filter(name='Администраторы').first()
    for code, name, path in MODULES:
        module, created = Module.objects.get_or_create(code=code, defaults={
            'name': name, 'default_path': path, 'description': 'Передача материалов со склада в производство.',
            'is_active': True,
        })
        if admin_group and created:
            access, _ = GroupModuleAccess.objects.get_or_create(group=admin_group, module=module)
            access.permissions.add(*permissions)


class Migration(migrations.Migration):
    dependencies = [('api', '0032_production_material_loadings')]
    operations = [migrations.RunPython(seed_modules, migrations.RunPython.noop)]
