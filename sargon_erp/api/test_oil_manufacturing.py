import json
import threading
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.db import close_old_connections
from django.test import Client, TestCase, TransactionTestCase

from .auth import create_access_token
from .models import (
    AccessGroup, GroupModuleAccess, InventoryCategory, InventoryItem, MaterialMovement, Module,
    OilGrade, OilManufacturingBatch, Permission, ProductionContainer, UnitOfMeasure, UserProfile,
    Warehouse, WarehouseBalance, WarehouseDocument, WarehouseMovement,
)


class OilManufacturingFixture:
    def setUp(self):
        self.admin = get_user_model().objects.create_superuser('manufacturing-test-admin')
        self.token = create_access_token(self.admin)
        self.grade = OilGrade.objects.create(name='Тестовая марка A')
        self.other_grade = OilGrade.objects.create(name='Тестовая марка B')
        self.base = self.container('finished_spindle_tank', 1, capacity=5000, volume=1000)
        self.reactor = self.container('concentrate_reactor', 1)
        self.blender = self.container('oil_blender', 1, capacity=2000)
        self.other_blender = self.container('oil_blender', 2, capacity=2000)
        self.tank = self.container('finished_oil_tank', 1, grade=self.grade, capacity=5000)
        self.other_tank = self.container('finished_oil_tank', 2, grade=self.other_grade)
        self.warehouse = Warehouse.objects.create(name='Тестовый склад полипропилена')
        unit = UnitOfMeasure.objects.create(name='Тестовый килограмм', symbol='kg', decimal_places=2)
        category = InventoryCategory.objects.create(name='Тестовый полипропилен')
        self.polypropylene = InventoryItem.objects.create(
            name='Тестовый полипропилен', unit=unit, category=category, production_material='polypropylene',
        )
        self.polypropylene.permanent_warehouses.add(self.warehouse)
        self.stock = WarehouseBalance.objects.create(
            warehouse=self.warehouse, item=self.polypropylene, quantity=100, average_unit_cost=Decimal('3.50'),
        )

    def container(self, kind, number, capacity=1000, volume=0, grade=None):
        return ProductionContainer.objects.create(kind=kind, number=number, system_code=f'manufacture-{kind}-{number}',
                                                   capacity_liters=capacity, current_volume_liters=volume, oil_grade=grade)

    def post(self, step, body, key=None, token=None):
        return Client().post(f'/api/oil-production/operations/{step}/',
                             data=json.dumps({**body, 'idempotency_key': key or str(uuid4())}), content_type='application/json',
                             HTTP_AUTHORIZATION=f'Bearer {token or self.token}')

    def concentrate_body(self, **changes):
        return {'equipment_id': self.reactor.pk, 'source_tank_id': self.base.pk, 'base_liters': '100',
                'warehouse_id': self.warehouse.pk, 'item_id': self.polypropylene.pk, 'polypropylene_quantity': '2', **changes}

    def create_concentrate(self, **changes):
        result = self.post('concentrate-loading', self.concentrate_body(**changes))
        self.assertEqual(result.status_code, 201, result.content)
        return result.json()

    def blending_body(self, concentrate_id, **changes):
        return {'equipment_id': self.blender.pk, 'source_tank_id': self.base.pk, 'base_liters': '200',
                'oil_grade_id': self.grade.pk, 'concentrate_batch_id': concentrate_id, 'concentrate_liters': '102', **changes}

    def create_blending(self):
        concentrate = self.create_concentrate()
        result = self.post('oil-blending', self.blending_body(concentrate['id']))
        self.assertEqual(result.status_code, 201, result.content)
        return result.json()

    def action(self, batch_id, action, body):
        return Client().post(f'/api/oil-production/batches/{batch_id}/{action}/',
                             data=json.dumps(body), content_type='application/json', HTTP_AUTHORIZATION=f'Bearer {self.token}')

    def compensate(self, movement_id):
        return Client().post(f'/api/processing/movements/{movement_id}/compensate/',
                             data=json.dumps({'reason': 'Тестовая корректировка'}), content_type='application/json',
                             HTTP_AUTHORIZATION=f'Bearer {self.token}')


class OilManufacturingTests(OilManufacturingFixture, TestCase):
    def test_concentrate_service_creates_batch(self):
        from .oil_manufacturing import _create_batch
        from .oil_processing import lock_oil_line
        lock_oil_line()
        batch = _create_batch('concentrate-loading', self.concentrate_body(), self.admin, 'service-test-concentrate')
        self.assertEqual(batch.input_liters, 100)

    def test_actual_transfer_and_filling_without_mass_conversion_or_second_issue(self):
        batch = self.create_blending()
        response = self.post('oil-tank-loading', {'batch_id': batch['id'], 'tank_id': self.tank.pk, 'volume_liters': '310'})
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(self.post('oil-filling', {'tank_id': self.tank.pk, 'volume_liters': '10'}).status_code, 201)
        self.base.refresh_from_db()
        self.stock.refresh_from_db()
        self.tank.refresh_from_db()
        self.assertEqual(self.base.current_volume_liters, 700)
        self.assertEqual(self.stock.quantity, 98)
        self.assertEqual(self.tank.current_volume_liters, 300)
        self.assertEqual(WarehouseMovement.objects.filter(movement_type='issue').count(), 1)
        self.assertEqual(OilManufacturingBatch.objects.get(pk=batch['id']).output_liters, 310)
        self.assertEqual(self.reactor.current_volume_liters, 0)
        self.assertEqual(self.blender.current_volume_liters, 0)

    def test_polypropylene_shortage_rolls_back_base_batch_and_document(self):
        response = self.post('concentrate-loading', self.concentrate_body(polypropylene_quantity='101'))
        self.assertEqual(response.status_code, 400)
        self.base.refresh_from_db()
        self.assertEqual(self.base.current_volume_liters, 1000)
        self.assertFalse(OilManufacturingBatch.objects.exists())
        self.assertFalse(MaterialMovement.objects.exists())
        self.assertFalse(WarehouseDocument.objects.exists())

    def test_invalid_inputs_and_capacity_do_not_create_records(self):
        for value in ('0', '-1', 'NaN', 'Infinity', '1e99999', '0.0001'):
            with self.subTest(value=value):
                self.assertEqual(self.post('concentrate-loading', self.concentrate_body(base_liters=value)).status_code, 400)
        for value in ('NaN', 'Infinity', '10000000000000000', '0', '1.001'):
            with self.subTest(value=value):
                self.assertEqual(self.post('concentrate-loading', self.concentrate_body(polypropylene_quantity=value)).status_code, 400)
        self.assertEqual(self.post('concentrate-loading', self.concentrate_body(base_liters='1001')).status_code, 400)
        self.assertEqual(self.post('concentrate-loading', self.concentrate_body(warehouse_id=999999)).status_code, 400)
        self.assertFalse(OilManufacturingBatch.objects.exists())
        self.assertFalse(WarehouseDocument.objects.exists())

    def test_batch_idempotency_busy_equipment_and_changed_request(self):
        first = self.post('concentrate-loading', self.concentrate_body(), key='same-concentrate')
        replay = self.post('concentrate-loading', self.concentrate_body(), key='same-concentrate')
        changed = self.post('concentrate-loading', self.concentrate_body(base_liters='101'), key='same-concentrate')
        self.assertEqual([first.status_code, replay.status_code, changed.status_code], [201, 200, 409])
        self.assertEqual(self.post('concentrate-loading', self.concentrate_body()).status_code, 400)
        self.assertEqual(OilManufacturingBatch.objects.count(), 1)
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.quantity, 98)

    def test_tank_grade_overflow_and_filling_shortage(self):
        batch = self.create_blending()
        self.assertEqual(self.post('oil-tank-loading', {'batch_id': batch['id'], 'tank_id': self.other_tank.pk, 'volume_liters': '100'}).status_code, 400)
        self.assertEqual(self.post('oil-tank-loading', {'batch_id': batch['id'], 'tank_id': self.tank.pk, 'volume_liters': '2001'}).status_code, 400)
        self.assertEqual(self.post('oil-filling', {'tank_id': self.tank.pk, 'volume_liters': '1'}).status_code, 400)
        self.tank.current_volume_liters = 4999
        self.tank.save()
        self.assertEqual(self.post('oil-tank-loading', {'batch_id': batch['id'], 'tank_id': self.tank.pk, 'volume_liters': '2'}).status_code, 400)

    def test_transfer_and_filling_idempotency(self):
        batch = self.create_blending()
        body = {'batch_id': batch['id'], 'tank_id': self.tank.pk, 'volume_liters': '200'}
        self.assertEqual(self.post('oil-tank-loading', body, key='same-transfer').status_code, 201)
        self.assertEqual(self.post('oil-tank-loading', body, key='same-transfer').status_code, 200)
        self.assertEqual(self.post('oil-tank-loading', {**body, 'volume_liters': '201'}, key='same-transfer').status_code, 409)
        self.assertEqual(self.post('oil-filling', {'tank_id': self.tank.pk, 'volume_liters': '20'}, key='same-fill').status_code, 201)
        self.assertEqual(self.post('oil-filling', {'tank_id': self.tank.pk, 'volume_liters': '20'}, key='same-fill').status_code, 200)
        self.tank.refresh_from_db()
        self.assertEqual(self.tank.current_volume_liters, 180)

    def test_completion_requires_measured_transfer_and_explicit_empty_confirmation(self):
        batch = self.create_blending()
        self.assertEqual(self.action(batch['id'], 'complete', {'equipment_empty': True}).status_code, 400)
        self.post('oil-tank-loading', {'batch_id': batch['id'], 'tank_id': self.tank.pk, 'volume_liters': '302'})
        self.assertEqual(self.action(batch['id'], 'complete', {}).status_code, 400)
        self.assertEqual(self.action(batch['id'], 'complete', {'equipment_empty': True}).status_code, 200)
        self.assertEqual(self.post('oil-tank-loading', {'batch_id': batch['id'], 'tank_id': self.tank.pk, 'volume_liters': '1'}).status_code, 400)

    def test_cancel_loading_returns_base_and_polypropylene_once(self):
        batch = self.create_concentrate()
        response = self.action(batch['id'], 'cancel', {'reason': 'Ошибка ввода'})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self.action(batch['id'], 'cancel', {'reason': 'Повтор'}).status_code, 400)
        self.base.refresh_from_db()
        self.stock.refresh_from_db()
        self.assertEqual(self.base.current_volume_liters, 1000)
        self.assertEqual(self.stock.quantity, 100)
        self.assertEqual(self.stock.average_unit_cost, Decimal('3.50'))
        self.assertEqual(WarehouseDocument.objects.get().status, 'cancelled')
        self.assertEqual(MaterialMovement.objects.filter(movement_type='compensation').count(), 1)

    def test_cancel_blending_restores_concentrate_and_prevents_parent_cancellation_until_then(self):
        batch = self.create_blending()
        source = OilManufacturingBatch.objects.get(equipment=self.reactor)
        self.assertEqual(self.action(source.pk, 'cancel', {'reason': 'Ошибка'}).status_code, 400)
        self.assertEqual(self.action(batch['id'], 'cancel', {'reason': 'Ошибка'}).status_code, 200)
        source.refresh_from_db()
        self.assertEqual(source.output_liters, 0)
        self.assertEqual(self.action(source.pk, 'cancel', {'reason': 'Ошибка'}).status_code, 200)
        self.base.refresh_from_db()
        self.assertEqual(self.base.current_volume_liters, 1000)

    def test_direct_warehouse_cancellation_is_blocked(self):
        batch = self.create_concentrate()
        document = OilManufacturingBatch.objects.get(pk=batch['id']).material_document
        response = self.client.post(f'/api/warehouse/documents/{document.pk}/cancel/', HTTP_AUTHORIZATION=f'Bearer {self.token}')
        self.assertEqual(response.status_code, 423)
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.quantity, 98)

    def test_compensation_of_filling_and_transfer_and_grade_protection(self):
        batch = self.create_blending()
        transfer = self.post('oil-tank-loading', {'batch_id': batch['id'], 'tank_id': self.tank.pk, 'volume_liters': '300'}).json()
        filling = self.post('oil-filling', {'tank_id': self.tank.pk, 'volume_liters': '300'}).json()
        headers = {'HTTP_AUTHORIZATION': f'Bearer {self.token}'}
        path = f'/api/processing/containers/{self.tank.pk}/'
        self.assertEqual(self.client.patch(path, data=json.dumps({'oil_grade_id': self.other_grade.pk}), content_type='application/json', **headers).status_code, 200)
        self.assertEqual(self.compensate(filling['id']).status_code, 400)
        self.client.patch(path, data=json.dumps({'oil_grade_id': self.grade.pk}), content_type='application/json', **headers)
        self.assertEqual(self.compensate(filling['id']).status_code, 201)
        self.assertEqual(self.compensate(transfer['id']).status_code, 201)
        self.tank.refresh_from_db()
        self.assertEqual(self.tank.current_volume_liters, 0)
        self.assertEqual(OilManufacturingBatch.objects.get(pk=batch['id']).output_liters, 0)

    def test_production_equipment_crud_and_grade_protect(self):
        headers = {'HTTP_AUTHORIZATION': f'Bearer {self.token}'}
        self.create_concentrate()
        path = f'/api/processing/containers/{self.reactor.pk}/'
        self.assertEqual(self.client.patch(path, data=json.dumps({'is_active': False}), content_type='application/json', **headers).status_code, 400)
        self.assertEqual(self.client.delete(path, **headers).status_code, 400)
        self.assertEqual(self.client.delete(f'/api/oil-production/grades/{self.grade.pk}/', **headers).status_code, 400)
        created = self.client.post('/api/oil-production/containers/finished-oil-tanks/',
                                   data=json.dumps({'number': 3, 'capacity_liters': 1000, 'oil_grade_id': self.grade.pk}), content_type='application/json', **headers)
        self.assertEqual(created.status_code, 201, created.content)

    def test_single_form_role_cannot_reach_other_forms_or_warehouse_settings(self):
        user = get_user_model().objects.create_user('manufacturing-reader-test')
        group = AccessGroup.objects.create(name='Тестовая группа концентрата')
        access = GroupModuleAccess.objects.create(group=group, module=Module.objects.get(code='concentrate-loading'))
        access.permissions.add(Permission.objects.get(code='view'))
        UserProfile.objects.filter(user=user).update(group=group)
        token = create_access_token(user)
        headers = {'HTTP_AUTHORIZATION': f'Bearer {token}'}
        data = self.client.get('/api/oil-production/operations/concentrate-loading/', **headers)
        self.assertEqual(data.status_code, 200)
        self.assertEqual(data.json()['materials'][0]['quantity'], '100.00')
        self.assertEqual(self.post('concentrate-loading', self.concentrate_body(), token=token).status_code, 403)
        self.assertEqual(self.client.get('/api/oil-production/operations/oil-blending/', **headers).status_code, 403)
        self.assertEqual(self.client.get('/api/warehouse/overview/', **headers).status_code, 403)
        access.permissions.add(Permission.objects.get(code='create'))
        self.assertEqual(self.post('concentrate-loading', self.concentrate_body(), token=token).status_code, 201)

    def test_overview_and_reference_do_not_present_input_as_measured_stock(self):
        batch = self.create_blending()
        self.post('oil-tank-loading', {'batch_id': batch['id'], 'tank_id': self.tank.pk, 'volume_liters': '300'})
        self.post('oil-filling', {'tank_id': self.tank.pk, 'volume_liters': '25'})
        headers = {'HTTP_AUTHORIZATION': f'Bearer {self.token}'}
        data = self.client.get('/api/dashboard/overview/', **headers).json()['oil_manufacturing']
        self.assertEqual(data['polypropylene_kg'], '98.00')
        self.assertEqual(data['filled_today_liters'], '25.000')
        self.assertEqual(data['tanks'][0]['current_volume_liters'], '275.000')
        container = self.client.get('/api/oil-production/containers/concentrate-reactors/', **headers).json()['items'][0]
        self.assertFalse(container['volume_known'])
        self.assertIsNone(container['current_volume_liters'])
        self.assertEqual(container['active_batch']['output_liters'], '102.000')


class ConcurrentOilManufacturingTests(OilManufacturingFixture, TransactionTestCase):
    def parallel(self, requests):
        barrier = threading.Barrier(len(requests))

        def send(arguments):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                return self.post(*arguments).status_code
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=len(requests)) as executor:
            return sorted(executor.map(send, requests))

    def test_concurrent_duplicate_does_not_issue_polypropylene_twice(self):
        request = ('concentrate-loading', self.concentrate_body(), 'concurrent-concentrate')
        self.assertEqual(self.parallel([request, request]), [200, 201])
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.quantity, 98)
        self.assertEqual(OilManufacturingBatch.objects.count(), 1)

    def test_concurrent_loads_cannot_overdraw_polypropylene(self):
        second_reactor = self.container('concentrate_reactor', 2)
        self.stock.quantity = 3
        self.stock.save()
        self.assertEqual(self.parallel([
            ('concentrate-loading', self.concentrate_body(), 'polypropylene-first'),
            ('concentrate-loading', self.concentrate_body(equipment_id=second_reactor.pk), 'polypropylene-second'),
        ]), [201, 400])
        self.stock.refresh_from_db()
        self.base.refresh_from_db()
        self.assertEqual(self.stock.quantity, 1)
        self.assertEqual(self.base.current_volume_liters, 900)

    def test_simultaneous_concentrate_transfers_enforce_batch_capacity(self):
        source = self.create_concentrate(base_liters='800')
        self.assertEqual(self.parallel([
            ('oil-blending', self.blending_body(source['id'], base_liters='50', concentrate_liters='600'), 'blend-first'),
            ('oil-blending', self.blending_body(source['id'], equipment_id=self.other_blender.pk, base_liters='50', concentrate_liters='600'), 'blend-second'),
        ]), [201, 400])
        self.assertEqual(OilManufacturingBatch.objects.get(pk=source['id']).output_liters, 600)

    def test_simultaneous_filling_cannot_overdraw_product_tank(self):
        self.tank.current_volume_liters = 100
        self.tank.save()
        self.assertEqual(self.parallel([
            ('oil-filling', {'tank_id': self.tank.pk, 'volume_liters': '75'}, 'filling-first'),
            ('oil-filling', {'tank_id': self.tank.pk, 'volume_liters': '75'}, 'filling-second'),
        ]), [201, 400])
        self.tank.refresh_from_db()
        self.assertEqual(self.tank.current_volume_liters, 25)
