from django.db import migrations


SUPPLIER_MODULE_CODE = 'suppliers'


def add_supplier_access(apps, schema_editor):
    AccessGroup = apps.get_model('api', 'AccessGroup')
    GroupModuleAccess = apps.get_model('api', 'GroupModuleAccess')
    Module = apps.get_model('api', 'Module')
    Permission = apps.get_model('api', 'Permission')

    supplier_module, _ = Module.objects.update_or_create(
        code=SUPPLIER_MODULE_CODE,
        defaults={
            'name': 'Поставщики',
            'description': 'Просмотр и управление справочником поставщиков.',
            'default_path': '/directories/suppliers',
            'is_active': True,
        },
    )
    crud_permissions = Permission.objects.filter(code__in=['view', 'create', 'update', 'delete'])

    for group_name in ['Администраторы', 'Менеджер приема сырья']:
        group = AccessGroup.objects.filter(name=group_name).first()
        if group is None:
            continue
        access, _ = GroupModuleAccess.objects.get_or_create(group=group, module=supplier_module)
        access.permissions.set(crud_permissions)


def remove_supplier_access(apps, schema_editor):
    Module = apps.get_model('api', 'Module')
    Module.objects.filter(code=SUPPLIER_MODULE_CODE).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0013_laboratoryanalysis_decided_at_and_more'),
    ]

    operations = [
        migrations.RunPython(add_supplier_access, remove_supplier_access),
    ]
