import json
from decimal import Decimal
from importlib import import_module

from django.apps import apps
from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase

from .auth import create_access_token
from .models import (
    AccessGroup, City, GroupModuleAccess, KnowledgeArticle, LaboratoryAnalysis,
    Module, Permission, ProductionContainer, RawMaterialReceipt, ReceiptBatch,
    Supplier, UserProfile,
)


class LaboratoryAnalysisTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.laborant = get_user_model().objects.create_user('laboratory-operator')
        cls.admin = get_user_model().objects.create_superuser('laboratory-admin')
        group = AccessGroup.objects.create(name='Тестовая лаборатория')
        access = GroupModuleAccess.objects.create(group=group, module=Module.objects.get(code='laboratory-analysis'))
        access.permissions.set(Permission.objects.filter(code__in=('view', 'update', 'approve')))
        UserProfile.objects.update_or_create(user=cls.laborant, defaults={'group': group})
        cls.supplier = Supplier.objects.create(
            company_name='Поставщик для анализа', city=City.objects.create(name='Город лаборатории'),
            address='Тестовый адрес', phone='',
        )

    def create_analysis(self, **values):
        receipt = RawMaterialReceipt.objects.create(supplier=self.supplier)
        batch = ReceiptBatch.objects.create(receipt=receipt, sequence_number=1)
        return LaboratoryAnalysis.objects.create(batch=batch, **values)

    def patch_json(self, path, payload, user=None):
        return self.client.patch(
            path, data=json.dumps(payload), content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {create_access_token(user or self.laborant)}',
        )

    def test_approval_accepts_missing_blank_null_and_zero_optional_values(self):
        for optional_values in (
            {}, {'flash_point_temperature': '', 'water_percentage': ''},
            {'flash_point_temperature': None, 'water_percentage': None},
            {'flash_point_temperature': '0'}, {'water_percentage': '0'},
            {'flash_point_temperature': '150.00', 'water_percentage': '100'},
        ):
            with self.subTest(optional_values=optional_values):
                analysis = self.create_analysis()
                response = self.patch_json(f'/api/laboratory/analyses/{analysis.pk}/', {
                    'density': '0.8800', 'current_temperature': '0', 'is_approved': True, **optional_values,
                })
                self.assertEqual(response.status_code, 200, response.content)
                analysis.refresh_from_db()
                self.assertTrue(analysis.is_approved)
                self.assertTrue(analysis.is_filled)
                self.assertIsNotNone(analysis.decided_at)
                for field in ('flash_point_temperature', 'water_percentage'):
                    value = optional_values.get(field)
                    expected = Decimal(value) if value not in (None, '') else None
                    self.assertEqual(getattr(analysis, field), expected)
                    self.assertEqual(response.json()[field], str(expected) if expected is not None else '')

    def test_approval_still_requires_density_and_current_temperature(self):
        for field in ('density', 'current_temperature'):
            for missing_value in (None, ''):
                with self.subTest(field=field, missing_value=missing_value):
                    analysis = self.create_analysis()
                    response = self.patch_json(f'/api/laboratory/analyses/{analysis.pk}/', {
                        'density': '0.8800', 'current_temperature': '20', 'flash_point_temperature': '150',
                        'water_percentage': '1', 'is_approved': True, field: missing_value,
                    })
                    self.assertEqual(response.status_code, 400)
                    analysis.refresh_from_db()
                    self.assertFalse(analysis.is_approved)
                    self.assertFalse(analysis.is_filled)
                    self.assertIsNone(analysis.decided_at)

    def test_invalid_optional_values_are_rejected_without_mutation(self):
        for field, value in (
            ('flash_point_temperature', 'invalid'), ('flash_point_temperature', 'NaN'),
            ('flash_point_temperature', 'Infinity'), ('water_percentage', 'invalid'),
            ('water_percentage', 'NaN'), ('water_percentage', 'Infinity'),
            ('water_percentage', '-0.001'), ('water_percentage', '100.001'),
        ):
            with self.subTest(field=field, value=value):
                analysis = self.create_analysis(
                    density=Decimal('0.8800'), current_temperature=Decimal('20'),
                    flash_point_temperature=Decimal('150'), water_percentage=Decimal('1'),
                )
                response = self.patch_json(f'/api/laboratory/analyses/{analysis.pk}/', {
                    field: value, 'is_approved': True,
                })
                self.assertEqual(response.status_code, 400)
                analysis.refresh_from_db()
                self.assertEqual(analysis.flash_point_temperature, Decimal('150'))
                self.assertEqual(analysis.water_percentage, Decimal('1'))
                self.assertFalse(analysis.is_approved)
                self.assertIsNone(analysis.decided_at)

    def test_required_values_must_remain_valid(self):
        for field, value in (
            ('density', '0'), ('density', '-0.8800'), ('density', 'NaN'),
            ('current_temperature', 'invalid'), ('current_temperature', 'Infinity'),
        ):
            with self.subTest(field=field, value=value):
                analysis = self.create_analysis()
                response = self.patch_json(f'/api/laboratory/analyses/{analysis.pk}/', {
                    'density': '0.8800', 'current_temperature': '20', 'is_approved': True, field: value,
                })
                self.assertEqual(response.status_code, 400)
                analysis.refresh_from_db()
                self.assertFalse(analysis.is_approved)

    def test_optional_values_can_be_cleared_before_approval(self):
        analysis = self.create_analysis(
            density=Decimal('0.8800'), current_temperature=Decimal('20'),
            flash_point_temperature=Decimal('150'), water_percentage=Decimal('1'),
        )
        response = self.patch_json(f'/api/laboratory/analyses/{analysis.pk}/', {
            'flash_point_temperature': '', 'water_percentage': None, 'is_approved': True,
        })
        self.assertEqual(response.status_code, 200)
        analysis.refresh_from_db()
        self.assertIsNone(analysis.flash_point_temperature)
        self.assertIsNone(analysis.water_percentage)
        self.assertTrue(analysis.is_filled)

    def test_required_values_mark_draft_filled_without_deciding(self):
        analysis = self.create_analysis()
        response = self.patch_json(f'/api/laboratory/analyses/{analysis.pk}/', {
            'density': '0.8800', 'current_temperature': '0',
        })
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['is_filled'])
        self.assertTrue(response.json()['batch']['is_analysis_filled'])
        self.assertFalse(response.json()['batch']['can_set_quantity'])
        self.assertFalse(response.json()['is_approved'])
        self.assertFalse(response.json()['is_rejected'])

    def test_rejection_does_not_require_measurements(self):
        analysis = self.create_analysis()
        response = self.patch_json(f'/api/laboratory/analyses/{analysis.pk}/', {'is_rejected': True})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['is_rejected'])
        self.assertFalse(response.json()['is_filled'])

    def test_minimal_approval_enables_receipt_completion_and_preserves_locks(self):
        analysis = self.create_analysis()
        analysis_path = f'/api/laboratory/analyses/{analysis.pk}/'
        response = self.patch_json(analysis_path, {
            'density': '0.8800', 'current_temperature': '20', 'is_approved': True,
        })
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['batch']['can_set_quantity'])
        self.assertEqual(self.patch_json(analysis_path, {'water_percentage': '1'}).status_code, 423)
        batch = analysis.batch
        quantity_response = self.patch_json(f'/api/raw-material/batches/{batch.pk}/', {
            'input_quantity': '88', 'input_unit': 'kilograms',
        }, self.admin)
        self.assertEqual(quantity_response.status_code, 200, quantity_response.content)
        self.assertEqual(Decimal(quantity_response.json()['quantity_liters']), Decimal('100'))
        tank = ProductionContainer.objects.create(
            kind=ProductionContainer.KIND_RECEIVING_TANK, number=90,
            system_code='laboratory-test-tank', capacity_liters=Decimal('1000'),
        )
        completion_response = self.patch_json(f'/api/raw-material/receipts/{batch.receipt_id}/', {
            'is_completed': True,
            'distributions': [{'batch_id': batch.pk, 'tank_id': tank.pk, 'volume_liters': '100'}],
        }, self.admin)
        self.assertEqual(completion_response.status_code, 200, completion_response.content)
        tank.refresh_from_db()
        self.assertEqual(tank.current_volume_liters, Decimal('100'))
        self.assertEqual(self.patch_json(analysis_path, {'water_percentage': '1'}, self.admin).status_code, 423)


class LaboratoryGuideMigrationTests(TestCase):
    def test_seeded_guide_describes_optional_fields(self):
        migration = import_module('api.migrations.0045_update_laboratory_guide')
        seed = import_module('api.migrations.0031_seed_knowledge_base')
        category, title, summary, content = next(
            article for article in seed.ARTICLES if article[1] == 'Проведение анализа и принятие решения'
        )
        guide = KnowledgeArticle.objects.get(title=title, category__name=category)
        self.assertEqual(guide.content, content.replace(migration.OLD_APPROVAL_TEXT, migration.NEW_APPROVAL_TEXT))
        guide.content = content
        guide.save(update_fields=['content'])
        with connection.schema_editor() as schema_editor:
            migration.update_laboratory_guide(apps, schema_editor)
            migration.update_laboratory_guide(apps, schema_editor)
        guide.refresh_from_db()
        self.assertIn(migration.NEW_APPROVAL_TEXT, guide.content)
        self.assertEqual(guide.summary, summary)

    def test_migration_preserves_customized_guide(self):
        migration = import_module('api.migrations.0045_update_laboratory_guide')
        guide = KnowledgeArticle.objects.get(title='Проведение анализа и принятие решения')
        guide.content = 'Инструкция, изменённая пользователем.'
        guide.save(update_fields=['content'])
        with connection.schema_editor() as schema_editor:
            migration.update_laboratory_guide(apps, schema_editor)
        guide.refresh_from_db()
        self.assertEqual(guide.content, 'Инструкция, изменённая пользователем.')
