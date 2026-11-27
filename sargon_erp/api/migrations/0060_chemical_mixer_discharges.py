import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


def seed_discharge_access(apps, schema_editor):
    alias = schema_editor.connection.alias
    modules = apps.get_model('api', 'Module').objects.using(alias)
    groups = apps.get_model('api', 'AccessGroup').objects.using(alias)
    grants = apps.get_model('api', 'GroupModuleAccess').objects.using(alias)
    permissions = apps.get_model('api', 'Permission').objects.using(alias)
    module, _ = modules.get_or_create(code='chemical-mixer-discharges', defaults={
        'name': 'Выгрузка из химического миксера',
        'description': 'Раздельный учёт выгрузки воды и мусора из химического миксера.',
        'default_path': '/processing/chemical-mixer-discharges',
    })
    group = groups.filter(name='Начальник смены').first()
    if group is not None:
        grant, created = grants.get_or_create(group=group, module=module)
        if created:
            grant.permissions.add(*permissions.filter(code__in=('view', 'create')))


def protect_discharge_history(apps, schema_editor):
    records = apps.get_model('api', 'ChemicalMixerDischarge').objects.using(schema_editor.connection.alias)
    if records.exists():
        raise RuntimeError('Restore a backup to roll back chemical mixer discharge records.')


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0059_chemical_mixer_reagents'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='ChemicalMixerDischarge',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('mixer_name', models.CharField(max_length=120)),
                ('discharge_type', models.CharField(choices=[('water', 'Вода'), ('waste', 'Мусор')], max_length=10)),
                ('quantity', models.DecimalField(decimal_places=3, max_digits=14)),
                ('idempotency_key', models.CharField(max_length=80, unique=True)),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('created_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='chemical_discharges', to=settings.AUTH_USER_MODEL)),
                ('mixer', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='chemical_discharges', to='api.productioncontainer')),
            ],
            options={
                'constraints': [models.CheckConstraint(condition=models.Q(('quantity__gt', 0)), name='chemical_discharge_quantity_positive'), models.CheckConstraint(condition=models.Q(('discharge_type__in', ['water', 'waste'])), name='chemical_discharge_type_valid')],
            },
        ),
        migrations.RunPython(seed_discharge_access, protect_discharge_history),
    ]
