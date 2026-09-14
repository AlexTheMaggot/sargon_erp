from decimal import Decimal

from django.db import migrations


def seed_initial_chemical_mixers(apps, schema_editor):
    ProductionContainer = apps.get_model('api', 'ProductionContainer')
    for number in (1, 2):
        ProductionContainer.objects.update_or_create(
            kind='chemical_mixer',
            number=number,
            defaults={
                'system_code': f'chemical-mixer-{number}',
                'capacity_liters': Decimal('10000.000'),
                'current_volume_liters': Decimal('0.000'),
                'is_active': True,
            },
        )


def remove_initial_chemical_mixers(apps, schema_editor):
    ProductionContainer = apps.get_model('api', 'ProductionContainer')
    ProductionContainer.objects.filter(
        kind='chemical_mixer',
        number__in=(1, 2),
        current_volume_liters=0,
        incoming_movements__isnull=True,
        outgoing_movements__isnull=True,
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0021_alter_materialmovement_movement_type_and_more'),
    ]

    operations = [
        migrations.RunPython(seed_initial_chemical_mixers, remove_initial_chemical_mixers),
    ]
