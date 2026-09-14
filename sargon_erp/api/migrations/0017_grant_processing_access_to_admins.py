from django.db import migrations


def grant_processing_access_to_admins(apps, schema_editor):
    AccessGroup = apps.get_model('api', 'AccessGroup')
    GroupModuleAccess = apps.get_model('api', 'GroupModuleAccess')
    Module = apps.get_model('api', 'Module')
    Permission = apps.get_model('api', 'Permission')

    admin_group = AccessGroup.objects.filter(name='Администраторы').first()
    module = Module.objects.filter(code='used-oil-processing').first()
    if admin_group is None or module is None:
        return

    access, _ = GroupModuleAccess.objects.get_or_create(group=admin_group, module=module)
    access.permissions.set(Permission.objects.filter(code__in=['view', 'create', 'update', 'delete', 'approve']))


def revoke_processing_access_from_admins(apps, schema_editor):
    GroupModuleAccess = apps.get_model('api', 'GroupModuleAccess')
    GroupModuleAccess.objects.filter(
        group__name='Администраторы',
        module__code='used-oil-processing',
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0016_seed_used_oil_processing'),
    ]

    operations = [
        migrations.RunPython(grant_processing_access_to_admins, revoke_processing_access_from_admins),
    ]
