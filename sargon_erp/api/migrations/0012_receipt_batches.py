from django.db import migrations, models
import django.db.models.deletion


def create_batches_for_existing_receipts(apps, schema_editor):
    RawMaterialReceipt = apps.get_model('api', 'RawMaterialReceipt')
    ReceiptBatch = apps.get_model('api', 'ReceiptBatch')
    LaboratoryAnalysis = apps.get_model('api', 'LaboratoryAnalysis')

    for receipt in RawMaterialReceipt.objects.all().order_by('id'):
        batch, _ = ReceiptBatch.objects.get_or_create(
            receipt=receipt,
            sequence_number=1,
            defaults={
                'input_quantity': receipt.input_quantity,
                'input_unit': receipt.input_unit,
                'quantity_liters': receipt.quantity_liters,
            },
        )
        LaboratoryAnalysis.objects.filter(receipt=receipt, batch__isnull=True).update(batch=batch)


def remove_created_batches(apps, schema_editor):
    ReceiptBatch = apps.get_model('api', 'ReceiptBatch')
    ReceiptBatch.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0011_group_start_module_and_module_default_path'),
    ]

    operations = [
        migrations.CreateModel(
            name='ReceiptBatch',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('sequence_number', models.PositiveIntegerField(default=1)),
                ('input_quantity', models.DecimalField(blank=True, decimal_places=3, max_digits=14, null=True)),
                ('input_unit', models.CharField(choices=[('liters', 'Литры'), ('kilograms', 'Килограммы')], default='liters', max_length=12)),
                ('quantity_liters', models.DecimalField(blank=True, decimal_places=3, max_digits=14, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('receipt', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='batches', to='api.rawmaterialreceipt')),
            ],
            options={
                'ordering': ['receipt_id', 'sequence_number'],
            },
        ),
        migrations.AlterField(
            model_name='laboratoryanalysis',
            name='receipt',
            field=models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='laboratory_analysis', to='api.rawmaterialreceipt'),
        ),
        migrations.AddField(
            model_name='laboratoryanalysis',
            name='batch',
            field=models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='laboratory_analysis', to='api.receiptbatch'),
        ),
        migrations.AddConstraint(
            model_name='receiptbatch',
            constraint=models.UniqueConstraint(fields=('receipt', 'sequence_number'), name='unique_receipt_batch_number'),
        ),
        migrations.RunPython(create_batches_for_existing_receipts, remove_created_batches),
    ]
