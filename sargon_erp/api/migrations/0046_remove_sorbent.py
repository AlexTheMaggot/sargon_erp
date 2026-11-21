from django.db import migrations, models


def remove_sorbent_data(apps, schema_editor):
    alias = schema_editor.connection.alias

    def rows(name):
        return apps.get_model('api', name).objects.using(alias)

    container_ids = set(rows('ProductionContainer').filter(kind='sorption_system').values_list('pk', flat=True))
    item_ids = set(rows('InventoryItem').filter(
        models.Q(production_material='sorbent') | models.Q(name__icontains='сорбент') | models.Q(name__icontains='sorbent'),
    ).values_list('pk', flat=True))
    document_ids = set(rows('WarehouseDocument').filter(
        models.Q(production_target='sorption') | models.Q(lines__item_id__in=item_ids)
        | models.Q(movements__item_id__in=item_ids),
    ).values_list('pk', flat=True))
    movement_ids = set(rows('MaterialMovement').filter(
        models.Q(movement_type__in=('raw_to_sorption', 'sorption_to_mixer'))
        | models.Q(source_container_id__in=container_ids) | models.Q(destination_container_id__in=container_ids),
    ).values_list('pk', flat=True))
    movement_ids.update(rows('MaterialMovement').filter(compensates_id__in=movement_ids).values_list('pk', flat=True))

    rows('SorbentMovement').filter(reversal_of__isnull=False).delete()
    rows('SorbentMovement').all().delete()
    rows('MaterialMovement').filter(pk__in=movement_ids, compensates__isnull=False).delete()
    rows('MaterialMovement').filter(pk__in=movement_ids).delete()
    rows('ProductionContainer').filter(pk__in=container_ids).delete()

    rows('WarehouseMovement').filter(item_id__in=item_ids).delete()
    rows('WarehouseDocumentLine').filter(item_id__in=item_ids).delete()
    rows('WarehouseBalance').filter(item_id__in=item_ids).delete()
    rows('InventoryItem').filter(pk__in=item_ids).delete()
    empty_documents = rows('WarehouseDocument').filter(pk__in=document_ids, lines__isnull=True, movements__isnull=True)
    deleted_document_ids = list(empty_documents.values_list('pk', flat=True))
    empty_documents.delete()
    rows('WarehouseDocument').filter(pk__in=document_ids, production_target='sorption').update(
        production_target='', purpose='Внутренний расход материалов.',
    )

    removed_codes = ('sorbent-loading', 'sorbent-cycle', 'sorption-loading')
    removed_module_ids = list(rows('Module').filter(code__in=removed_codes).values_list('pk', flat=True))
    rows('Module').filter(pk__in=removed_module_ids).delete()
    audit_filter = models.Q(object_type='sorbent_movement') | models.Q(action__in=('sorbent_moved', 'sorbent_reversed'))
    for object_type, identifiers in (
        ('material_movement', movement_ids), ('production_container', container_ids),
        ('inventory_item', item_ids), ('warehouse_document', deleted_document_ids), ('module', removed_module_ids),
    ):
        audit_filter |= models.Q(object_type=object_type, object_id__in=[str(value) for value in identifiers])
    rows('OperationAuditLog').filter(audit_filter).delete()
    apps.get_model('contenttypes', 'ContentType').objects.using(alias).filter(app_label='api', model='sorbentmovement').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0045_update_laboratory_guide'),
        ('contenttypes', '0002_remove_content_type_name'),
    ]

    operations = [migrations.RunPython(remove_sorbent_data, migrations.RunPython.noop)]
