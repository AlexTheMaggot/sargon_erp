from django.db import migrations


def update_laboratory_module(apps, schema_editor):
    Module = apps.get_model('api', 'Module')

    legacy_module = Module.objects.filter(code='laboratory').first()
    target_module = Module.objects.filter(code='laboratory-analysis').first()
    if legacy_module and target_module:
        legacy_module.delete()
        target_module.name = 'Лабораторный анализ'
        target_module.description = 'Лабораторные проверки, анализы и контроль качества.'
        target_module.is_active = True
        target_module.save(update_fields=['name', 'description', 'is_active'])
    elif legacy_module:
        legacy_module.code = 'laboratory-analysis'
        legacy_module.name = 'Лабораторный анализ'
        legacy_module.description = 'Лабораторные проверки, анализы и контроль качества.'
        legacy_module.is_active = True
        legacy_module.save(update_fields=['code', 'name', 'description', 'is_active'])
    else:
        Module.objects.update_or_create(
            code='laboratory-analysis',
            defaults={
                'name': 'Лабораторный анализ',
                'description': 'Лабораторные проверки, анализы и контроль качества.',
                'is_active': True,
            },
        )

    Module.objects.update_or_create(
        code='raw-material-receiving',
        defaults={
            'name': 'Прием сырья',
            'description': 'Учет поступления и первичной проверки сырья.',
            'is_active': True,
        },
    )


def rollback_laboratory_module(apps, schema_editor):
    Module = apps.get_model('api', 'Module')
    Module.objects.filter(code='laboratory-analysis').update(code='laboratory', name='Лаборатория')


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0005_rawmaterialreceipt_laboratoryanalysis'),
    ]

    operations = [
        migrations.RunPython(update_laboratory_module, rollback_laboratory_module),
    ]
