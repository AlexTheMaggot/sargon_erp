from django.db import migrations, models
import django.db.models.deletion


MODULE_DEFAULT_PATHS = {
    'dashboard': '/welcome',
    'raw-material-receiving': '/raw-material/receipts',
    'laboratory-analysis': '/laboratory/analyses',
    'access': '/access/users',
}


GROUP_START_MODULES = {
    'Администраторы': 'dashboard',
    'Менеджер приема сырья': 'raw-material-receiving',
    'Лаборант': 'laboratory-analysis',
}


def set_default_paths_and_start_modules(apps, schema_editor):
    AccessGroup = apps.get_model('api', 'AccessGroup')
    Module = apps.get_model('api', 'Module')

    modules = {
        module.code: module
        for module in Module.objects.filter(code__in=MODULE_DEFAULT_PATHS)
    }

    for code, default_path in MODULE_DEFAULT_PATHS.items():
        module = modules.get(code)
        if module:
            module.default_path = default_path
            module.save(update_fields=['default_path'])

    for group_name, module_code in GROUP_START_MODULES.items():
        group = AccessGroup.objects.filter(name=group_name).first()
        module = modules.get(module_code)
        if group and module:
            group.start_module = module
            group.save(update_fields=['start_module'])


def clear_default_paths_and_start_modules(apps, schema_editor):
    AccessGroup = apps.get_model('api', 'AccessGroup')
    Module = apps.get_model('api', 'Module')

    AccessGroup.objects.update(start_module=None)
    Module.objects.filter(code__in=MODULE_DEFAULT_PATHS).update(default_path='')


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0010_rawmaterialreceipt_is_completed'),
    ]

    operations = [
        migrations.AddField(
            model_name='module',
            name='default_path',
            field=models.CharField(blank=True, max_length=160),
        ),
        migrations.AddField(
            model_name='accessgroup',
            name='start_module',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='start_groups',
                to='api.module',
            ),
        ),
        migrations.RunPython(set_default_paths_and_start_modules, clear_default_paths_and_start_modules),
    ]
