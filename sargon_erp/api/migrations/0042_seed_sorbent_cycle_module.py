from django.db import migrations


def seed_module(apps, schema_editor):
    Module = apps.get_model('api', 'Module')
    Permission = apps.get_model('api', 'Permission')
    AccessGroup = apps.get_model('api', 'AccessGroup')
    GroupModuleAccess = apps.get_model('api', 'GroupModuleAccess')
    module, created = Module.objects.get_or_create(code='sorbent-cycle', defaults={
        'name': 'Циркуляция сорбента', 'default_path': '/processing/sorbent-cycle',
        'description': 'Подача из бака, прогрев и очистка, возврат сорбента без повторного складского списания.',
        'is_active': True,
    })
    if created:
        permissions = list(Permission.objects.filter(code__in=['view', 'create']))
        for group in AccessGroup.objects.filter(name__in=['Администраторы', 'Начальник смены']):
            access, _ = GroupModuleAccess.objects.get_or_create(group=group, module=module)
            access.permissions.add(*permissions)


class Migration(migrations.Migration):
    dependencies = [('api', '0041_sorbent_cycle')]
    operations = [migrations.RunPython(seed_module, migrations.RunPython.noop)]
