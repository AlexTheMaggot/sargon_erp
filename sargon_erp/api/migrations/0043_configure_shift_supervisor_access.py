from django.db import migrations


OPERATIONS = (
    'boiler-loading', 'separator-loading', 'separator-output', 'chemical-mixer-loading', 'workshop-loading',
    'raw-diesel-tank-loading', 'raw-spindle-tank-loading', 'sorption-loading', 'finishing-mixer-loading',
    'finishing-filter-loading', 'finished-product-loading', 'sorbent-loading', 'sorbent-cycle',
    'concentrate-loading', 'oil-blending', 'oil-tank-loading', 'oil-filling',
    'canister-loading', 'cap-loading', 'canister-output', 'cap-output',
)


def configure_access(apps, schema_editor):
    AccessGroup = apps.get_model('api', 'AccessGroup')
    GroupModuleAccess = apps.get_model('api', 'GroupModuleAccess')
    Module = apps.get_model('api', 'Module')
    Permission = apps.get_model('api', 'Permission')
    dashboard = Module.objects.get(code='dashboard')
    view = Permission.objects.get(code='view')
    create = Permission.objects.get(code='create')
    group, _ = AccessGroup.objects.get_or_create(name='Начальник смены', defaults={
        'description': 'Производственные операции без приёмки, лаборатории, обзора и административных полномочий.',
    })
    for existing_group in AccessGroup.objects.exclude(pk=group.pk):
        access, created = GroupModuleAccess.objects.get_or_create(group=existing_group, module=dashboard)
        if created:
            access.permissions.add(view)
    codes = (*OPERATIONS, 'used-oil-processing')
    GroupModuleAccess.objects.filter(group=group).exclude(module__code__in=codes).delete()
    for code in codes:
        module = Module.objects.get(code=code)
        access, _ = GroupModuleAccess.objects.get_or_create(group=group, module=module)
        access.permissions.set([view] if code == 'used-oil-processing' else [view, create])
    group.start_module = Module.objects.get(code='boiler-loading')
    group.save(update_fields=['start_module'])


class Migration(migrations.Migration):
    dependencies = [('api', '0042_seed_sorbent_cycle_module')]
    operations = [migrations.RunPython(configure_access, migrations.RunPython.noop)]
