import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def seed_reagents_access(apps, schema_editor):
    alias = schema_editor.connection.alias
    modules = apps.get_model('api', 'Module').objects.using(alias)
    groups = apps.get_model('api', 'AccessGroup').objects.using(alias)
    grants = apps.get_model('api', 'GroupModuleAccess').objects.using(alias)
    permissions = apps.get_model('api', 'Permission').objects.using(alias)
    module, _ = modules.get_or_create(code='chemical-mixer-reagents', defaults={
        'name': 'Реагенты в химический миксер',
        'description': 'Раздельное списание кислоты и бентонита в химический миксер.',
        'default_path': '/processing/chemical-mixer-reagents',
    })
    group = groups.filter(name='Начальник смены').first()
    if group is not None:
        grant, created = grants.get_or_create(group=group, module=module)
        if created:
            grant.permissions.add(*permissions.filter(code__in=('view', 'create')))


def protect_reagent_history(apps, schema_editor):
    alias = schema_editor.connection.alias
    documents = apps.get_model('api', 'WarehouseDocument').objects.using(alias)
    items = apps.get_model('api', 'InventoryItem').objects.using(alias)
    if documents.filter(production_mixer__isnull=False).exists() or items.filter(production_material='acid').exists():
        raise RuntimeError('Restore a backup to roll back configured acid stock or chemical mixer reagent history.')


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0058_flow_through_finishing_filter'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='warehousedocument',
            name='production_mixer',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='mixer_material_documents', to='api.productioncontainer'),
        ),
        migrations.AlterField(
            model_name='inventoryitem',
            name='production_material',
            field=models.CharField(blank=True, choices=[('', 'Не используется в производственной загрузке'), ('granules', 'Гранулы'), ('dye', 'Краситель'), ('polypropylene', 'Полипропилен'), ('bentonite', 'Бентонит'), ('acid', 'Кислота')], default='', max_length=20),
        ),
        migrations.AlterField(
            model_name='warehousedocument',
            name='production_target',
            field=models.CharField(blank=True, choices=[('canisters', 'Производство канистр'), ('caps', 'Производство крышек'), ('oil_concentrate', 'Приготовление концентрата'), ('bentonite_filter', 'Загрузка бентонита'), ('chemical_acid', 'Загрузка кислоты в химический миксер'), ('chemical_bentonite', 'Загрузка бентонита в химический миксер')], default='', max_length=20),
        ),
        migrations.AddConstraint(
            model_name='inventoryitem',
            constraint=models.UniqueConstraint(condition=models.Q(('production_material', 'acid')), fields=('production_material',), name='one_warehouse_acid_item'),
        ),
        migrations.AddConstraint(
            model_name='warehousedocument',
            constraint=models.CheckConstraint(condition=models.Q(models.Q(('production_mixer__isnull', False), ('production_target__in', ['chemical_acid', 'chemical_bentonite'])), models.Q(models.Q(('production_target__in', ['chemical_acid', 'chemical_bentonite']), _negated=True), ('production_mixer__isnull', True)), _connector='OR'), name='chemical_reagent_loading_records_mixer'),
        ),
        migrations.RunPython(seed_reagents_access, protect_reagent_history),
    ]
