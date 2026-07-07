from django.db import migrations


def create_operational_access_groups(apps, schema_editor):
    AccessGroup = apps.get_model('api', 'AccessGroup')
    GroupModuleAccess = apps.get_model('api', 'GroupModuleAccess')
    Module = apps.get_model('api', 'Module')
    Permission = apps.get_model('api', 'Permission')

    permissions = {
        permission.code: permission
        for permission in Permission.objects.filter(code__in=['view', 'create', 'update', 'delete', 'approve'])
    }
    raw_module = Module.objects.get(code='raw-material-receiving')
    laboratory_module = Module.objects.get(code='laboratory-analysis')

    raw_manager_group, _ = AccessGroup.objects.get_or_create(
        name='Менеджер приема сырья',
        defaults={'description': 'Доступ только к модулю приема сырья.'},
    )
    GroupModuleAccess.objects.filter(group=raw_manager_group).exclude(module=raw_module).delete()
    raw_access, _ = GroupModuleAccess.objects.get_or_create(group=raw_manager_group, module=raw_module)
    raw_access.permissions.set([
        permissions['view'],
        permissions['create'],
        permissions['update'],
        permissions['delete'],
    ])

    laboratory_group, _ = AccessGroup.objects.get_or_create(
        name='Лаборант',
        defaults={'description': 'Доступ только к модулю лабораторного анализа.'},
    )
    GroupModuleAccess.objects.filter(group=laboratory_group).exclude(module=laboratory_module).delete()
    laboratory_access, _ = GroupModuleAccess.objects.get_or_create(group=laboratory_group, module=laboratory_module)
    laboratory_access.permissions.set([
        permissions['view'],
        permissions['update'],
        permissions['approve'],
    ])


def remove_operational_access_groups(apps, schema_editor):
    AccessGroup = apps.get_model('api', 'AccessGroup')
    AccessGroup.objects.filter(name__in=['Менеджер приема сырья', 'Лаборант']).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0008_laboratoryanalysis_is_rejected'),
    ]

    operations = [
        migrations.RunPython(create_operational_access_groups, remove_operational_access_groups),
    ]
