from django.db import migrations


def seed_shift_supervisor(apps, schema_editor):
    AccessGroup = apps.get_model('api', 'AccessGroup')
    GroupModuleAccess = apps.get_model('api', 'GroupModuleAccess')
    Module = apps.get_model('api', 'Module')
    Permission = apps.get_model('api', 'Permission')
    group, created = AccessGroup.objects.get_or_create(name='Начальник смены', defaults={
        'description': 'Операции переработки масла и производства канистр и крышек без приёмки и административных полномочий.',
    })
    if not created:
        return
    view = Permission.objects.get(code='view')
    create = Permission.objects.get(code='create')
    for code in (
        'dashboard', 'used-oil-processing',
        'boiler-loading', 'separator-loading', 'separator-output',
        'chemical-mixer-loading', 'workshop-loading',
        'raw-diesel-tank-loading', 'raw-spindle-tank-loading',
        'sorption-loading', 'finishing-mixer-loading', 'finishing-filter-loading', 'finished-product-loading',
        'sorbent-loading', 'canister-loading', 'cap-loading', 'canister-output', 'cap-output',
    ):
        module = Module.objects.get(code=code)
        access = GroupModuleAccess.objects.create(group=group, module=module)
        access.permissions.add(view)
        if code not in ('dashboard', 'used-oil-processing'):
            access.permissions.add(create)
        if code == 'dashboard':
            group.start_module = module
    group.save(update_fields=['start_module'])


class Migration(migrations.Migration):
    dependencies = [('api', '0037_seed_oil_finishing_modules')]
    operations = [migrations.RunPython(seed_shift_supervisor, migrations.RunPython.noop)]
