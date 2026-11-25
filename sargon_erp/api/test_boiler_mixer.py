import json
import threading
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.db import close_old_connections
from django.test import Client, TestCase, TransactionTestCase

from .auth import create_access_token
from .models import AccessGroup, GroupModuleAccess, MaterialMovement, Module, Permission, ProductionContainer, UserProfile


class BoilerWorkshopFixture:
    def setUp(self):
        self.admin = get_user_model().objects.create_superuser('boiler-mixer-admin')
        self.headers = {'HTTP_AUTHORIZATION': f'Bearer {create_access_token(self.admin)}'}
        self.boiler = ProductionContainer.objects.create(
            kind='preheating_boiler', number=930, system_code='test-boiler-930', capacity_liters=1000, current_volume_liters=200,
        )
        self.workshop = ProductionContainer.objects.create(
            kind='processing_workshop', number=930, system_code='test-mixer-930', capacity_liters=100,
        )
        self.other_workshop = ProductionContainer.objects.create(
            kind='processing_workshop', number=931, system_code='test-mixer-931', capacity_liters=100,
        )

    def payload(self, **updates):
        return {
            'source_boiler_id': self.boiler.pk, 'destination_workshop_id': self.workshop.pk,
            'volume_liters': '75.125', 'idempotency_key': str(uuid4()), **updates,
        }

    def send(self, payload=None, headers=None):
        return Client().post(
            '/api/processing/movements/boiler-to-workshop/',
            data=json.dumps(payload if payload is not None else self.payload()),
            content_type='application/json', **(headers or self.headers),
        )


class BoilerWorkshopTests(BoilerWorkshopFixture, TestCase):
    def assert_unchanged(self):
        self.boiler.refresh_from_db()
        self.workshop.refresh_from_db()
        self.assertEqual(self.boiler.current_volume_liters, 200)
        self.assertEqual(self.workshop.current_volume_liters, 0)
        self.assertFalse(MaterialMovement.objects.exists())

    def test_loading_records_boiler_balance_without_inventing_reactor_measurement(self):
        response = self.send()
        self.assertEqual(response.status_code, 201, response.content)
        self.boiler.refresh_from_db()
        self.workshop.refresh_from_db()
        self.assertEqual(self.boiler.current_volume_liters, Decimal('124.875'))
        self.assertEqual(self.workshop.current_volume_liters, 0)
        movement = MaterialMovement.objects.get()
        self.assertEqual(movement.movement_type, 'boiler_to_reactor')
        self.assertEqual(movement.product_name, 'Прогретое отработанное масло')
        self.assertEqual(movement.created_by, self.admin)
        self.assertEqual(movement.source_volume_before, 200)
        self.assertEqual(movement.source_volume_after, Decimal('124.875'))
        self.assertIsNone(movement.destination_volume_after)
        data = self.client.get('/api/dashboard/overview/', **self.headers).json()
        item = next(item for item in data['processing_reactors']['items'] if item['id'] == self.workshop.pk)
        self.assertIsNone(item['measured_liters'])
        self.assertIsNone(item['measured_at'])
        self.assertNotIn('separators', data)
        self.assertNotIn('separator_outputs', data['oil_finishing'])

    def test_invalid_values_and_shortages_do_not_change_balances(self):
        for volume in ('0', '-1', '0.0001', 'NaN', 'Infinity', '201', None):
            with self.subTest(volume=volume):
                self.assertEqual(self.send(self.payload(volume_liters=volume)).status_code, 400)
                self.assert_unchanged()
        for payload in ([], None, 'bad'):
            response = self.client.post('/api/processing/movements/boiler-to-workshop/',
                                        data=json.dumps(payload), content_type='application/json', **self.headers)
            self.assertEqual(response.status_code, 400)
            self.assert_unchanged()

    def test_inactive_wrong_kind_and_capacity_are_rejected(self):
        for field in ('source_boiler_id', 'destination_workshop_id'):
            for value in (True, 1.5, 'bad', 0, -1, 2 ** 63):
                with self.subTest(field=field, value=value):
                    self.assertEqual(self.send(self.payload(**{field: value})).status_code, 400)
        self.assertEqual(self.send(self.payload(source_boiler_id=self.workshop.pk)).status_code, 400)
        self.assertEqual(self.send(self.payload(destination_workshop_id=self.boiler.pk)).status_code, 400)
        self.assertEqual(self.send(self.payload(volume_liters='100.001')).status_code, 400)
        for container in (self.boiler, self.workshop):
            container.is_active = False
            container.save(update_fields=['is_active'])
            self.assertEqual(self.send().status_code, 400)
            container.is_active = True
            container.save(update_fields=['is_active'])
        self.assert_unchanged()

    def test_idempotency_checks_amount_destination_and_operation(self):
        payload = self.payload()
        first = self.send(payload)
        self.assertEqual(first.status_code, 201)
        self.assertEqual(self.send(payload).status_code, 200)
        for updates in ({'volume_liters': '1'}, {'destination_workshop_id': self.other_workshop.pk}):
            self.assertEqual(self.send({**payload, **updates}).status_code, 409)
        other = MaterialMovement.objects.create(
            movement_number='OTHER-OPERATION', movement_type='tank_to_boiler', created_by=self.admin,
            volume_liters=1, idempotency_key='other-operation',
        )
        self.assertEqual(self.send(self.payload(idempotency_key=other.idempotency_key)).status_code, 409)
        self.assertEqual(MaterialMovement.objects.filter(movement_type='boiler_to_reactor').count(), 1)

    def test_compensation_restores_balances(self):
        movement_id = self.send().json()['id']
        response = self.client.post(f'/api/processing/movements/{movement_id}/compensate/',
                                   data=json.dumps({'reason': 'Исправление теста'}), content_type='application/json', **self.headers)
        self.assertEqual(response.status_code, 201, response.content)
        self.boiler.refresh_from_db()
        self.workshop.refresh_from_db()
        self.assertEqual(self.boiler.current_volume_liters, 200)
        self.assertEqual(self.workshop.current_volume_liters, 0)
        self.assertEqual(MaterialMovement.objects.count(), 2)

    def test_module_grants_only_boiler_and_workshop_references_and_loading(self):
        user = get_user_model().objects.create_user('workshop-loading-operator')
        group = AccessGroup.objects.create(name='Загрузка цеха в тесте')
        access = GroupModuleAccess.objects.create(group=group, module=Module.objects.get(code='workshop-loading'))
        access.permissions.add(Permission.objects.get(code='view'))
        UserProfile.objects.update_or_create(user=user, defaults={'group': group})
        headers = {'HTTP_AUTHORIZATION': f'Bearer {create_access_token(user)}'}
        for path in ('preheating-boilers', 'workshops'):
            self.assertEqual(self.client.get(f'/api/processing/{path}/', **headers).status_code, 200)
        for path in ('receiving-tanks', 'chemical-mixers', 'raw-diesel-tanks'):
            self.assertEqual(self.client.get(f'/api/processing/{path}/', **headers).status_code, 403)
        self.assertEqual(self.send(headers=headers).status_code, 403)
        access.permissions.add(Permission.objects.get(code='create'))
        self.assertEqual(self.send(headers=headers).status_code, 201)

    def test_removed_endpoints_and_permissions_are_unavailable(self):
        for path in ('separators', 'movements/boiler-to-chemical-mixer', 'movements/chemical-mixer-to-workshop', 'movements/boiler-to-separator', 'movements/separator-output', 'movements/separator-to-chemical-mixer'):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(f'/api/processing/{path}/', **self.headers).status_code, 404)
                self.assertEqual(self.client.post(f'/api/processing/{path}/', data='{}', content_type='application/json', **self.headers).status_code, 404)
        self.assertFalse(Module.objects.filter(code__in=('separator-loading', 'separator-output')).exists())


class ConcurrentBoilerWorkshopTests(BoilerWorkshopFixture, TransactionTestCase):
    def parallel(self, payloads):
        barrier = threading.Barrier(len(payloads))

        def send(payload):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                return self.send(payload).status_code
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=len(payloads)) as executor:
            return sorted(executor.map(send, payloads))

    def test_parallel_loadings_cannot_overdraw_boiler(self):
        self.boiler.current_volume_liters = 100
        self.boiler.save(update_fields=['current_volume_liters'])
        self.assertEqual(self.parallel([self.payload(), self.payload(destination_workshop_id=self.other_workshop.pk)]), [201, 400])
        self.assertEqual(MaterialMovement.objects.count(), 1)

    def test_parallel_duplicate_is_posted_once(self):
        payload = self.payload()
        self.assertEqual(self.parallel([payload, payload]), [200, 201])
        self.assertEqual(MaterialMovement.objects.count(), 1)

    def test_same_key_with_different_amounts_conflicts(self):
        payload = self.payload()
        self.assertEqual(self.parallel([payload, {**payload, 'volume_liters': '1'}]), [201, 409])
        self.assertEqual(MaterialMovement.objects.count(), 1)
