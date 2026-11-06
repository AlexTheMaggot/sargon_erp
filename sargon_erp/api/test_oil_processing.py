import json
import threading
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.db import close_old_connections, IntegrityError, transaction
from django.test import Client, TestCase, TransactionTestCase
from django.utils import timezone

from .auth import create_access_token
from .models import AccessGroup, GroupModuleAccess, MaterialMovement, Module, Permission, ProductionContainer, UserProfile


class OilProcessingFixture:
    def setUp(self):
        self.admin = get_user_model().objects.create_superuser('oil-test-admin')
        self.token = create_access_token(self.admin)
        self.containers = {}
        for kind in (
            'raw_diesel_tank', 'raw_spindle_tank', 'sorption_system', 'finishing_mixer',
            'finishing_filter', 'finished_diesel_tank', 'finished_spindle_tank',
        ):
            self.containers[kind] = ProductionContainer.objects.create(
                kind=kind, number=99, system_code=f'oil-test-{kind}', capacity_liters=1000,
                current_volume_liters=500 if kind.startswith('raw_') else 0,
            )

    def post(self, step, source, destination, volume='100', key=None, token=None):
        return Client().post(
            f'/api/processing/oil-movements/{step}/',
            data=json.dumps({'source_id': self.containers[source].pk, 'destination_id': self.containers[destination].pk,
                             'volume_liters': volume, 'idempotency_key': key or str(uuid4())}),
            content_type='application/json', HTTP_AUTHORIZATION=f'Bearer {token or self.token}',
        )

    def compensate(self, movement_id):
        return self.client.post(f'/api/processing/movements/{movement_id}/compensate/',
                                data=json.dumps({'reason': 'Тест отмены'}), content_type='application/json',
                                HTTP_AUTHORIZATION=f'Bearer {self.token}')

    def chain(self, product, volume='100'):
        result = []
        for step, source, destination in (
            ('sorption-loading', f'raw_{product}_tank', 'sorption_system'),
            ('finishing-mixer-loading', 'sorption_system', 'finishing_mixer'),
            ('finishing-filter-loading', 'finishing_mixer', 'finishing_filter'),
            ('finished-product-loading', 'finishing_filter', f'finished_{product}_tank'),
        ):
            response = self.post(step, source, destination, volume)
            self.assertEqual(response.status_code, 201, response.content)
            result.append(response.json())
        return result


class OilProcessingTests(OilProcessingFixture, TestCase):
    def test_full_chain_tracks_products_and_releases_line_only_after_drain(self):
        self.chain('diesel')
        self.chain('spindle', '125.500')
        for product, expected in [('diesel', Decimal('100')), ('spindle', Decimal('125.500'))]:
            tank = self.containers[f'finished_{product}_tank']
            tank.refresh_from_db()
            self.assertEqual(tank.current_volume_liters, expected)
        for kind in ProductionContainer.SHARED_OIL_KINDS:
            container = self.containers[kind]
            container.refresh_from_db()
            self.assertEqual(container.current_volume_liters, 0)
            self.assertEqual(container.oil_product, '')
        self.assertEqual(MaterialMovement.objects.count(), 8)

    def test_mixing_is_blocked_while_product_is_anywhere_on_shared_line(self):
        self.post('sorption-loading', 'raw_diesel_tank', 'sorption_system')
        self.post('finishing-mixer-loading', 'sorption_system', 'finishing_mixer')
        response = self.post('sorption-loading', 'raw_spindle_tank', 'sorption_system')
        self.assertEqual(response.status_code, 400)
        self.assertIn('линия', response.json()['detail'])
        self.assertEqual(MaterialMovement.objects.count(), 2)
        self.containers['raw_spindle_tank'].refresh_from_db()
        self.assertEqual(self.containers['raw_spindle_tank'].current_volume_liters, 500)

    def test_invalid_volume_source_overflow_and_wrong_stage_do_not_mutate(self):
        for amount in ('0', '-1', '1.0001', 'NaN', 'Infinity', '1e99999', '501', [], None):
            with self.subTest(amount=amount):
                self.assertEqual(self.post('sorption-loading', 'raw_diesel_tank', 'sorption_system', amount).status_code, 400)
        self.assertEqual(self.post('finishing-mixer-loading', 'raw_diesel_tank', 'finishing_mixer').status_code, 400)
        self.containers['sorption_system'].capacity_liters = 10
        self.containers['sorption_system'].save()
        self.assertEqual(self.post('sorption-loading', 'raw_diesel_tank', 'sorption_system', '11').status_code, 400)
        self.assertEqual(MaterialMovement.objects.count(), 0)

    def test_idempotency_matches_payload_and_operation(self):
        first = self.post('sorption-loading', 'raw_diesel_tank', 'sorption_system', key='oil-duplicate')
        second = self.post('sorption-loading', 'raw_diesel_tank', 'sorption_system', key='oil-duplicate')
        changed = self.post('sorption-loading', 'raw_diesel_tank', 'sorption_system', volume='101', key='oil-duplicate')
        different = self.post('finishing-mixer-loading', 'sorption_system', 'finishing_mixer', key='oil-duplicate')
        self.assertEqual([first.status_code, second.status_code, changed.status_code, different.status_code], [201, 200, 409, 409])
        self.assertEqual(first.json()['id'], second.json()['id'])
        self.assertEqual(MaterialMovement.objects.count(), 1)

    def test_finished_tank_kind_cannot_be_swapped(self):
        self.post('sorption-loading', 'raw_diesel_tank', 'sorption_system')
        self.post('finishing-mixer-loading', 'sorption_system', 'finishing_mixer')
        self.post('finishing-filter-loading', 'finishing_mixer', 'finishing_filter')
        response = self.post('finished-product-loading', 'finishing_filter', 'finished_spindle_tank')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(MaterialMovement.objects.count(), 3)

    def test_compensations_reverse_chain_and_preserve_history(self):
        movements = self.chain('diesel')
        self.assertEqual(self.compensate(movements[0]['id']).status_code, 400)
        for movement in reversed(movements):
            response = self.compensate(movement['id'])
            self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(self.compensate(movements[-1]['id']).status_code, 400)
        self.containers['raw_diesel_tank'].refresh_from_db()
        self.assertEqual(self.containers['raw_diesel_tank'].current_volume_liters, 500)
        self.assertEqual(MaterialMovement.objects.filter(is_compensated=True).count(), 4)
        self.assertEqual(MaterialMovement.objects.count(), 8)

    def test_compensation_cannot_return_other_product_into_busy_line(self):
        movements = self.chain('diesel')
        self.post('sorption-loading', 'raw_spindle_tank', 'sorption_system')
        self.assertEqual(self.compensate(movements[-1]['id']).status_code, 400)
        self.containers['finished_diesel_tank'].refresh_from_db()
        self.assertEqual(self.containers['finished_diesel_tank'].current_volume_liters, 100)

    def test_read_only_and_single_form_permissions(self):
        operator = get_user_model().objects.create_user('oil-test-operator')
        group = AccessGroup.objects.create(name='Oil test group')
        module = Module.objects.get(code='sorption-loading')
        access = GroupModuleAccess.objects.create(group=group, module=module)
        access.permissions.add(Permission.objects.get(code='view'))
        UserProfile.objects.filter(user=operator).update(group=group)
        token = create_access_token(operator)
        headers = {'HTTP_AUTHORIZATION': f'Bearer {token}'}
        for path in ('/api/processing/raw-diesel-tanks/', '/api/processing/raw-spindle-tanks/',
                     '/api/processing/oil-containers/sorption-systems/', '/api/processing/oil-movements/sorption-loading/'):
            self.assertEqual(self.client.get(path, **headers).status_code, 200)
        self.assertEqual(self.client.get('/api/processing/oil-containers/finishing-filters/', **headers).status_code, 403)
        self.assertEqual(self.post('sorption-loading', 'raw_diesel_tank', 'sorption_system', token=token).status_code, 403)
        access.permissions.add(Permission.objects.get(code='create'))
        self.assertEqual(self.post('sorption-loading', 'raw_diesel_tank', 'sorption_system', token=token).status_code, 201)
        self.assertEqual(self.post('finishing-mixer-loading', 'sorption_system', 'finishing_mixer', token=token).status_code, 403)
        self.assertEqual(self.client.post('/api/processing/oil-containers/sorption-systems/', data='{}', content_type='application/json', **headers).status_code, 403)
        self.assertEqual(self.client.get('/api/processing/journal/', **headers).status_code, 403)

    def test_container_admin_crud_and_database_product_constraint(self):
        headers = {'HTTP_AUTHORIZATION': f'Bearer {self.token}'}
        created = self.client.post('/api/processing/oil-containers/sorption-systems/',
                                   data=json.dumps({'number': 7, 'capacity_liters': 100}), content_type='application/json', **headers)
        self.assertEqual(created.status_code, 201)
        self.assertEqual(self.client.delete(f"/api/processing/containers/{created.json()['id']}/", **headers).status_code, 200)
        with self.assertRaises(IntegrityError), transaction.atomic():
            ProductionContainer.objects.filter(pk=self.containers['sorption_system'].pk).update(current_volume_liters=1)

    def test_inactive_containers_and_malformed_requests_are_rejected(self):
        self.containers['sorption_system'].is_active = False
        self.containers['sorption_system'].save()
        self.assertEqual(self.post('sorption-loading', 'raw_diesel_tank', 'sorption_system').status_code, 400)
        url = '/api/processing/oil-movements/sorption-loading/'
        headers = {'HTTP_AUTHORIZATION': f'Bearer {self.token}'}
        for body in ('[]', 'null', '{'):
            self.assertEqual(self.client.post(url, data=body, content_type='application/json', **headers).status_code, 400)
        self.assertEqual(self.client.get(url).status_code, 401)
        self.assertEqual(self.client.patch(url, **headers).status_code, 405)
        self.assertEqual(MaterialMovement.objects.count(), 0)

    def test_separator_overview_excludes_cancelled_discharge(self):
        MaterialMovement.objects.create(
            movement_number='water-actual', movement_type=MaterialMovement.TYPE_SEPARATOR_OUTPUT,
            product_name=MaterialMovement.PRODUCT_TECHNICAL_WATER, volume_liters='12.250', moved_at=timezone.now(),
        )
        MaterialMovement.objects.create(
            movement_number='water-cancelled', movement_type=MaterialMovement.TYPE_SEPARATOR_OUTPUT,
            product_name=MaterialMovement.PRODUCT_TECHNICAL_WATER, volume_liters='5', is_compensated=True,
        )
        response = self.client.get('/api/dashboard/overview/', HTTP_AUTHORIZATION=f'Bearer {self.token}')
        self.assertEqual(response.json()['oil_finishing']['separator_outputs']['water'], {
            'today_liters': '12.250', 'total_liters': '12.250',
        })

    def test_overview_and_paginated_history_are_real(self):
        self.chain('diesel')
        headers = {'HTTP_AUTHORIZATION': f'Bearer {self.token}'}
        data = self.client.get('/api/dashboard/overview/', **headers).json()['oil_finishing']
        self.assertEqual(Decimal(data['finished_diesel_tank']['current_volume_liters']), 100)
        self.assertEqual(data['finished_spindle_tank']['current_volume_liters'], '0.000')
        self.assertEqual(data['sorption_system']['items'][0]['oil_product'], '')
        for index in range(11):
            self.assertEqual(self.post('sorption-loading', 'raw_diesel_tank', 'sorption_system', '1', key=f'page-{index}').status_code, 201)
        history = self.client.get('/api/processing/oil-movements/sorption-loading/?page=2', **headers).json()
        self.assertEqual(history['total'], 12)
        self.assertEqual(len(history['items']), 2)


class ConcurrentOilProcessingTests(OilProcessingFixture, TransactionTestCase):
    def parallel(self, requests):
        barrier = threading.Barrier(len(requests))

        def send(arguments):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                if arguments[0] == 'compensate':
                    return self.compensate(arguments[1]).status_code
                return self.post(*arguments).status_code
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=len(requests)) as executor:
            return sorted(executor.map(send, requests))

    def test_simultaneous_different_products_cannot_occupy_line(self):
        self.containers['sorption_other'] = ProductionContainer.objects.create(
            kind='sorption_system', number=100, system_code='oil-test-other-sorption', capacity_liters=1000,
        )
        statuses = self.parallel([
            ('sorption-loading', 'raw_diesel_tank', 'sorption_system', '100', 'parallel-diesel'),
            ('sorption-loading', 'raw_spindle_tank', 'sorption_other', '100', 'parallel-spindle'),
        ])
        self.assertEqual(statuses, [201, 400])
        self.assertEqual(MaterialMovement.objects.count(), 1)

    def test_compensation_and_new_product_cannot_mix_on_different_line_stages(self):
        movements = self.chain('diesel')
        statuses = self.parallel([
            ('compensate', movements[-1]['id']),
            ('sorption-loading', 'raw_spindle_tank', 'sorption_system', '100', 'parallel-after-compensation'),
        ])
        self.assertEqual(statuses, [201, 400])
        products = set(ProductionContainer.objects.filter(
            kind__in=ProductionContainer.SHARED_OIL_KINDS, current_volume_liters__gt=0,
        ).values_list('oil_product', flat=True))
        self.assertEqual(len(products), 1)

    def test_concurrent_duplicate_and_overdraw(self):
        request = ('sorption-loading', 'raw_diesel_tank', 'sorption_system', '400', 'parallel-duplicate')
        self.assertEqual(self.parallel([request, request]), [200, 201])
        self.assertEqual(self.parallel([
            ('sorption-loading', 'raw_diesel_tank', 'sorption_system', '75', 'parallel-first'),
            ('sorption-loading', 'raw_diesel_tank', 'sorption_system', '75', 'parallel-second'),
        ]), [201, 400])
        self.containers['raw_diesel_tank'].refresh_from_db()
        self.assertEqual(self.containers['raw_diesel_tank'].current_volume_liters, 25)
