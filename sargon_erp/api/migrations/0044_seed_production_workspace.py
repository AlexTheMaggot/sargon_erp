from django.db import migrations


def seed_workspace(apps, schema_editor):
    Module = apps.get_model('api', 'Module')
    Permission = apps.get_model('api', 'Permission')
    AccessGroup = apps.get_model('api', 'AccessGroup')
    GroupModuleAccess = apps.get_model('api', 'GroupModuleAccess')
    module, _ = Module.objects.get_or_create(code='production-workspace', defaults={
        'name': 'Рабочее место производства', 'default_path': '/production',
        'description': 'Крупные карточки направлений и доступных производственных форм.',
        'is_active': True,
    })
    group = AccessGroup.objects.filter(name='Начальник смены').first()
    if group is None:
        return
    access, created = GroupModuleAccess.objects.get_or_create(group=group, module=module)
    if created:
        access.permissions.add(Permission.objects.get(code='view'))
        group.start_module = module
        group.save(update_fields=['start_module'])


class Migration(migrations.Migration):
    dependencies = [('api', '0043_configure_shift_supervisor_access')]
    operations = [migrations.RunPython(seed_workspace, migrations.RunPython.noop)]
