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
    for code, name, path in (
        ('canister-output', 'Выпуск канистр', '/production/canister-output'),
        ('cap-output', 'Выпуск крышек', '/production/cap-output'),
    ):
        module, created = Module.objects.get_or_create(code=code, defaults={
            'name': name, 'default_path': path, 'is_active': True,
            'description': 'Регистрация выпуска и фактического расхода сырья в производстве.',
        })
        if created and admin_group:
            access, _ = GroupModuleAccess.objects.get_or_create(group=admin_group, module=module)
            access.permissions.add(*permissions)


class Migration(migrations.Migration):
    dependencies = [('api', '0034_production_output_accounting')]
    operations = [migrations.RunPython(seed_modules, migrations.RunPython.noop)]
