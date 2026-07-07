from django.db import migrations


def seed_real_modules(apps, schema_editor):
    AccessGroup = apps.get_model('api', 'AccessGroup')
    GroupModuleAccess = apps.get_model('api', 'GroupModuleAccess')
    Module = apps.get_model('api', 'Module')
    Permission = apps.get_model('api', 'Permission')

    Module.objects.filter(code__in=['sales', 'warehouse', 'clients', 'reports']).delete()
    AccessGroup.objects.filter(name='Менеджеры продаж').delete()

    modules = []
    for code, name, description in [
        ('raw-material-receiving', 'Прием сырья', 'Учет поступления и первичной проверки сырья.'),
        ('laboratory', 'Лаборатория', 'Лабораторные проверки, анализы и контроль качества.'),
    ]:
        module, _ = Module.objects.update_or_create(
            code=code,
            defaults={
                'name': name,
                'description': description,
                'is_active': True,
            },
        )
        modules.append(module)

    admin_group = AccessGroup.objects.filter(name='Администраторы').first()
    if admin_group is None:
        return

    permissions = list(Permission.objects.all())
    for module in modules:
        access, _ = GroupModuleAccess.objects.get_or_create(group=admin_group, module=module)
        access.permissions.set(permissions)


def rollback_real_modules(apps, schema_editor):
    Module = apps.get_model('api', 'Module')
    Module.objects.filter(code__in=['raw-material-receiving', 'laboratory']).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(seed_real_modules, rollback_real_modules),
    ]
