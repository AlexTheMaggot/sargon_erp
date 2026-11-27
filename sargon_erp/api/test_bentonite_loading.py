from decimal import Decimal
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase

from .auth import create_access_token
from .models import (
    AccessGroup, InventoryCategory, InventoryItem, MaterialMovement, ProductionContainer,
    UnitOfMeasure, UserProfile, Warehouse, WarehouseBalance, WarehouseDocument, WarehouseMovement,
)


LOADINGS = '/api/warehouse/production-loadings/bentonite_filter/'
PREVIOUS_MIGRATION = ('api', '0057_reactor_receivers')
FLOW_FILTER_MIGRATION = ('api', '0058_flow_through_finishing_filter')


class BentoniteLoadingTests(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_superuser('bentonite-test-admin')
        self.operator = get_user_model().objects.create_user('bentonite-test-operator')
        UserProfile.objects.filter(user=self.operator).update(group=AccessGroup.objects.get(name='Начальник смены'))
        self.headers = {'HTTP_AUTHORIZATION': f'Bearer {create_access_token(self.operator)}'}
        self.admin_headers = {'HTTP_AUTHORIZATION': f'Bearer {create_access_token(self.admin)}'}
        self.filter = ProductionContainer.objects.create(kind='finishing_filter', number=99, system_code='bentonite-test-filter')
        self.warehouse = Warehouse.objects.create(name='Bentonite test warehouse')
        unit = UnitOfMeasure.objects.get(symbol='кг')
        category = InventoryCategory.objects.get(name='Сырьё')
        self.bentonite = InventoryItem.objects.create(name='Bentonite test item', category=category, unit=unit, production_material='bentonite')
        self.bentonite.permanent_warehouses.add(self.warehouse)
        self.balance = WarehouseBalance.objects.create(warehouse=self.warehouse, item=self.bentonite, quantity=10000, average_unit_cost=12)
        self.other_item = InventoryItem.objects.create(name='Other test material', category=category, unit=unit, production_material='granules')
        self.other_item.permanent_warehouses.add(self.warehouse)
        WarehouseBalance.objects.create(warehouse=self.warehouse, item=self.other_item, quantity=999)

    def payload(self, **updates):
        return {
            'source_warehouse_id': self.warehouse.pk,
            'lines': [{'item_id': self.bentonite.pk, 'quantity': '10.25'}],
            'idempotency_key': str(uuid4()),
            **updates,
        }

    def post(self, payload):
        return self.client.post(LOADINGS, payload, content_type='application/json', **self.headers)

    def test_scoped_loading_records_warehouse_issue_once_and_history_in_kg(self):
        self.assertEqual(self.client.get(LOADINGS + 'reference-data/').status_code, 401)
        self.assertEqual(self.client.get('/api/warehouse/overview/', **self.headers).status_code, 403)
        reference = self.client.get(LOADINGS + 'reference-data/', **self.headers).json()
        self.assertEqual(reference['filter_name'], self.filter.display_name)
        self.assertEqual([item['item']['id'] for item in reference['materials']], [self.bentonite.pk])
        self.assertNotIn('production_balances', reference)
        payload = self.payload()
        first = self.post(payload)
        self.assertEqual(first.status_code, 201, first.content)
        self.assertEqual(self.post(payload).status_code, 200)
        self.balance.refresh_from_db()
        self.assertEqual(self.balance.quantity, Decimal('9989.75'))
        self.assertEqual(self.balance.average_unit_cost, 12)
        document = WarehouseDocument.objects.get(pk=first.json()['id'])
        self.assertEqual(document.production_filter, self.filter)
        self.assertEqual(document.posted_by, self.operator)
        movement = document.movements.get()
        self.assertEqual(movement.quantity_delta, Decimal('-10.25'))
        self.assertEqual(movement.unit_cost, 12)
        saved = self.client.get(LOADINGS, **self.headers).json()['items'][0]
        self.assertEqual(saved['lines'][0]['quantity'], '10.25')
        self.assertEqual(saved['filter_name'], self.filter.display_name)
        self.assertNotIn('material_cost', saved)
        overview = self.client.get('/api/dashboard/overview/', **self.admin_headers).json()
        self.assertEqual(overview['oil_finishing']['finishing_filter']['last_bentonite_kg'], '10.25')
        self.assertEqual(MaterialMovement.objects.count(), 0)

    def test_invalid_material_quantity_and_inactive_filter_do_not_change_stock(self):
        for item, quantity in (
            (self.other_item, '1'), (self.bentonite, '10000.01'), (self.bentonite, '1.001'),
            (self.bentonite, '0'), (self.bentonite, 'NaN'),
        ):
            with self.subTest(quantity=quantity, item=item.pk):
                response = self.post(self.payload(lines=[{'item_id': item.pk, 'quantity': quantity}]))
                self.assertEqual(response.status_code, 400, response.content)
        self.filter.is_active = False
        self.filter.save(update_fields=['is_active'])
        self.assertEqual(self.post(self.payload()).status_code, 400)
        self.balance.refresh_from_db()
        self.assertEqual(self.balance.quantity, 10000)
        self.assertFalse(WarehouseDocument.objects.exists())
        self.assertFalse(WarehouseMovement.objects.exists())

    def test_only_admin_can_cancel_and_cancel_reverses_the_issue(self):
        document_id = self.post(self.payload()).json()['id']
        url = f'/api/warehouse/documents/{document_id}/cancel/'
        self.assertEqual(self.client.post(url, {}, **self.headers).status_code, 403)
        self.assertEqual(self.client.post(url, {}, **self.admin_headers).status_code, 200)
        self.balance.refresh_from_db()
        self.assertEqual(self.balance.quantity, 10000)
        self.assertEqual(WarehouseMovement.objects.filter(document_id=document_id).count(), 2)

    def test_both_mixers_use_same_filter_without_another_bentonite_issue(self):
        self.assertEqual(self.post(self.payload()).status_code, 201)
        tank = ProductionContainer.objects.create(
            kind='finished_diesel_tank', number=99, system_code='bentonite-test-diesel', capacity_liters=200,
        )
        for number in (98, 99):
            mixer = ProductionContainer.objects.create(
                kind='finishing_mixer', number=number, system_code=f'bentonite-test-mixer-{number}',
                capacity_liters=200, current_volume_liters=75, oil_product='diesel',
            )
            transferred = self.client.post('/api/processing/oil-movements/finished-product-loading/', {
                'source_id': mixer.pk, 'destination_id': tank.pk, 'volume_liters': '75', 'idempotency_key': str(uuid4()),
            }, content_type='application/json', **self.headers)
            self.assertEqual(transferred.status_code, 201, transferred.content)
            self.assertEqual(MaterialMovement.objects.get(pk=transferred.json()['id']).via_filter, self.filter)
            mixer.refresh_from_db()
            self.assertEqual(mixer.current_volume_liters, 0)
        tank.refresh_from_db()
        self.balance.refresh_from_db()
        self.assertEqual(tank.current_volume_liters, 150)
        self.assertEqual(self.balance.quantity, Decimal('9989.75'))
        self.assertEqual(WarehouseMovement.objects.count(), 1)


class FlowFilterMigrationTests(TransactionTestCase):
    def setUp(self):
        executor = MigrationExecutor(connection)
        executor.migrate([PREVIOUS_MIGRATION])
        self.old = executor.loader.project_state([PREVIOUS_MIGRATION]).apps

    def tearDown(self):
        self.old.get_model('api', 'ProductionContainer').objects.filter(kind='finishing_filter').update(
            current_volume_liters=0, oil_product='',
        )
        MigrationExecutor(connection).migrate([('api', '0059_chemical_mixer_reagents')])
        super().tearDown()

    def test_existing_oil_blocks_migration_and_empty_filter_keeps_its_history(self):
        filter_equipment = self.old.get_model('api', 'ProductionContainer').objects.create(
            kind='finishing_filter', number=98, system_code='legacy-filter',
            capacity_liters=100, current_volume_liters=10, oil_product='diesel',
        )
        historical = self.old.get_model('api', 'MaterialMovement').objects.create(
            movement_number='LEGACY-FILTER-HISTORY', movement_type='mixer_to_filter',
            destination_container=filter_equipment, destination_snapshot='Финишный фильтр №98', volume_liters=10,
        )
        with self.assertRaisesMessage(RuntimeError, 'Finishing filters still hold oil'):
            MigrationExecutor(connection).migrate([FLOW_FILTER_MIGRATION])
        filter_equipment.refresh_from_db()
        self.assertEqual(filter_equipment.current_volume_liters, 10)
        filter_equipment.current_volume_liters = 0
        filter_equipment.oil_product = ''
        filter_equipment.save(update_fields=['current_volume_liters', 'oil_product'])
        MigrationExecutor(connection).migrate([FLOW_FILTER_MIGRATION])
        updated = ProductionContainer.objects.get(pk=filter_equipment.pk)
        self.assertIsNone(updated.capacity_liters)
        self.assertEqual(updated.number, 98)
        self.assertEqual(MaterialMovement.objects.get(pk=historical.pk).destination_snapshot, 'Финишный фильтр №98')
