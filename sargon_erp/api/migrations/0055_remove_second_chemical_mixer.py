from bisect import bisect_right

from django.db import migrations, models


RETIRED_SNAPSHOT = 'Химический миксер №2'


def remove_mixer_measurements(rows, mixer):
    measurements = rows('ContainerMeasurement')
    revisions = rows('ContainerReconciliationRevision')
    audits = rows('OperationAuditLog')
    entries = list(measurements.filter(container_id=mixer.pk).order_by(
        'revision__number',
    ).values_list('revision_id', 'revision__reconciliation_id', 'revision__number'))
    first_measured_revision = {}
    for _, walk_id, number in entries:
        first_measured_revision.setdefault(walk_id, number)

    activity_changes = []
    for changed_at, changes in audits.filter(
        action='container_updated', object_type='production_container', object_id=str(mixer.pk),
    ).order_by('created_at', 'pk').values_list('created_at', 'changes'):
        previous = changes.get('before', {}).get('is_active')
        current = changes.get('after', {}).get('is_active')
        if isinstance(previous, bool) and isinstance(current, bool) and previous != current:
            activity_changes.append((changed_at, previous))
    change_times = [changed_at for changed_at, _ in activity_changes]
    counted_revisions = []
    for revision_id, walk_id, number, created_at in revisions.filter(
        created_at__gte=mixer.created_at,
    ).values_list('pk', 'reconciliation_id', 'number', 'created_at').iterator():
        next_change = bisect_right(change_times, created_at)
        was_active = activity_changes[next_change][1] if next_change < len(activity_changes) else mixer.is_active
        first_measured = first_measured_revision.get(walk_id)
        if was_active or (first_measured is not None and number >= first_measured):
            counted_revisions.append(revision_id)
    revisions.filter(pk__in=counted_revisions, eligible_count__gt=0).update(
        eligible_count=models.F('eligible_count') - 1,
    )
    measurements.filter(container_id=mixer.pk).delete()
    for revision_id, walk_id, number in entries:
        count = measurements.filter(revision_id=revision_id).count()
        audit_entries = audits.filter(
            action='container_reconciled', object_type='container_reconciliation', object_id=str(walk_id),
            changes__revision=number,
        )
        if count:
            for audit in audit_entries:
                audit.changes = {**audit.changes, 'measured_count': count}
                audit.save(update_fields=['changes'])
        else:
            audit_entries.delete()
            revisions.filter(pk=revision_id).delete()
    for walk_id in first_measured_revision:
        if not revisions.filter(reconciliation_id=walk_id).exists():
            audits.filter(object_type='container_reconciliation', object_id=str(walk_id)).delete()
            rows('ContainerReconciliation').filter(pk=walk_id).delete()


def remove_second_chemical_mixer(apps, schema_editor):
    alias = schema_editor.connection.alias

    def rows(name):
        return apps.get_model('api', name).objects.using(alias)

    with schema_editor.connection.cursor() as cursor:
        cursor.execute('SELECT pg_advisory_xact_lock(%s)', [734092601])
    mixers = rows('ProductionContainer')
    mixer = mixers.select_for_update().filter(kind='chemical_mixer', number=2).first()
    if mixer is not None and mixer.current_volume_liters:
        raise RuntimeError('Empty chemical mixer No. 2 before applying migration 0055; no balances or history have changed.')

    movements = rows('MaterialMovement')
    audits = rows('OperationAuditLog')
    orphaned_snapshots = (
        models.Q(source_container__isnull=True, source_snapshot=RETIRED_SNAPSHOT)
        | models.Q(destination_container__isnull=True, destination_snapshot=RETIRED_SNAPSHOT)
    )
    movement_filter = orphaned_snapshots
    audit_filter = models.Q(
        object_type='production_container', action='container_deleted', changes__name=RETIRED_SNAPSHOT,
    )
    if mixer is not None:
        movement_filter |= models.Q(source_container_id=mixer.pk) | models.Q(destination_container_id=mixer.pk)
        identifiers = [mixer.pk, str(mixer.pk)]
        audit_filter |= models.Q(object_type='production_container', object_id=str(mixer.pk))
        audit_filter |= models.Q(object_type='material_movement') & (
            models.Q(changes__source_id__in=identifiers) | models.Q(changes__destination_id__in=identifiers)
        )
        remove_mixer_measurements(rows, mixer)
    movement_ids = set(movements.filter(movement_filter).values_list('pk', flat=True))
    movement_ids.update(movements.filter(compensates_id__in=movement_ids).values_list('pk', flat=True))
    audit_filter |= models.Q(object_type='material_movement', object_id__in=[str(value) for value in movement_ids])
    audits.filter(audit_filter).delete()
    movements.filter(pk__in=movement_ids, compensates__isnull=False).delete()
    movements.filter(pk__in=movement_ids).delete()
    if mixer is not None:
        mixer.delete()


class Migration(migrations.Migration):
    dependencies = [('api', '0054_rename_sand_mixer')]
    operations = [migrations.RunPython(remove_second_chemical_mixer, migrations.RunPython.noop)]
