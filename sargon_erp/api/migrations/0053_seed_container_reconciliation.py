from django.db import migrations


def seed_reconciliation_access(apps, schema_editor):
    alias = schema_editor.connection.alias
    modules = apps.get_model('api', 'Module').objects.using(alias)
    groups = apps.get_model('api', 'AccessGroup').objects.using(alias)
    permissions = apps.get_model('api', 'Permission').objects.using(alias)
    grants = apps.get_model('api', 'GroupModuleAccess').objects.using(alias)
    module, _ = modules.get_or_create(code='container-reconciliation', defaults={
        'name': 'Сверка остатков',
        'description': 'Замеры и корректировка остатков ёмкостей переработки масла.',
        'default_path': '/processing/reconciliation',
    })
    group, created = groups.get_or_create(name='Заведующий складом', defaults={'start_module': module})
    if created:
        access = grants.create(group=group, module=module)
        access.permissions.add(*permissions.filter(code__in=('view', 'create', 'update')))


class Migration(migrations.Migration):
    dependencies = [('api', '0052_container_reconciliations')]
    operations = [migrations.RunPython(seed_reconciliation_access, migrations.RunPython.noop)]
