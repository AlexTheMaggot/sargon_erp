from django.db import migrations, models


def require_empty_chemical_mixers(apps, schema_editor):
    containers = apps.get_model('api', 'ProductionContainer').objects.using(schema_editor.connection.alias)
    if containers.filter(kind='chemical_mixer', current_volume_liters__gt=0).exists():
        raise RuntimeError('Empty chemical mixers using the previous route before applying migration 0050. Balances and history have not been changed.')


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0049_remove_separator_schema'),
    ]

    operations = [
        migrations.RunPython(require_empty_chemical_mixers, migrations.RunPython.noop),
        migrations.RemoveConstraint(
            model_name='productioncontainer',
            name='production_container_oil_product_valid',
        ),
        migrations.AlterField(
            model_name='materialmovement',
            name='movement_type',
            field=models.CharField(choices=[('receipt_to_tank', 'Поступление из приёмки'), ('tank_to_boiler', 'Загрузка котла'), ('boiler_to_workshop', 'Загрузка в цех переработки'), ('raw_to_chemical_mixer', 'Загрузка химического миксера'), ('chemical_to_finishing_mixer', 'Загрузка финишного миксера'), ('boiler_to_chemical_mixer', 'Загрузка химического миксера (прежний маршрут)'), ('chemical_mixer_to_workshop', 'Загрузка в цех переработки (прежний маршрут)'), ('workshop_to_raw_diesel_tank', 'Загрузка бака сырой солярки'), ('workshop_to_raw_spindle_tank', 'Загрузка бака сырой веретенки'), ('raw_to_finishing_mixer', 'Загрузка финишного миксера (прежний маршрут)'), ('mixer_to_filter', 'Загрузка финишного фильтра'), ('filter_to_finished_tank', 'Загрузка бака готовой продукции'), ('spindle_to_concentrate', 'Загрузка реактора концентрата'), ('spindle_to_blender', 'Загрузка основы в смеситель'), ('concentrate_to_blender', 'Передача концентрата в смеситель'), ('blender_to_oil_tank', 'Перелив товарного масла в бак'), ('oil_filling', 'Розлив товарного масла'), ('compensation', 'Компенсирующее движение')], max_length=32),
        ),
        migrations.AddConstraint(
            model_name='productioncontainer',
            constraint=models.CheckConstraint(condition=models.Q(models.Q(('current_volume_liters__gt', 0), ('kind__in', ['chemical_mixer', 'finishing_mixer', 'finishing_filter']), ('oil_product__in', ['diesel', 'spindle'])), models.Q(('current_volume_liters', 0), ('kind__in', ['chemical_mixer', 'finishing_mixer', 'finishing_filter']), ('oil_product', '')), models.Q(models.Q(('kind__in', ['chemical_mixer', 'finishing_mixer', 'finishing_filter']), _negated=True), ('oil_product', '')), _connector='OR'), name='production_container_oil_product_valid'),
        ),
    ]
