import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0051_refresh_processing_route_guides'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='ContainerReconciliation',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now)),
            ],
        ),
        migrations.CreateModel(
            name='ContainerReconciliationRevision',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('number', models.PositiveIntegerField()),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('operator_name', models.CharField(max_length=150)),
                ('eligible_count', models.PositiveIntegerField()),
                ('created_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
                ('reconciliation', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='revisions', to='api.containerreconciliation')),
            ],
        ),
        migrations.CreateModel(
            name='ContainerMeasurement',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('container_name', models.CharField(max_length=120)),
                ('expected_liters', models.DecimalField(decimal_places=3, max_digits=14)),
                ('previous_liters', models.DecimalField(decimal_places=3, max_digits=14)),
                ('actual_liters', models.DecimalField(decimal_places=3, max_digits=14)),
                ('previous_product', models.CharField(blank=True, max_length=10)),
                ('actual_product', models.CharField(blank=True, max_length=10)),
                ('movement_watermark', models.PositiveBigIntegerField(default=0)),
                ('container', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='measurements', to='api.productioncontainer')),
                ('revision', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='measurements', to='api.containerreconciliationrevision')),
            ],
        ),
        migrations.AddConstraint(
            model_name='containerreconciliationrevision',
            constraint=models.UniqueConstraint(fields=('reconciliation', 'number'), name='unique_container_reconciliation_revision'),
        ),
        migrations.AddConstraint(
            model_name='containermeasurement',
            constraint=models.UniqueConstraint(fields=('revision', 'container'), name='unique_container_measurement_in_revision'),
        ),
        migrations.AddConstraint(
            model_name='containermeasurement',
            constraint=models.CheckConstraint(condition=models.Q(('actual_liters__gte', 0), ('expected_liters__gte', 0), ('previous_liters__gte', 0)), name='container_measurement_volumes_nonnegative'),
        ),
    ]
