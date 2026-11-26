import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def configure_flow_filter(apps, schema_editor):
    alias = schema_editor.connection.alias
    filters = apps.get_model('api', 'ProductionContainer').objects.using(alias).filter(kind='finishing_filter')
    if filters.exclude(current_volume_liters=0).exists():
        raise RuntimeError('Finishing filters still hold oil. Record the actual transfers before migrating.')
    if filters.filter(is_active=True).count() > 1:
        raise RuntimeError('Only one finishing filter can be active. Select it before migrating.')
    filters.update(capacity_liters=None)

    modules = apps.get_model('api', 'Module').objects.using(alias)
    groups = apps.get_model('api', 'AccessGroup').objects.using(alias)
    grants = apps.get_model('api', 'GroupModuleAccess').objects.using(alias)
    permissions = apps.get_model('api', 'Permission').objects.using(alias)

    modules.filter(code='finishing-filter-loading').update(is_active=False)
    modules.filter(code='finished-product-loading', name='Загрузка бака готовой продукции').update(
        name='Перелив через финишный фильтр',
    )
    modules.filter(code='finished-product-loading', description='Движение продукта из финишного фильтра в бак готовой продукции.').update(
        description='Перелив из песочного миксера через финишный фильтр в бак готовой продукции.',
    )
    module, _ = modules.get_or_create(code='bentonite-loading', defaults={
        'name': 'Загрузка бентонита',
        'description': 'Списание бентонита со склада при загрузке финишного фильтра.',
        'default_path': '/processing/bentonite-loading',
    })
    group = groups.filter(name='Начальник смены').first()
    if group is not None:
        grant, created = grants.get_or_create(group=group, module=module)
        if created:
            grant.permissions.add(*permissions.filter(code__in=('view', 'create')))


def preserve_flow_filter_history(apps, schema_editor):
    alias = schema_editor.connection.alias
    containers = apps.get_model('api', 'ProductionContainer').objects.using(alias)
    items = apps.get_model('api', 'InventoryItem').objects.using(alias)
    if (containers.filter(kind='finishing_filter').exists() or items.filter(production_material='bentonite').exists()):
        raise RuntimeError('Rollback needs a backup with legacy filter capacities and without new bentonite data.')
    apps.get_model('api', 'Module').objects.using(alias).filter(code='finishing-filter-loading').update(is_active=True)


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0057_reactor_receivers'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name='productioncontainer',
            name='production_container_capacity_positive',
        ),
        migrations.RemoveConstraint(
            model_name='productioncontainer',
            name='production_container_oil_product_valid',
        ),
        migrations.AddField(
            model_name='materialmovement',
            name='via_filter',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='filtered_movements', to='api.productioncontainer'),
        ),
        migrations.AddField(
            model_name='warehousedocument',
            name='production_filter',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='filter_material_documents', to='api.productioncontainer'),
        ),
        migrations.AlterField(
            model_name='inventoryitem',
            name='production_material',
            field=models.CharField(blank=True, choices=[('', 'Не используется в производственной загрузке'), ('granules', 'Гранулы'), ('dye', 'Краситель'), ('polypropylene', 'Полипропилен'), ('bentonite', 'Бентонит')], default='', max_length=20),
        ),
        migrations.AlterField(
            model_name='materialmovement',
            name='movement_type',
            field=models.CharField(choices=[('receipt_to_tank', 'Поступление из приёмки'), ('tank_to_boiler', 'Загрузка котла'), ('boiler_to_workshop', 'Загрузка в цех переработки'), ('boiler_to_reactor', 'Загрузка реактора переработки'), ('receiver_to_raw_diesel_tank', 'Слив солярки из ресивера'), ('receiver_to_raw_spindle_tank', 'Слив веретенки из ресивера'), ('reactor_to_nigrol_tank', 'Отгрузка нигрола из реактора'), ('raw_to_chemical_mixer', 'Загрузка химического миксера'), ('chemical_to_finishing_mixer', 'Загрузка песочного миксера'), ('boiler_to_chemical_mixer', 'Загрузка химического миксера (прежний маршрут)'), ('chemical_mixer_to_workshop', 'Загрузка в цех переработки (прежний маршрут)'), ('workshop_to_raw_diesel_tank', 'Загрузка бака сырой солярки'), ('workshop_to_raw_spindle_tank', 'Загрузка бака сырой веретенки'), ('workshop_to_nigrol_tank', 'Отгрузка нигрола'), ('raw_to_finishing_mixer', 'Загрузка песочного миксера (прежний маршрут)'), ('mixer_to_filter', 'Загрузка финишного фильтра'), ('filter_to_finished_tank', 'Загрузка бака готовой продукции'), ('mixer_to_finished_tank', 'Перелив через финишный фильтр'), ('spindle_to_concentrate', 'Загрузка реактора концентрата'), ('spindle_to_blender', 'Загрузка основы в смеситель'), ('concentrate_to_blender', 'Передача концентрата в смеситель'), ('blender_to_oil_tank', 'Перелив товарного масла в бак'), ('oil_filling', 'Розлив товарного масла'), ('compensation', 'Компенсирующее движение')], max_length=32),
        ),
        migrations.AlterField(
            model_name='productioncontainer',
            name='capacity_liters',
            field=models.DecimalField(blank=True, decimal_places=3, max_digits=14, null=True),
        ),
        migrations.AlterField(
            model_name='warehousedocument',
            name='production_target',
            field=models.CharField(blank=True, choices=[('canisters', 'Производство канистр'), ('caps', 'Производство крышек'), ('oil_concentrate', 'Приготовление концентрата'), ('bentonite_filter', 'Загрузка бентонита')], default='', max_length=20),
        ),
        migrations.RunPython(configure_flow_filter, preserve_flow_filter_history),
        migrations.AddConstraint(
            model_name='materialmovement',
            constraint=models.CheckConstraint(condition=models.Q(models.Q(('movement_type', 'mixer_to_finished_tank'), ('via_filter__isnull', False)), models.Q(models.Q(('movement_type', 'mixer_to_finished_tank'), _negated=True), ('via_filter__isnull', True)), _connector='OR'), name='finished_tank_transfer_records_filter'),
        ),
        migrations.AddConstraint(
            model_name='productioncontainer',
            constraint=models.CheckConstraint(condition=models.Q(models.Q(('capacity_liters__isnull', True), ('current_volume_liters', 0), ('kind', 'finishing_filter')), models.Q(models.Q(('kind', 'finishing_filter'), _negated=True), ('capacity_liters__gt', 0), ('capacity_liters__isnull', False)), _connector='OR'), name='production_volume_only_for_containers'),
        ),
        migrations.AddConstraint(
            model_name='productioncontainer',
            constraint=models.UniqueConstraint(condition=models.Q(('is_active', True), ('kind', 'finishing_filter')), fields=('kind',), name='one_active_finishing_filter'),
        ),
        migrations.AddConstraint(
            model_name='productioncontainer',
            constraint=models.CheckConstraint(condition=models.Q(models.Q(('current_volume_liters__gt', 0), ('kind__in', ['chemical_mixer', 'finishing_mixer']), ('oil_product__in', ['diesel', 'spindle'])), models.Q(('current_volume_liters', 0), ('kind__in', ['chemical_mixer', 'finishing_mixer']), ('oil_product', '')), models.Q(models.Q(('kind__in', ['chemical_mixer', 'finishing_mixer']), _negated=True), ('oil_product', '')), _connector='OR'), name='production_container_oil_product_valid'),
        ),
        migrations.AddConstraint(
            model_name='warehousedocument',
            constraint=models.CheckConstraint(condition=models.Q(models.Q(('production_filter__isnull', False), ('production_target', 'bentonite_filter')), models.Q(models.Q(('production_target', 'bentonite_filter'), _negated=True), ('production_filter__isnull', True)), _connector='OR'), name='bentonite_loading_records_filter'),
        ),
    ]
