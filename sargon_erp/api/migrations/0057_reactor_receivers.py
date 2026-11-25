from importlib import import_module

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


def seed_reactor_receivers(apps, schema_editor):
    alias = schema_editor.connection.alias
    modules = apps.get_model('api', 'Module').objects.using(alias)
    groups = apps.get_model('api', 'AccessGroup').objects.using(alias)
    grants = apps.get_model('api', 'GroupModuleAccess').objects.using(alias)
    permissions = apps.get_model('api', 'Permission').objects.using(alias)
    module, _ = modules.get_or_create(code='reactor-receivers', defaults={
        'name': 'Ресиверы реактора',
        'description': 'Регистрация открытия и закрытия ресиверов реактора переработки.',
        'default_path': '/processing/reactor-receivers',
    })
    group = groups.filter(name='Начальник смены').first()
    if group is not None:
        grant, created = grants.get_or_create(group=group, module=module)
        if created:
            grant.permissions.add(*permissions.filter(code__in=('view', 'create')))
    for code, old_name, new_name in (
        ('workshop-loading', 'Загрузка в цех переработки', 'Загрузка реактора переработки'),
        ('raw-diesel-tank-loading', 'Загрузка бака сырой солярки', 'Слив солярки из ресивера'),
        ('raw-spindle-tank-loading', 'Загрузка бака сырой веретенки', 'Слив веретенки из ресивера'),
    ):
        modules.filter(code=code, name=old_name).update(name=new_name)
    modules.filter(
        code='nigrol-loading', description='Перелив нигрола из общего остатка цеха переработки в отдельный бак.',
    ).update(description='Отгрузка нигрола напрямую из реактора в отдельный бак.')
    for code, before, after in (
        ('workshop-loading', 'Движение прогретого масла из котла первичного прогрева в цех переработки.',
         'Передать прогретое масло из котла в реактор переработки.'),
        ('raw-diesel-tank-loading', 'Движение сырой солярки из цеха переработки в продуктовый бак.',
         'Полностью слить ресивер №1 в бак сырой солярки.'),
        ('raw-spindle-tank-loading', 'Движение сырой веретенки из цеха переработки в продуктовый бак.',
         'Полностью слить выбранный ресивер №2, №3 или №4 в бак сырой веретенки.'),
    ):
        modules.filter(code=code, description=before).update(description=after)


GUIDE_REPLACEMENTS = (
    ('баками, котлами, цехами, баками сырой продукции', 'баками, котлами, реакторами, ресиверами, баками сырой продукции'),
    ('цехов переработки, баков сырой солярки и сырой веретенки', 'реакторов, ресиверов, баков нигрола, сырой солярки и сырой веретенки'),
    ('## Статичные участки\n\nСледующие за баками сырой продукции этапы и схема производства масел пока представлены статично. Не используйте их демонстрационные показатели как фактические остатки.',
     '## Реактор и ресиверы\n\nДля реактора виден последний фактический замер с датой. Для ресиверов видны состояния и время открытия и закрытия, а не остатки в литрах.'),
    ('→ цех переработки → бак сырой солярки или бак сырой веретенки',
     '→ реактор → охладитель → ресивер → бак сырой солярки или бак сырой веретенки'),
    ('Каждая ёмкость хранит свой остаток, а движение оформляется тогда, когда фактически происходит передача масла.',
     'Движение оформляется при фактической передаче масла. Нигрол отгружается напрямую из реактора в отдельный бак.'),
    ('Система уменьшит остаток источника и увеличит остаток получателя в одной операции. Нельзя передать больше имеющегося объёма или превысить вместимость получателя. Для сырой солярки и сырой веретенки используются разные формы, баки и истории движения.',
     'В форме «Ресиверы реактора» подтверждайте открытие и закрытие: после загрузки откройте №1, затем №2 → №3 → №4. До новой загрузки повторяйте №2 → №3 → №4. Закрытый ресивер слейте целиком в один подходящий бак и укажите фактические литры. №1 — сырая солярка, остальные — сырая веретёнка. Остаток реактора указывается фактическим замером при сверке; остатки ресиверов не рассчитываются.'),
)


def refresh_reactor_guides(apps, schema_editor, reverse=False):
    seed = import_module('api.migrations.0031_seed_knowledge_base')
    separator = import_module('api.migrations.0048_remove_separator')
    route = import_module('api.migrations.0051_refresh_processing_route_guides')
    sand_mixer = import_module('api.migrations.0054_rename_sand_mixer')
    articles = apps.get_model('api', 'KnowledgeArticle').objects.using(schema_editor.connection.alias)
    for category, title, summary, content in seed.ARTICLES:
        title, summary, content = separator.updated_guide(title, summary, content)
        content = route.updated_content(content)
        for original, replacement in sand_mixer.GUIDE_REPLACEMENTS:
            content = content.replace(original, replacement)
        updated = content
        for original, replacement in GUIDE_REPLACEMENTS:
            updated = updated.replace(original, replacement)
        if content != updated:
            before, after = (updated, content) if reverse else (content, updated)
            articles.filter(category__name=category, title=title, summary=summary, content=before).update(content=after)


def reverse_reactor_guides(apps, schema_editor):
    refresh_reactor_guides(apps, schema_editor, reverse=True)


def protect_receiver_history(apps, schema_editor):
    alias = schema_editor.connection.alias
    movements = apps.get_model('api', 'MaterialMovement').objects.using(alias)
    measurements = apps.get_model('api', 'ContainerMeasurement').objects.using(alias)
    if (movements.filter(movement_type__in=(
            'boiler_to_reactor', 'receiver_to_raw_diesel_tank', 'receiver_to_raw_spindle_tank', 'reactor_to_nigrol_tank',
    )).exists() or measurements.filter(expected_liters__isnull=True).exists()):
        raise RuntimeError('Откат удалит новые данные реакторов или ресиверов. Сначала сохраните данные.')


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0056_nigrol_tank_loading'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name='containermeasurement',
            name='expected_liters',
            field=models.DecimalField(decimal_places=3, max_digits=14, null=True),
        ),
        migrations.AlterField(
            model_name='materialmovement',
            name='movement_type',
            field=models.CharField(choices=[('receipt_to_tank', 'Поступление из приёмки'), ('tank_to_boiler', 'Загрузка котла'), ('boiler_to_workshop', 'Загрузка в цех переработки'), ('boiler_to_reactor', 'Загрузка реактора переработки'), ('receiver_to_raw_diesel_tank', 'Слив солярки из ресивера'), ('receiver_to_raw_spindle_tank', 'Слив веретенки из ресивера'), ('reactor_to_nigrol_tank', 'Отгрузка нигрола из реактора'), ('raw_to_chemical_mixer', 'Загрузка химического миксера'), ('chemical_to_finishing_mixer', 'Загрузка песочного миксера'), ('boiler_to_chemical_mixer', 'Загрузка химического миксера (прежний маршрут)'), ('chemical_mixer_to_workshop', 'Загрузка в цех переработки (прежний маршрут)'), ('workshop_to_raw_diesel_tank', 'Загрузка бака сырой солярки'), ('workshop_to_raw_spindle_tank', 'Загрузка бака сырой веретенки'), ('workshop_to_nigrol_tank', 'Отгрузка нигрола'), ('raw_to_finishing_mixer', 'Загрузка песочного миксера (прежний маршрут)'), ('mixer_to_filter', 'Загрузка финишного фильтра'), ('filter_to_finished_tank', 'Загрузка бака готовой продукции'), ('spindle_to_concentrate', 'Загрузка реактора концентрата'), ('spindle_to_blender', 'Загрузка основы в смеситель'), ('concentrate_to_blender', 'Передача концентрата в смеситель'), ('blender_to_oil_tank', 'Перелив товарного масла в бак'), ('oil_filling', 'Розлив товарного масла'), ('compensation', 'Компенсирующее движение')], max_length=32),
        ),
        migrations.AlterField(
            model_name='productioncontainer',
            name='kind',
            field=models.CharField(choices=[('receiving_tank', 'Приёмный бак'), ('preheating_boiler', 'Котёл первичного прогрева'), ('chemical_mixer', 'Химический миксер'), ('processing_workshop', 'Реактор переработки'), ('raw_diesel_tank', 'Бак сырой солярки'), ('raw_spindle_tank', 'Бак сырой веретенки'), ('nigrol_tank', 'Бак нигрола'), ('finishing_mixer', 'Песочный миксер'), ('finishing_filter', 'Финишный фильтр'), ('finished_diesel_tank', 'Бак готовой солярки'), ('finished_spindle_tank', 'Бак готовой веретенки'), ('concentrate_reactor', 'Реактор концентрата'), ('oil_blender', 'Блендинговый смеситель'), ('finished_oil_tank', 'Бак товарного масла')], max_length=32),
        ),
        migrations.CreateModel(
            name='ReceiverRun',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('number', models.PositiveSmallIntegerField()),
                ('opened_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('closed_at', models.DateTimeField(blank=True, null=True)),
                ('open_key', models.CharField(max_length=80, unique=True)),
                ('close_key', models.CharField(blank=True, max_length=80, null=True, unique=True)),
                ('closed_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='closed_receiver_runs', to=settings.AUTH_USER_MODEL)),
                ('loading', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='receiver_runs_started', to='api.materialmovement')),
                ('opened_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='opened_receiver_runs', to=settings.AUTH_USER_MODEL)),
                ('reactor', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='receiver_runs', to='api.productioncontainer')),
            ],
        ),
        migrations.AddField(
            model_name='materialmovement',
            name='receiver_run',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='discharges', to='api.receiverrun'),
        ),
        migrations.AddConstraint(
            model_name='materialmovement',
            constraint=models.UniqueConstraint(condition=models.Q(('is_compensated', False), ('receiver_run__isnull', False)), fields=('receiver_run',), name='one_active_discharge_per_receiver_run'),
        ),
        migrations.AddConstraint(
            model_name='materialmovement',
            constraint=models.CheckConstraint(condition=models.Q(models.Q(('destination_container__isnull', False), ('movement_type__in', ['receiver_to_raw_diesel_tank', 'receiver_to_raw_spindle_tank']), ('receiver_run__isnull', False), ('source_container__isnull', True)), models.Q(models.Q(('movement_type__in', ['receiver_to_raw_diesel_tank', 'receiver_to_raw_spindle_tank']), _negated=True), ('receiver_run__isnull', True)), _connector='OR'), name='receiver_discharge_requires_run'),
        ),
        migrations.AddConstraint(
            model_name='receiverrun',
            constraint=models.CheckConstraint(condition=models.Q(('number__range', (1, 4))), name='receiver_number_in_range'),
        ),
        migrations.AddConstraint(
            model_name='receiverrun',
            constraint=models.UniqueConstraint(condition=models.Q(('closed_at__isnull', True)), fields=('reactor',), name='one_open_receiver_per_reactor'),
        ),
        migrations.AddConstraint(
            model_name='receiverrun',
            constraint=models.CheckConstraint(condition=models.Q(models.Q(('close_key__isnull', True), ('closed_at__isnull', True)), models.Q(('close_key__isnull', False), ('closed_at__gte', models.F('opened_at')), ('closed_at__isnull', False)), _connector='OR'), name='receiver_close_after_open'),
        ),
        migrations.RunPython(refresh_reactor_guides, reverse_reactor_guides),
        migrations.RunPython(seed_reactor_receivers, protect_receiver_history),
    ]
