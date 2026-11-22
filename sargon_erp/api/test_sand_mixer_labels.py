from importlib import import_module
from types import SimpleNamespace

from django.apps import apps
from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase

from .auth import create_access_token
from .models import ContainerMeasurement, ContainerReconciliation, ContainerReconciliationRevision, KnowledgeArticle, MaterialMovement, Module, OperationAuditLog, ProductionContainer


class SandMixerLabelTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser('sand-mixer-label-test')
        self.headers = {'HTTP_AUTHORIZATION': f'Bearer {create_access_token(self.user)}'}
        self.mixer = ProductionContainer.objects.create(
            kind='finishing_mixer', number=994, system_code='finishing-mixer-994', capacity_liters=100,
        )

    def test_new_name_in_equipment_and_legacy_history_without_rewriting_snapshots(self):
        old_label = 'Финишный миксер №994'
        new_label = 'Песочный миксер №994'
        movement = MaterialMovement.objects.create(
            movement_number='OLD-MIXER-LABEL', movement_type='mixer_to_filter',
            source_container=self.mixer, source_snapshot=old_label, destination_snapshot='Финишный фильтр №1',
            volume_liters=1, system_description='Загрузка финишного миксера',
        )
        tanks = self.client.get('/api/processing/oil-containers/finishing-mixers/', **self.headers)
        tank = next(row for row in tanks.json()['items'] if row['id'] == self.mixer.pk)
        self.assertEqual((tank['name'], tank['kind']), (new_label, 'finishing_mixer'))
        for search in ({'source': 'Песочный'}, {'query': new_label}, {'query': old_label}):
            with self.subTest(search=search):
                response = self.client.get('/api/processing/journal/', search, **self.headers)
                self.assertEqual(response.status_code, 200, response.content)
                self.assertEqual(response.json()['items'][0]['source'], new_label)
                self.assertEqual(response.json()['items'][0]['destination'], 'Финишный фильтр №1')
        walk = ContainerReconciliation.objects.create()
        revision = ContainerReconciliationRevision.objects.create(
            reconciliation=walk, number=1, created_by=self.user, operator_name=self.user.username, eligible_count=1,
        )
        measurement = ContainerMeasurement.objects.create(
            revision=revision, container=self.mixer, container_name=old_label,
            expected_liters=0, previous_liters=0, actual_liters=0,
        )
        history = self.client.get(f'/api/processing/container-reconciliations/{walk.pk}/', **self.headers)
        self.assertEqual(history.json()['measurements'][0]['name'], new_label)
        audit = OperationAuditLog.objects.create(
            action='container_deleted', object_type='production_container', object_id=str(self.mixer.pk),
            user=self.user, changes={'name': old_label},
        )
        journal = self.client.get('/api/processing/journal/', **self.headers).json()
        audit_row = next(row for row in journal['items'] if row['entry_type'] == 'audit')
        self.assertEqual(audit_row['changes']['name'], new_label)
        movement.refresh_from_db()
        measurement.refresh_from_db()
        audit.refresh_from_db()
        self.assertEqual(movement.source_snapshot, old_label)
        self.assertEqual(measurement.container_name, old_label)
        self.assertEqual(audit.changes['name'], old_label)

    def test_migration_updates_only_standard_labels(self):
        migration = import_module('api.migrations.0054_rename_sand_mixer')
        schema_editor = SimpleNamespace(connection=connection)
        module = Module.objects.get(code='finishing-mixer-loading')
        expected_guide = KnowledgeArticle.objects.get(title='Движение масла по производственным ёмкостям')
        edited_guide = KnowledgeArticle.objects.get(title='Что показывает страница «Обзор»')
        self.assertEqual(module.name, migration.NEW_MODULE_NAME)
        self.assertIn('→ песочный миксер →', expected_guide.content)
        migration.reverse_builtin_labels(apps, schema_editor)
        edited_guide.refresh_from_db()
        edited_guide.content += '\n\nСобственное примечание.'
        edited_guide.save(update_fields=['content'])
        custom_content = edited_guide.content
        for _ in range(2):
            migration.update_builtin_labels(apps, schema_editor)
        module.refresh_from_db()
        expected_guide.refresh_from_db()
        edited_guide.refresh_from_db()
        self.assertEqual(module.name, migration.NEW_MODULE_NAME)
        self.assertEqual(module.default_path, '/processing/finishing-mixer-loading')
        self.assertIn('→ песочный миксер →', expected_guide.content)
        self.assertEqual(edited_guide.content, custom_content)
        module.name = 'Локальное название операции'
        module.save(update_fields=['name'])
        migration.update_builtin_labels(apps, schema_editor)
        module.refresh_from_db()
        self.assertEqual(module.name, 'Локальное название операции')
