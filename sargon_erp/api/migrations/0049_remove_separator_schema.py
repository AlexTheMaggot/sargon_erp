from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0048_remove_separator'),
    ]

    operations = [
        migrations.AlterField(
            model_name='materialmovement',
            name='movement_type',
            field=models.CharField(choices=[('receipt_to_tank', 'Поступление из приёмки'), ('tank_to_boiler', 'Загрузка котла'), ('boiler_to_chemical_mixer', 'Загрузка химического миксера'), ('chemical_mixer_to_workshop', 'Загрузка в цех переработки'), ('workshop_to_raw_diesel_tank', 'Загрузка бака сырой солярки'), ('workshop_to_raw_spindle_tank', 'Загрузка бака сырой веретенки'), ('raw_to_finishing_mixer', 'Загрузка финишного миксера'), ('mixer_to_filter', 'Загрузка финишного фильтра'), ('filter_to_finished_tank', 'Загрузка бака готовой продукции'), ('spindle_to_concentrate', 'Загрузка реактора концентрата'), ('spindle_to_blender', 'Загрузка основы в смеситель'), ('concentrate_to_blender', 'Передача концентрата в смеситель'), ('blender_to_oil_tank', 'Перелив товарного масла в бак'), ('oil_filling', 'Розлив товарного масла'), ('compensation', 'Компенсирующее движение')], max_length=32),
        ),
        migrations.AlterField(
            model_name='productioncontainer',
            name='kind',
            field=models.CharField(choices=[('receiving_tank', 'Приёмный бак'), ('preheating_boiler', 'Котёл первичного прогрева'), ('chemical_mixer', 'Химический миксер'), ('processing_workshop', 'Цех переработки'), ('raw_diesel_tank', 'Бак сырой солярки'), ('raw_spindle_tank', 'Бак сырой веретенки'), ('finishing_mixer', 'Финишный миксер'), ('finishing_filter', 'Финишный фильтр'), ('finished_diesel_tank', 'Бак готовой солярки'), ('finished_spindle_tank', 'Бак готовой веретенки'), ('concentrate_reactor', 'Реактор концентрата'), ('oil_blender', 'Блендинговый смеситель'), ('finished_oil_tank', 'Бак товарного масла')], max_length=32),
        ),
    ]
