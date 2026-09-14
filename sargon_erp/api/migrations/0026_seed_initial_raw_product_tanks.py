from decimal import Decimal

from django.db import migrations


INITIAL_TANKS = (
    ('raw_diesel_tank', 'raw-diesel-tank-1', Decimal('35000.000')),
    ('raw_spindle_tank', 'raw-spindle-tank-1', Decimal('30000.000')),
)


def seed_initial_raw_product_tanks(apps, schema_editor):
    ProductionContainer = apps.get_model('api', 'ProductionContainer')
    for kind, system_code, capacity in INITIAL_TANKS:
        ProductionContainer.objects.update_or_create(
            kind=kind,
            number=1,
            defaults={
                'system_code': system_code,
                'capacity_liters': capacity,
                'current_volume_liters': Decimal('0.000'),
                'is_active': True,
            },
        )


def remove_initial_raw_product_tanks(apps, schema_editor):
    ProductionContainer = apps.get_model('api', 'ProductionContainer')
    for kind, system_code, _capacity in INITIAL_TANKS:
        ProductionContainer.objects.filter(
            kind=kind,
            number=1,
            system_code=system_code,
            current_volume_liters=0,
            incoming_movements__isnull=True,
            outgoing_movements__isnull=True,
        ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0025_alter_materialmovement_movement_type_and_more'),
    ]

    operations = [
        migrations.RunPython(seed_initial_raw_product_tanks, remove_initial_raw_product_tanks),
    ]
