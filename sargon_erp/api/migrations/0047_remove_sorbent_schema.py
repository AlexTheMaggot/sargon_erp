from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0046_remove_sorbent'),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name='sorbentmovement',
            name='sorbent_movement_quantity_positive',
        ),
        migrations.RemoveConstraint(
            model_name='sorbentmovement',
            name='sorbent_movement_reversal_link',
        ),
        migrations.RemoveConstraint(
            model_name='productioncontainer',
            name='production_container_oil_product_valid',
        ),
        migrations.AlterField(
            model_name='inventoryitem',
            name='production_material',
            field=models.CharField(blank=True, choices=[('', 'Не используется в производственной загрузке'), ('granules', 'Гранулы'), ('dye', 'Краситель'), ('polypropylene', 'Полипропилен')], default='', max_length=20),
        ),
        migrations.AlterField(
            model_name='materialmovement',
            name='movement_type',
            field=models.CharField(choices=[('receipt_to_tank', 'Поступление из приёмки'), ('tank_to_boiler', 'Загрузка котла'), ('boiler_to_separator', 'Загрузка сепаратора'), ('separator_output', 'Отгрузка сепаратора'), ('separator_to_chemical_mixer', 'Загрузка химического миксера'), ('chemical_mixer_to_workshop', 'Загрузка в цех переработки'), ('workshop_to_raw_diesel_tank', 'Загрузка бака сырой солярки'), ('workshop_to_raw_spindle_tank', 'Загрузка бака сырой веретенки'), ('raw_to_finishing_mixer', 'Загрузка финишного миксера'), ('mixer_to_filter', 'Загрузка финишного фильтра'), ('filter_to_finished_tank', 'Загрузка бака готовой продукции'), ('spindle_to_concentrate', 'Загрузка реактора концентрата'), ('spindle_to_blender', 'Загрузка основы в смеситель'), ('concentrate_to_blender', 'Передача концентрата в смеситель'), ('blender_to_oil_tank', 'Перелив товарного масла в бак'), ('oil_filling', 'Розлив товарного масла'), ('compensation', 'Компенсирующее движение')], max_length=32),
        ),
        migrations.AlterField(
            model_name='productioncontainer',
            name='kind',
            field=models.CharField(choices=[('receiving_tank', 'Приёмный бак'), ('preheating_boiler', 'Котёл первичного прогрева'), ('separator', 'Сепаратор'), ('chemical_mixer', 'Химический миксер'), ('processing_workshop', 'Цех переработки'), ('raw_diesel_tank', 'Бак сырой солярки'), ('raw_spindle_tank', 'Бак сырой веретенки'), ('finishing_mixer', 'Финишный миксер'), ('finishing_filter', 'Финишный фильтр'), ('finished_diesel_tank', 'Бак готовой солярки'), ('finished_spindle_tank', 'Бак готовой веретенки'), ('concentrate_reactor', 'Реактор концентрата'), ('oil_blender', 'Блендинговый смеситель'), ('finished_oil_tank', 'Бак товарного масла')], max_length=32),
        ),
        migrations.AlterField(
            model_name='warehousedocument',
            name='production_target',
            field=models.CharField(blank=True, choices=[('canisters', 'Производство канистр'), ('caps', 'Производство крышек'), ('oil_concentrate', 'Приготовление концентрата')], default='', max_length=20),
        ),
        migrations.AddConstraint(
            model_name='productioncontainer',
            constraint=models.CheckConstraint(condition=models.Q(models.Q(('current_volume_liters__gt', 0), ('kind__in', ['finishing_mixer', 'finishing_filter']), ('oil_product__in', ['diesel', 'spindle'])), models.Q(('current_volume_liters', 0), ('kind__in', ['finishing_mixer', 'finishing_filter']), ('oil_product', '')), models.Q(models.Q(('kind__in', ['finishing_mixer', 'finishing_filter']), _negated=True), ('oil_product', '')), _connector='OR'), name='production_container_oil_product_valid'),
        ),
        migrations.DeleteModel(
            name='SorbentMovement',
        ),
    ]
