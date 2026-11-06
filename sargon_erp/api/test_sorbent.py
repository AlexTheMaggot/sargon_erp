import json
import threading
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.db import close_old_connections, IntegrityError, transaction
from django.test import Client, TestCase, TransactionTestCase

from .auth import create_access_token
from .models import (
    AccessGroup, GroupModuleAccess, InventoryCategory, InventoryItem, Module, Permission,
    ProductionContainer, SorbentMovement, UnitOfMeasure, UserProfile, Warehouse,
    WarehouseBalance, WarehouseDocument, WarehouseMovement,
)


class SorbentFixture:
    def setUp(self):
        self.admin = get_user_model().objects.create_superuser('sorbent-test-admin')
        self.token = create_access_token(self.admin)
        self.warehouse = Warehouse.objects.create(name='Тестовый склад сорбента')
        unit = UnitOfMeasure.objects.create(name='Тестовый килограмм сорбента', symbol='kg', decimal_places=2)
        category = InventoryCategory.objects.create(name='Тестовый сорбент')
        self.item = InventoryItem.objects.create(name='Тестовый сорбент', unit=unit, category=category, production_material='sorbent')
        self.item.permanent_warehouses.add(self.warehouse)
        self.stock = WarehouseBalance.objects.create(warehouse=self.warehouse, item=self.item, quantity=1000, average_unit_cost=Decimal('2.50'))
        self.system = ProductionContainer.objects.create(kind='sorption_system', number=91, system_code='test-sorbent-91', capacity_liters=1000)
        self.other_system = ProductionContainer.objects.create(kind='sorption_system', number=92, system_code='test-sorbent-92', capacity_liters=1000)
        response = self.request('/api/warehouse/production-loadings/sorption/', {
            'source_warehouse_id': self.warehouse.pk, 'lines': [{'item_id': self.item.pk, 'quantity': '100'}],
            'idempotency_key': str(uuid4()),
        })
        self.assertEqual(response.status_code, 201, response.content)
        self.document_id = response.json()['id']
        self.source = WarehouseMovement.objects.get(document_id=self.document_id, movement_type='issue')

    def request(self, path, body=None, token=None):
        client = Client()
        headers = {'HTTP_AUTHORIZATION': f'Bearer {token or self.token}'}
        if body is None:
            return client.get(path, **headers)
        return client.post(path, data=json.dumps(body), content_type='application/json', **headers)

    def move(self, step='tank_to_system', quantity='60', key=None, token=None, **changes):
        return self.request('/api/processing/sorbent-cycle/', {
            'movement_type': step, 'source_movement_id': self.source.pk, 'system_id': self.system.pk,
            'quantity': quantity, 'idempotency_key': key or str(uuid4()), **changes,
        }, token)

    def reverse(self, movement_id, key=None, token=None, **changes):
        return self.request(f'/api/processing/sorbent-cycle/{movement_id}/reverse/', {
            'reason': 'Тестовая корректировка', 'idempotency_key': key or str(uuid4()), **changes,
        }, token)

    def summary(self):
        return self.request('/api/processing/sorbent-cycle/').json()['summary']

    def cancel_loading(self):
        return self.request(f'/api/warehouse/documents/{self.document_id}/cancel/', {})


class SorbentCycleTests(SorbentFixture, TestCase):
    def test_warehouse_refill_and_repeated_closed_cycle_do_not_issue_twice(self):
        self.assertEqual(self.summary(), {'tank_kg': '100.00', 'in_system_kg': '0.00', 'regeneration_kg': '0.00', 'total_kg': '100.00'})
        for _ in range(2):
            self.assertEqual(self.move().status_code, 201)
            self.assertEqual(self.summary()['tank_kg'], '40.00')
            self.assertEqual(self.move('system_to_regeneration').status_code, 201)
            self.assertEqual(self.summary()['regeneration_kg'], '60.00')
            self.assertEqual(self.move('regeneration_to_tank').status_code, 201)
            self.assertEqual(self.summary()['tank_kg'], '100.00')
        self.stock.refresh_from_db()
        self.system.refresh_from_db()
        self.assertEqual(self.stock.quantity, 900)
        self.assertEqual(self.system.current_volume_liters, 0)
        self.assertEqual(WarehouseMovement.objects.count(), 1)
        self.assertEqual(WarehouseDocument.objects.count(), 1)
        self.assertEqual(SorbentMovement.objects.count(), 6)

    def test_every_location_rejects_overdraw_and_wrong_system(self):
        self.assertEqual(self.move(quantity='101').status_code, 400)
        self.assertEqual(self.move('system_to_regeneration').status_code, 400)
        self.assertEqual(self.move('regeneration_to_tank').status_code, 400)
        self.move()
        self.assertEqual(self.move('system_to_regeneration', system_id=self.other_system.pk).status_code, 400)
        self.assertEqual(self.move('system_to_regeneration', quantity='61').status_code, 400)
        self.move('system_to_regeneration', quantity='30')
        self.assertEqual(self.move('regeneration_to_tank', quantity='31').status_code, 400)
        self.assertEqual(self.summary(), {'tank_kg': '40.00', 'in_system_kg': '30.00', 'regeneration_kg': '30.00', 'total_kg': '100.00'})

    def test_invalid_payloads_and_precision_are_rejected(self):
        for value in ('0', '-1', 'NaN', 'Infinity', '1e99999', '0.001', '10000000000000000', None, True, []):
            with self.subTest(value=value):
                self.assertEqual(self.move(quantity=value).status_code, 400)
        for changes in ({'movement_type': []}, {'movement_type': 'reversal'}, {'system_id': True}, {'source_movement_id': '1'}, {'note': []}, {'note': 'x' * 1001}):
            self.assertEqual(self.move(**changes).status_code, 400)
        self.assertEqual(self.request('/api/processing/sorbent-cycle/', []).status_code, 400)
        self.assertFalse(SorbentMovement.objects.exists())
        self.item.unit.decimal_places = 0
        self.item.unit.save(update_fields=['decimal_places'])
        self.assertEqual(self.move(quantity='0.01').status_code, 400)

    def test_idempotency_and_actor_are_checked(self):
        result = self.move(key='same-sorbent')
        self.assertEqual(result.status_code, 201)
        self.assertEqual(self.move(key='same-sorbent').status_code, 200)
        self.assertEqual(self.move(key='same-sorbent', quantity='61').status_code, 409)
        self.assertEqual(self.move(key='same-sorbent', note='changed').status_code, 409)
        other = get_user_model().objects.create_superuser('sorbent-other-test-admin')
        self.assertEqual(self.move(key='same-sorbent', token=create_access_token(other)).status_code, 409)
        self.assertEqual(SorbentMovement.objects.count(), 1)

    def test_admin_reversal_preserves_history_and_prevents_double_reversal(self):
        first = self.move().json()
        second = self.move('system_to_regeneration').json()
        self.assertEqual(self.reverse(first['id']).status_code, 400)
        self.assertEqual(self.reverse(second['id'], key='reverse-sorbent').status_code, 201)
        self.assertEqual(self.reverse(second['id'], key='reverse-sorbent').status_code, 200)
        self.assertEqual(self.reverse(second['id']).status_code, 423)
        self.assertEqual(self.reverse(first['id']).status_code, 201)
        self.assertEqual(self.summary()['tank_kg'], '100.00')
        self.assertEqual(SorbentMovement.objects.count(), 4)
        original = self.request('/api/processing/sorbent-cycle/').json()['items'][-1]
        self.assertTrue(original['is_reversed'])

    def test_loading_cancellation_is_guarded_and_restores_warehouse_only_once(self):
        movement = self.move().json()
        self.assertEqual(self.cancel_loading().status_code, 423)
        self.assertEqual(self.reverse(movement['id']).status_code, 201)
        self.assertEqual(self.cancel_loading().status_code, 200)
        self.assertEqual(self.cancel_loading().status_code, 423)
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.quantity, 1000)
        self.assertEqual(self.summary()['total_kg'], '0.00')
        self.assertEqual(self.move().status_code, 400)

    def test_compensation_requires_reason_and_cannot_reverse_reversal(self):
        movement = self.move().json()
        self.assertEqual(self.reverse(movement['id'], reason=' ').status_code, 400)
        reversal = self.reverse(movement['id']).json()
        self.assertEqual(self.reverse(reversal['id']).status_code, 404)

    def test_system_history_and_remaining_sorbent_protect_container(self):
        self.move()
        path = f'/api/processing/containers/{self.system.pk}/'
        headers = {'HTTP_AUTHORIZATION': f'Bearer {self.token}'}
        response = self.client.patch(path, data=json.dumps({'is_active': False}), content_type='application/json', **headers)
        self.assertEqual(response.status_code, 400)
        self.move('system_to_regeneration')
        self.assertEqual(self.client.patch(path, data=json.dumps({'is_active': False}), content_type='application/json', **headers).status_code, 400)
        self.move('regeneration_to_tank')
        self.assertEqual(self.client.patch(path, data=json.dumps({'is_active': False}), content_type='application/json', **headers).status_code, 200)
        self.assertEqual(self.move().status_code, 400)
        self.assertEqual(self.client.delete(path, **headers).status_code, 400)

    def test_wrong_equipment_and_non_sorbent_source_are_rejected(self):
        self.system.kind = 'separator'
        self.system.save(update_fields=['kind'])
        self.assertEqual(self.move().status_code, 400)
        self.system.kind = 'sorption_system'
        self.system.save(update_fields=['kind'])
        self.source.document.production_target = 'canisters'
        self.source.document.save(update_fields=['production_target'])
        self.assertEqual(self.move().status_code, 400)

    def test_permissions_are_independent_and_reference_contains_no_finances(self):
        group = AccessGroup.objects.create(name='Тест оператора циркуляции')
        access = GroupModuleAccess.objects.create(group=group, module=Module.objects.get(code='sorbent-cycle'))
        access.permissions.add(Permission.objects.get(code='view'))
        user = get_user_model().objects.create_user('sorbent-test-operator')
        UserProfile.objects.filter(user=user).update(group=group)
        token = create_access_token(user)
        data = self.request('/api/processing/sorbent-cycle/', token=token)
        self.assertEqual(data.status_code, 200)
        self.assertNotIn('cost', data.content.decode())
        self.assertEqual(self.move(token=token).status_code, 403)
        access.permissions.add(Permission.objects.get(code='create'))
        movement = self.move(token=token)
        self.assertEqual(movement.status_code, 201)
        self.assertEqual(self.reverse(movement.json()['id'], token=token).status_code, 403)
        for path in ('/api/warehouse/overview/', '/api/warehouse/production-loadings/sorption/', '/api/processing/oil-movements/sorption-loading/'):
            self.assertEqual(self.request(path, token=token).status_code, 403)
        self.assertEqual(Client().get('/api/processing/sorbent-cycle/').status_code, 401)

    def test_overview_and_source_totals_are_real_and_do_not_include_prices(self):
        self.move(quantity='25')
        self.move('system_to_regeneration', quantity='10')
        data = self.request('/api/dashboard/overview/').json()['sorbent_cycle']
        self.assertEqual(data, {'tank_kg': '75.00', 'in_system_kg': '15.00', 'regeneration_kg': '10.00', 'total_kg': '100.00'})
        self.assertNotIn('cost', str(data))
        source = self.request('/api/processing/sorbent-cycle/').json()['sources'][0]
        self.assertEqual(source['tank_quantity'], '75.00')
        self.assertEqual(source['systems'][0]['system_quantity'], '15.00')

    def test_database_rejects_nonpositive_quantity(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            SorbentMovement.objects.create(number='invalid-test-move', movement_type='tank_to_system', source_movement=self.source,
                                           system=self.system, quantity=0, idempotency_key='invalid-test-move')


class ConcurrentSorbentTests(SorbentFixture, TransactionTestCase):
    def parallel(self, callbacks):
        barrier = threading.Barrier(len(callbacks))

        def send(callback):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                return callback().status_code
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=len(callbacks)) as executor:
            return sorted(executor.map(send, callbacks))

    def test_concurrent_duplicate_creates_one_movement(self):
        self.assertEqual(self.parallel([lambda: self.move(key='concurrent-sorbent')] * 2), [200, 201])
        self.assertEqual(SorbentMovement.objects.count(), 1)

    def test_concurrent_loads_cannot_overdraw_tank(self):
        self.assertEqual(self.parallel([lambda: self.move()] * 2), [201, 400])
        self.assertEqual(self.summary()['tank_kg'], '40.00')

    def test_loading_cancellation_cannot_race_with_cycle(self):
        results = self.parallel([lambda: self.move(), self.cancel_loading])
        self.assertIn(results, ([200, 400], [201, 423]))
        self.assertIn(self.summary()['tank_kg'], ('0.00', '40.00'))
