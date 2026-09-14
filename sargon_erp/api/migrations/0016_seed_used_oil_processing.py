from decimal import Decimal

from django.db import migrations


MODULE_CODE = 'used-oil-processing'
GROUP_NAME = 'Менеджер переработки отработанного масла'


def seed_used_oil_processing(apps, schema_editor):
    AccessGroup = apps.get_model('api', 'AccessGroup')
    GroupModuleAccess = apps.get_model('api', 'GroupModuleAccess')
    Module = apps.get_model('api', 'Module')
    Permission = apps.get_model('api', 'Permission')
    ProductionContainer = apps.get_model('api', 'ProductionContainer')

    module, _ = Module.objects.update_or_create(
        code=MODULE_CODE,
        defaults={
            'name': 'Переработка отработанного масла',
            'description': 'Учёт приёмных баков, котлов первичного прогрева и движений масла.',
            'default_path': '/processing/receiving-tanks',
            'is_active': True,
        },
    )
    group, _ = AccessGroup.objects.update_or_create(
        name=GROUP_NAME,
        defaults={
            'description': 'Доступ к загрузке котлов из приёмных баков.',
            'start_module': module,
        },
    )
    access, _ = GroupModuleAccess.objects.get_or_create(group=group, module=module)
    access.permissions.set(Permission.objects.filter(code__in=['view', 'create']))

    ProductionContainer.objects.update_or_create(
        kind='receiving_tank',
        number=1,
        defaults={
            'system_code': 'receiving-tank-1',
            'capacity_liters': Decimal('40000.000'),
            'current_volume_liters': Decimal('0.000'),
            'is_active': True,
        },
    )
    ProductionContainer.objects.update_or_create(
        kind='preheating_boiler',
        number=1,
        defaults={
            'system_code': 'preheating-boiler-1',
            'capacity_liters': Decimal('10000.000'),
            'current_volume_liters': Decimal('0.000'),
            'is_active': True,
        },
    )


def unseed_used_oil_processing(apps, schema_editor):
    AccessGroup = apps.get_model('api', 'AccessGroup')
    Module = apps.get_model('api', 'Module')
    ProductionContainer = apps.get_model('api', 'ProductionContainer')

    AccessGroup.objects.filter(name=GROUP_NAME, users__isnull=True).delete()
    Module.objects.filter(code=MODULE_CODE, access_groups__isnull=True).delete()
    ProductionContainer.objects.filter(
        system_code__in=['receiving-tank-1', 'preheating-boiler-1'],
        current_volume_liters=0,
        incoming_movements__isnull=True,
        outgoing_movements__isnull=True,
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0015_operationauditlog_productioncontainer_and_more'),
    ]

    operations = [
        migrations.RunPython(seed_used_oil_processing, unseed_used_oil_processing),
    ]
