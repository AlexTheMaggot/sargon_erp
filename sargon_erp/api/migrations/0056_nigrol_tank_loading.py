from django.db import migrations, models


def seed_nigrol_loading(apps, schema_editor):
    alias = schema_editor.connection.alias
    modules = apps.get_model('api', 'Module').objects.using(alias)
    groups = apps.get_model('api', 'AccessGroup').objects.using(alias)
    grants = apps.get_model('api', 'GroupModuleAccess').objects.using(alias)
    permissions = apps.get_model('api', 'Permission').objects.using(alias)
    module, _ = modules.get_or_create(code='nigrol-loading', defaults={
        'name': 'Отгрузка нигрола',
        'description': 'Перелив нигрола из общего остатка цеха переработки в отдельный бак.',
        'default_path': '/processing/nigrol-loading',
    })
    group = groups.filter(name='Начальник смены').first()
    if group is not None:
        grant, created = grants.get_or_create(group=group, module=module)
        if created:
            grant.permissions.add(*permissions.filter(code__in=('view', 'create')))


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0055_remove_second_chemical_mixer'),
    ]

    operations = [
        migrations.AlterField(
            model_name='materialmovement',
            name='movement_type',
            field=models.CharField(choices=[('receipt_to_tank', 'Поступление из приёмки'), ('tank_to_boiler', 'Загрузка котла'), ('boiler_to_workshop', 'Загрузка в цех переработки'), ('raw_to_chemical_mixer', 'Загрузка химического миксера'), ('chemical_to_finishing_mixer', 'Загрузка песочного миксера'), ('boiler_to_chemical_mixer', 'Загрузка химического миксера (прежний маршрут)'), ('chemical_mixer_to_workshop', 'Загрузка в цех переработки (прежний маршрут)'), ('workshop_to_raw_diesel_tank', 'Загрузка бака сырой солярки'), ('workshop_to_raw_spindle_tank', 'Загрузка бака сырой веретенки'), ('workshop_to_nigrol_tank', 'Отгрузка нигрола'), ('raw_to_finishing_mixer', 'Загрузка песочного миксера (прежний маршрут)'), ('mixer_to_filter', 'Загрузка финишного фильтра'), ('filter_to_finished_tank', 'Загрузка бака готовой продукции'), ('spindle_to_concentrate', 'Загрузка реактора концентрата'), ('spindle_to_blender', 'Загрузка основы в смеситель'), ('concentrate_to_blender', 'Передача концентрата в смеситель'), ('blender_to_oil_tank', 'Перелив товарного масла в бак'), ('oil_filling', 'Розлив товарного масла'), ('compensation', 'Компенсирующее движение')], max_length=32),
        ),
        migrations.AlterField(
            model_name='productioncontainer',
            name='kind',
            field=models.CharField(choices=[('receiving_tank', 'Приёмный бак'), ('preheating_boiler', 'Котёл первичного прогрева'), ('chemical_mixer', 'Химический миксер'), ('processing_workshop', 'Цех переработки'), ('raw_diesel_tank', 'Бак сырой солярки'), ('raw_spindle_tank', 'Бак сырой веретенки'), ('nigrol_tank', 'Бак нигрола'), ('finishing_mixer', 'Песочный миксер'), ('finishing_filter', 'Финишный фильтр'), ('finished_diesel_tank', 'Бак готовой солярки'), ('finished_spindle_tank', 'Бак готовой веретенки'), ('concentrate_reactor', 'Реактор концентрата'), ('oil_blender', 'Блендинговый смеситель'), ('finished_oil_tank', 'Бак товарного масла')], max_length=32),
        ),
        migrations.RunPython(seed_nigrol_loading, migrations.RunPython.noop),
    ]
