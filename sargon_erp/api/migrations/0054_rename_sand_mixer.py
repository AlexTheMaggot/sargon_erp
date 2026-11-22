from importlib import import_module

from django.db import migrations, models


OLD_MODULE_NAME = 'Загрузка финишного миксера'
NEW_MODULE_NAME = 'Загрузка песочного миксера'
GUIDE_REPLACEMENTS = (
    ('финишных миксеров', 'песочных миксеров'),
    ('финишный миксер', 'песочный миксер'),
)


def update_builtin_labels(apps, schema_editor, reverse=False):
    alias = schema_editor.connection.alias
    modules = apps.get_model('api', 'Module').objects.using(alias)
    before, after = (NEW_MODULE_NAME, OLD_MODULE_NAME) if reverse else (OLD_MODULE_NAME, NEW_MODULE_NAME)
    modules.filter(code='finishing-mixer-loading', name=before).update(name=after)

    seed = import_module('api.migrations.0031_seed_knowledge_base')
    separator = import_module('api.migrations.0048_remove_separator')
    route = import_module('api.migrations.0051_refresh_processing_route_guides')
    articles = apps.get_model('api', 'KnowledgeArticle').objects.using(alias)
    for category, title, summary, content in seed.ARTICLES:
        title, summary, content = separator.updated_guide(title, summary, content)
        content = route.updated_content(content)
        renamed = content
        for original, replacement in GUIDE_REPLACEMENTS:
            renamed = renamed.replace(original, replacement)
        if renamed == content:
            continue
        before, after = (renamed, content) if reverse else (content, renamed)
        articles.filter(category__name=category, title=title, summary=summary, content=before).update(content=after)


def reverse_builtin_labels(apps, schema_editor):
    update_builtin_labels(apps, schema_editor, reverse=True)


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0053_seed_container_reconciliation'),
    ]

    operations = [
        migrations.AlterField(
            model_name='materialmovement',
            name='movement_type',
            field=models.CharField(choices=[('receipt_to_tank', 'Поступление из приёмки'), ('tank_to_boiler', 'Загрузка котла'), ('boiler_to_workshop', 'Загрузка в цех переработки'), ('raw_to_chemical_mixer', 'Загрузка химического миксера'), ('chemical_to_finishing_mixer', 'Загрузка песочного миксера'), ('boiler_to_chemical_mixer', 'Загрузка химического миксера (прежний маршрут)'), ('chemical_mixer_to_workshop', 'Загрузка в цех переработки (прежний маршрут)'), ('workshop_to_raw_diesel_tank', 'Загрузка бака сырой солярки'), ('workshop_to_raw_spindle_tank', 'Загрузка бака сырой веретенки'), ('raw_to_finishing_mixer', 'Загрузка песочного миксера (прежний маршрут)'), ('mixer_to_filter', 'Загрузка финишного фильтра'), ('filter_to_finished_tank', 'Загрузка бака готовой продукции'), ('spindle_to_concentrate', 'Загрузка реактора концентрата'), ('spindle_to_blender', 'Загрузка основы в смеситель'), ('concentrate_to_blender', 'Передача концентрата в смеситель'), ('blender_to_oil_tank', 'Перелив товарного масла в бак'), ('oil_filling', 'Розлив товарного масла'), ('compensation', 'Компенсирующее движение')], max_length=32),
        ),
        migrations.AlterField(
            model_name='productioncontainer',
            name='kind',
            field=models.CharField(choices=[('receiving_tank', 'Приёмный бак'), ('preheating_boiler', 'Котёл первичного прогрева'), ('chemical_mixer', 'Химический миксер'), ('processing_workshop', 'Цех переработки'), ('raw_diesel_tank', 'Бак сырой солярки'), ('raw_spindle_tank', 'Бак сырой веретенки'), ('finishing_mixer', 'Песочный миксер'), ('finishing_filter', 'Финишный фильтр'), ('finished_diesel_tank', 'Бак готовой солярки'), ('finished_spindle_tank', 'Бак готовой веретенки'), ('concentrate_reactor', 'Реактор концентрата'), ('oil_blender', 'Блендинговый смеситель'), ('finished_oil_tank', 'Бак товарного масла')], max_length=32),
        ),
        migrations.RunPython(update_builtin_labels, reverse_builtin_labels),
    ]
