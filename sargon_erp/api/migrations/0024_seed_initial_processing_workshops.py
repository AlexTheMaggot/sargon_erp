from decimal import Decimal

from django.db import migrations


def seed_initial_processing_workshops(apps, schema_editor):
    ProductionContainer = apps.get_model('api', 'ProductionContainer')
    for number in (1, 2):
        ProductionContainer.objects.update_or_create(
            kind='processing_workshop',
            number=number,
            defaults={
                'system_code': f'processing-workshop-{number}',
                'capacity_liters': Decimal('10000.000'),
                'current_volume_liters': Decimal('0.000'),
                'is_active': True,
            },
        )


def remove_initial_processing_workshops(apps, schema_editor):
    ProductionContainer = apps.get_model('api', 'ProductionContainer')
    ProductionContainer.objects.filter(
        kind='processing_workshop',
        number__in=(1, 2),
        current_volume_liters=0,
        incoming_movements__isnull=True,
        outgoing_movements__isnull=True,
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0023_alter_materialmovement_movement_type_and_more'),
    ]

    operations = [
        migrations.RunPython(seed_initial_processing_workshops, remove_initial_processing_workshops),
    ]
