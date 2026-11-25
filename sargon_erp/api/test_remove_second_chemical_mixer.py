from datetime import timedelta

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.utils import timezone


PREVIOUS = ('api', '0054_rename_sand_mixer')
CURRENT = ('api', '0055_remove_second_chemical_mixer')


class RemoveSecondChemicalMixerTests(TransactionTestCase):
    def setUp(self):
        executor = MigrationExecutor(connection)
        executor.migrate([PREVIOUS])
        self.old_apps = executor.loader.project_state([PREVIOUS]).apps
        self.mixer, _ = self.model('ProductionContainer').objects.get_or_create(
            kind='chemical_mixer', number=2,
            defaults={'system_code': 'chemical-mixer-2', 'capacity_liters': 100},
        )

    def tearDown(self):
        self.model('ProductionContainer').objects.filter(pk=self.mixer.pk).update(current_volume_liters=0, oil_product='')
        MigrationExecutor(connection).migrate([('api', '0057_reactor_receivers')])
        super().tearDown()

    def model(self, name):
        return self.old_apps.get_model('api', name)

    def test_nonempty_mixer_blocks_removal(self):
        self.mixer.current_volume_liters = 5
        self.mixer.oil_product = 'diesel'
        self.mixer.save()
        with self.assertRaisesMessage(RuntimeError, 'Empty chemical mixer No. 2'):
            MigrationExecutor(connection).migrate([CURRENT])
        self.mixer.refresh_from_db()
        self.assertEqual(self.mixer.current_volume_liters, 5)

    def test_removes_only_related_history_and_preserves_other_balances(self):
        Mover = self.model('MaterialMovement')
        Container = self.model('ProductionContainer')
        Audit = self.model('OperationAuditLog')
        Walk = self.model('ContainerReconciliation')
        Revision = self.model('ContainerReconciliationRevision')
        Measurement = self.model('ContainerMeasurement')
        mixer_one, _ = Container.objects.get_or_create(
            kind='chemical_mixer', number=1,
            defaults={'system_code': 'chemical-mixer-1', 'capacity_liters': 100},
        )
        raw_tank = Container.objects.create(
            kind='raw_diesel_tank', number=982, system_code='raw-diesel-tank-982',
            current_volume_liters=35, capacity_liters=100,
        )
        same_number_tank = Container.objects.create(
            kind='raw_diesel_tank', number=2, system_code='raw-diesel-tank-2', capacity_liters=100,
        )
        removed = Mover.objects.create(
            movement_number='REMOVE-MIXER-LOAD', movement_type='raw_to_chemical_mixer', volume_liters=4,
            source_container=raw_tank, destination_container=self.mixer, is_compensated=True,
        )
        reversal = Mover.objects.create(
            movement_number='REMOVE-MIXER-REVERSAL', movement_type='compensation', volume_liters=4,
            source_container=self.mixer, destination_container=raw_tank, compensates=removed,
        )
        orphan = Mover.objects.create(
            movement_number='REMOVE-MIXER-SNAPSHOT', movement_type='chemical_to_finishing_mixer',
            volume_liters=1, source_snapshot='Химический миксер №2',
        )
        kept = Mover.objects.create(
            movement_number='KEEP-MIXER-LOAD', movement_type='raw_to_chemical_mixer', volume_liters=1,
            source_container=raw_tank, destination_container=mixer_one,
        )
        removed_audit = Audit.objects.create(action='movement_created', object_type='material_movement', object_id=str(removed.pk))
        rejected_audit = Audit.objects.create(
            action='movement_rejected', object_type='material_movement', changes={'source_id': self.mixer.pk},
        )
        container_audit = Audit.objects.create(action='container_created', object_type='production_container', object_id=str(self.mixer.pk))
        kept_audit = Audit.objects.create(action='movement_created', object_type='material_movement', object_id=str(kept.pk))
        kept_container_audit = Audit.objects.create(
            action='container_deleted', object_type='production_container', object_id=str(same_number_tank.pk),
            changes={'name': 'Бак сырой солярки №2'},
        )

        def add_measurement(revision, container):
            return Measurement.objects.create(
                revision=revision, container=container, container_name='Equipment snapshot',
                expected_liters=0, previous_liters=0, actual_liters=0,
            )

        def add_revision(walk, number, eligible, count, created_at=None):
            revision = Revision.objects.create(
                reconciliation=walk, number=number, eligible_count=eligible,
                operator_name='operator', created_at=created_at or timezone.now(),
            )
            audit = Audit.objects.create(
                action='container_reconciled', object_type='container_reconciliation', object_id=str(walk.pk),
                changes={'revision': number, 'measured_count': count},
            )
            return revision, audit

        walk = Walk.objects.create()
        mixed, mixed_audit = add_revision(walk, 1, 4, 2)
        add_measurement(mixed, self.mixer)
        kept_measurement = add_measurement(mixed, mixer_one)
        removed_revision, revision_audit = add_revision(walk, 2, 4, 1)
        add_measurement(removed_revision, self.mixer)
        removed_walk = Walk.objects.create()
        only_mixer, only_audit = add_revision(removed_walk, 1, 4, 1)
        add_measurement(only_mixer, self.mixer)
        before_mixer, _ = add_revision(Walk.objects.create(), 1, 3, 1, self.mixer.created_at - timedelta(days=1))
        add_measurement(before_mixer, raw_tank)
        self.mixer.is_active = False
        self.mixer.save(update_fields=['is_active'])
        inactive_log = Audit.objects.create(
            action='container_updated', object_type='production_container', object_id=str(self.mixer.pk),
            changes={'before': {'is_active': True}, 'after': {'is_active': False}},
        )
        unmeasured, _ = add_revision(Walk.objects.create(), 1, 3, 1)
        add_measurement(unmeasured, raw_tank)
        supplemental, _ = add_revision(walk, 3, 4, 1)
        add_measurement(supplemental, raw_tank)

        MigrationExecutor(connection).migrate([CURRENT])
        self.assertFalse(Container.objects.filter(pk=self.mixer.pk).exists())
        self.assertEqual(Container.objects.filter(pk__in=[mixer_one.pk, same_number_tank.pk]).count(), 2)
        raw_tank.refresh_from_db()
        self.assertEqual(raw_tank.current_volume_liters, 35)
        self.assertTrue(Mover.objects.filter(pk=kept.pk).exists())
        self.assertFalse(Mover.objects.filter(pk__in=[removed.pk, reversal.pk, orphan.pk]).exists())
        self.assertFalse(Audit.objects.filter(pk__in=[
            removed_audit.pk, rejected_audit.pk, container_audit.pk, revision_audit.pk, only_audit.pk, inactive_log.pk,
        ]).exists())
        self.assertEqual(Audit.objects.filter(pk__in=[kept_audit.pk, kept_container_audit.pk]).count(), 2)
        self.assertFalse(Walk.objects.filter(pk=removed_walk.pk).exists())
        self.assertTrue(Walk.objects.filter(pk=walk.pk).exists())
        self.assertFalse(Revision.objects.filter(pk__in=[removed_revision.pk, only_mixer.pk]).exists())
        self.assertTrue(Measurement.objects.filter(pk=kept_measurement.pk).exists())
        for revision in (mixed, supplemental, before_mixer, unmeasured):
            revision.refresh_from_db()
            self.assertEqual(revision.eligible_count, 3)
        mixed_audit.refresh_from_db()
        self.assertEqual(mixed_audit.changes, {'revision': 1, 'measured_count': 1})
