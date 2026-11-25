from decimal import Decimal
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.test import TestCase

from .auth import create_access_token
from .models import AccessGroup, GroupModuleAccess, MaterialMovement, Module, Permission, ProductionContainer, UserProfile


TANKS_API = '/api/processing/nigrol-tanks/'
LOADING_API = '/api/processing/movements/workshop-to-nigrol-tank/'
DIESEL_LOADING_API = '/api/processing/movements/workshop-to-raw-diesel-tank/'
OVERVIEW_API = '/api/dashboard/overview/'
RECONCILIATION_API = '/api/processing/container-reconciliations/'


class NigrolLoadingTests(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_superuser('nigrol-admin')
        self.headers = self.headers_for(self.admin)
        self.workshop = ProductionContainer.objects.create(
            kind=ProductionContainer.KIND_PROCESSING_WORKSHOP, number=991, system_code='test-nigrol-workshop',
            capacity_liters=100, current_volume_liters=100,
        )
        self.assertEqual(self.client.get(TANKS_API, **self.headers).json()['items'], [])
        self.tank = self.create_tank(1, 70)

    def headers_for(self, user):
        return {'HTTP_AUTHORIZATION': f'Bearer {create_access_token(user)}'}

    def post_json(self, path, payload, headers=None):
        return self.client.post(path, data=payload, content_type='application/json', **(headers or self.headers))

    def create_tank(self, number, capacity):
        response = self.post_json(TANKS_API, {'number': number, 'capacity_liters': capacity})
        self.assertEqual(response.status_code, 201, response.content)
        return ProductionContainer.objects.get(pk=response.json()['id'])

    def payload(self, **updates):
        return {
            'source_workshop_id': self.workshop.pk,
            'destination_tank_id': self.tank.pk,
            'volume_liters': '60.125',
            'idempotency_key': str(uuid4()),
            **updates,
        }

    def test_direct_nigrol_outlet_preserves_measurements_and_updates_both_tanks(self):
        other = self.create_tank(2, 50)
        payload = self.payload()
        response = self.post_json(LOADING_API, payload)
        self.assertEqual(response.status_code, 201, response.content)
        movement = MaterialMovement.objects.get(pk=response.json()['id'])
        self.assertEqual(movement.movement_type, MaterialMovement.TYPE_REACTOR_TO_NIGROL_TANK)
        self.assertEqual(movement.product_name, 'Нигрол')
        self.assertEqual(movement.created_by, self.admin)
        self.assertEqual(movement.source_container, self.workshop)
        self.assertEqual(movement.destination_container, self.tank)
        self.assertIsNone(movement.source_volume_before)
        self.assertIsNone(movement.source_volume_after)
        self.assertEqual(movement.destination_volume_after, Decimal('60.125'))
        self.assertEqual(self.post_json(LOADING_API, payload).status_code, 200)
        self.assertEqual(self.post_json(LOADING_API, {**payload, 'volume_liters': '1'}).status_code, 409)
        self.assertEqual(self.post_json(DIESEL_LOADING_API, payload).status_code, 400)

        self.assertEqual(self.post_json(LOADING_API, self.payload(destination_tank_id=other.pk, volume_liters='50.001')).status_code, 400)
        response = self.post_json(LOADING_API, self.payload(destination_tank_id=other.pk, volume_liters='39.875'))
        self.assertEqual(response.status_code, 201, response.content)
        self.workshop.refresh_from_db()
        self.assertEqual(self.workshop.current_volume_liters, 100)
        tanks = self.client.get(OVERVIEW_API, **self.headers).json()['nigrol_tanks']
        self.assertEqual({item['id']: item['current_volume_liters'] for item in tanks['items']},
                         {self.tank.pk: '60.125', other.pk: '39.875'})
        self.assertTrue(all(item['last_loading_at'] for item in tanks['items']))
        journal = self.client.get('/api/processing/journal/', {'movement_type': movement.movement_type}, **self.headers).json()
        self.assertEqual(journal['total'], 2)

    def test_invalid_transfers_leave_stock_unchanged_and_nigrol_is_terminal(self):
        mixer = ProductionContainer.objects.create(
            kind=ProductionContainer.KIND_CHEMICAL_MIXER, number=991, system_code='test-nigrol-mixer', capacity_liters=100,
        )
        for updates in (
            {'volume_liters': '0'}, {'volume_liters': '1.0001'}, {'volume_liters': 'NaN'},
            {'volume_liters': '70.001'}, {'destination_tank_id': mixer.pk}, {'source_workshop_id': self.tank.pk},
            {'source_workshop_id': True}, {'destination_tank_id': 2 ** 63}, {'idempotency_key': 1},
        ):
            with self.subTest(updates=updates):
                self.assertEqual(self.post_json(LOADING_API, self.payload(**updates)).status_code, 400)
        self.tank.is_active = False
        self.tank.save(update_fields=['is_active'])
        self.assertEqual(self.post_json(LOADING_API, self.payload()).status_code, 400)
        self.assertFalse(MaterialMovement.objects.exists())
        self.workshop.refresh_from_db()
        self.assertEqual(self.workshop.current_volume_liters, 100)
        self.tank.is_active = True
        self.tank.save(update_fields=['is_active'])
        self.assertEqual(self.post_json(LOADING_API, self.payload()).status_code, 201)
        response = self.post_json('/api/processing/oil-movements/chemical-mixer-loading/', {
            'source_id': self.tank.pk, 'destination_id': mixer.pk, 'volume_liters': '1', 'idempotency_key': str(uuid4()),
        })
        self.assertEqual(response.status_code, 400)
        self.tank.refresh_from_db()
        self.assertEqual(self.tank.current_volume_liters, Decimal('60.125'))
        self.assertEqual(MaterialMovement.objects.count(), 1)

    def test_only_operation_permissions_grant_read_and_loading(self):
        user = get_user_model().objects.create_user('nigrol-operator')
        group = AccessGroup.objects.create(name='Отгрузка нигрола (тест)')
        UserProfile.objects.update_or_create(user=user, defaults={'group': group})
        grant = GroupModuleAccess.objects.create(group=group, module=Module.objects.get(code='nigrol-loading'))
        grant.permissions.add(Permission.objects.get(code='view'))
        headers = self.headers_for(user)
        self.assertEqual(self.client.get('/api/processing/workshops/', **headers).status_code, 200)
        response = self.client.get(TANKS_API, **headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['items'][0]['free_volume_liters'], '70.000')
        for path in (OVERVIEW_API, RECONCILIATION_API, '/api/processing/raw-diesel-tanks/'):
            self.assertEqual(self.client.get(path, **headers).status_code, 403)
        self.assertEqual(self.post_json(LOADING_API, self.payload(), headers).status_code, 403)
        grant.permissions.add(Permission.objects.get(code='create'))
        self.assertEqual(self.post_json(LOADING_API, self.payload(), headers).status_code, 201)
        self.assertEqual(self.post_json(TANKS_API, {'number': 2, 'capacity_liters': 50}, headers).status_code, 403)
        self.assertEqual(self.post_json(DIESEL_LOADING_API, self.payload(), headers).status_code, 403)

    def test_reconciliation_counts_active_nigrol_tank_and_corrects_balance(self):
        self.assertEqual(self.post_json(LOADING_API, self.payload(volume_liters='50')).status_code, 201)
        operator = get_user_model().objects.create_user('nigrol-reconciliation-operator')
        UserProfile.objects.update_or_create(
            user=operator, defaults={'group': AccessGroup.objects.get(name='Заведующий складом')},
        )
        headers = self.headers_for(operator)
        response = self.client.get(RECONCILIATION_API, **headers)
        tank = next(item for item in response.json()['containers'] if item['id'] == self.tank.pk)
        self.assertEqual(tank['kind'], 'nigrol_tank')
        self.tank.refresh_from_db()
        response = self.post_json(RECONCILIATION_API, {'measurements': [{
            'container_id': self.tank.pk, 'version': self.tank.updated_at.isoformat(), 'actual_liters': '45',
        }]}, headers)
        self.assertEqual(response.status_code, 201, response.content)
        overview = self.client.get(OVERVIEW_API, **self.headers).json()
        self.assertEqual(overview['nigrol_tanks']['items'][0]['current_volume_liters'], '45.000')
        self.assertEqual(overview['reconciliation']['stages']['nigrol_tank']['summary']['deviation_percent'], '-10.00')

    def test_compensation_restores_tank_balance_and_keeps_history(self):
        movement_id = self.post_json(LOADING_API, self.payload()).json()['id']
        response = self.post_json(f'/api/processing/movements/{movement_id}/compensate/', {'reason': 'Исправление теста'})
        self.assertEqual(response.status_code, 201, response.content)
        self.workshop.refresh_from_db()
        self.tank.refresh_from_db()
        self.assertEqual(self.workshop.current_volume_liters, 100)
        self.assertEqual(self.tank.current_volume_liters, 0)
        self.assertEqual(MaterialMovement.objects.count(), 2)
        self.assertEqual(self.client.delete(f'/api/processing/containers/{self.tank.pk}/', **self.headers).status_code, 400)
