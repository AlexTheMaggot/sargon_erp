from django.db import migrations


PROCESSING_FORM_MODULES = (
    (
        'boiler-loading',
        'Загрузка котла отработки',
        'Движение масла из приёмного бака в котёл первичного прогрева.',
        '/processing/boiler-loading',
    ),
    (
        'separator-loading',
        'Загрузка сепаратора',
        'Движение масла из котла первичного прогрева в сепаратор.',
        '/processing/separator-loading',
    ),
    (
        'separator-output',
        'Отгрузка сепаратора',
        'Отгрузка технической воды и технического мусора из сепаратора.',
        '/processing/separator-output',
    ),
    (
        'chemical-mixer-loading',
        'Загрузка химического миксера',
        'Движение очищенного масла из сепаратора в химический миксер.',
        '/processing/chemical-mixer-loading',
    ),
    (
        'workshop-loading',
        'Загрузка в цех переработки',
        'Движение масла из химического миксера в цех переработки.',
        '/processing/workshop-loading',
    ),
    (
        'raw-diesel-tank-loading',
        'Загрузка бака сырой солярки',
        'Движение сырой солярки из цеха переработки в продуктовый бак.',
        '/processing/raw-diesel-tank-loading',
    ),
    (
        'raw-spindle-tank-loading',
        'Загрузка бака сырой веретенки',
        'Движение сырой веретенки из цеха переработки в продуктовый бак.',
        '/processing/raw-spindle-tank-loading',
    ),
)


def create_processing_form_modules(apps, schema_editor):
    GroupModuleAccess = apps.get_model('api', 'GroupModuleAccess')
    Module = apps.get_model('api', 'Module')

    modules = []
    for code, name, description, default_path in PROCESSING_FORM_MODULES:
        module, _ = Module.objects.update_or_create(
            code=code,
            defaults={
                'name': name,
                'description': description,
                'default_path': default_path,
                'is_active': True,
            },
        )
        modules.append(module)

    legacy_access_rows = list(
        GroupModuleAccess.objects
        .filter(module__code='used-oil-processing')
        .prefetch_related('permissions')
    )
    for legacy_access in legacy_access_rows:
        permissions = list(legacy_access.permissions.all())
        for module in modules:
            access, _ = GroupModuleAccess.objects.get_or_create(
                group=legacy_access.group,
                module=module,
            )
            access.permissions.set(permissions)


def remove_processing_form_modules(apps, schema_editor):
    Module = apps.get_model('api', 'Module')
    Module.objects.filter(code__in=[item[0] for item in PROCESSING_FORM_MODULES]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0026_seed_initial_raw_product_tanks'),
    ]

    operations = [
        migrations.RunPython(create_processing_form_modules, remove_processing_form_modules),
    ]
