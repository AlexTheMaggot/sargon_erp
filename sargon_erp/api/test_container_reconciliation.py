import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from django.contrib.auth import get_user_model
from django.db import close_old_connections
from django.test import Client, TestCase, TransactionTestCase

from .auth import create_access_token
from .models import AccessGroup, ContainerMeasurement, ContainerReconciliation, ContainerReconciliationRevision, MaterialMovement, ProductionContainer, UserProfile


API = '/api/processing/container-reconciliations/'


class ReconciliationFixture:
    def setUp(self):
        self.admin = get_user_model().objects.create_superuser('reconciliation-admin')
        self.headers = {'HTTP_AUTHORIZATION': f'Bearer {create_access_token(self.admin)}'}
        self.tank = self.make_container('receiving_tank', 100)
        self.boiler = self.make_container('preheating_boiler', 50)

    def make_container(self, kind, volume=0, product='', number=991, active=True):
        return ProductionContainer.objects.create(
            kind=kind, number=number, system_code=f'reconciliation-{kind}-{number}', capacity_liters=200,
            current_volume_liters=volume, oil_product=product, is_active=active,
        )

    def row(self, container, actual, product=''):
        container.refresh_from_db()
        return {'container_id': container.pk, 'version': container.updated_at.isoformat(),
                'actual_liters': actual, 'oil_product': product}

    def post(self, rows, previous=None, headers=None):
        body = {'measurements': rows}
        if previous:
            body.update(reconciliation_id=previous['id'], base_revision_id=previous['latest_revision']['id'])
        return Client().post(API, json.dumps(body), content_type='application/json', **(headers or self.headers))

    def transfer(self, volume='5'):
        response = Client().post('/api/processing/movements/tank-to-boiler/', json.dumps({
            'source_tank_id': self.tank.pk, 'destination_boiler_id': self.boiler.pk,
            'volume_liters': volume, 'idempotency_key': f'reconciliation-transfer-{MaterialMovement.objects.count()}',
        }), content_type='application/json', **self.headers)
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()['id']


class ContainerReconciliationTests(ReconciliationFixture, TestCase):
    def test_manager_can_save_and_see_history_without_dashboard_or_equipment_access(self):
        group = AccessGroup.objects.get(name='Заведующий складом')
        self.assertEqual(list(group.modules.values_list('code', flat=True)), ['container-reconciliation'])
        self.assertEqual(group.start_module.default_path, '/processing/reconciliation')
        operator = get_user_model().objects.create_user('reconciliation-operator')
        UserProfile.objects.filter(user=operator).update(group=group)
        headers = {'HTTP_AUTHORIZATION': f'Bearer {create_access_token(operator)}'}
        listing = self.client.get(API, **headers)
        self.assertEqual(listing.status_code, 200)
        self.assertIn(self.tank.pk, [row['id'] for row in listing.json()['containers']])
        for path in ('/api/dashboard/overview/', '/api/processing/receiving-tanks/', '/api/processing/journal/'):
            self.assertEqual(self.client.get(path, **headers).status_code, 403)
        saved = self.post([self.row(self.tank, '90')], headers=headers)
        self.assertEqual(saved.status_code, 201, saved.content)
        self.assertEqual(saved.json()['latest_revision']['operator'], operator.username)
        url = f"{API}{saved.json()['id']}/"
        self.assertEqual(self.client.get(url, **headers).status_code, 200)
        self.assertEqual(self.client.delete(url, **headers).status_code, 405)
        outsider = get_user_model().objects.create_user('reconciliation-outsider')
        denied = {'HTTP_AUTHORIZATION': f'Bearer {create_access_token(outsider)}'}
        self.assertEqual(self.client.get(API, **denied).status_code, 403)
        self.assertEqual(self.post([self.row(self.tank, '100')], headers=denied).status_code, 403)

    def test_partial_save_zero_and_unchanged_are_different(self):
        spare = self.make_container('receiving_tank', 70, number=992)
        skipped = self.row(spare, '')
        saved = self.post([self.row(self.tank, '0'), skipped, self.row(self.boiler, '50')])
        self.assertEqual(saved.status_code, 201, saved.content)
        self.tank.refresh_from_db()
        spare.refresh_from_db()
        self.assertEqual(self.tank.current_volume_liters, 0)
        self.assertEqual(spare.updated_at.isoformat(), skipped['version'])
        self.assertEqual(spare.current_volume_liters, 70)
        self.assertEqual(saved.json()['summary']['measured_count'], 2)
        self.assertEqual(saved.json()['summary']['difference_liters'], '-100.000')
        self.assertEqual(ContainerMeasurement.objects.count(), 2)
        self.assertEqual(MaterialMovement.objects.count(), 0)
        self.assertEqual(self.post([skipped]).status_code, 400)

    def test_net_absolute_and_coverage_use_measurements_from_one_walk(self):
        spare = self.make_container('receiving_tank', 50, number=992)
        previous = self.post([self.row(spare, '47')]).json()
        saved = self.post([self.row(self.tank, '90'), self.row(self.boiler, '60')]).json()
        self.assertEqual(saved['summary']['deviation_percent'], '0.00')
        self.assertEqual(saved['summary']['absolute_deviation_percent'], '13.33')
        self.transfer()
        overview = self.client.get('/api/dashboard/overview/', **self.headers).json()['reconciliation']
        self.assertEqual(overview['latest']['reconciliation_id'], saved['id'])
        self.assertEqual(overview['latest']['difference_liters'], '0.000')
        receiving = overview['stages']['receiving_tank']
        self.assertEqual(receiving['summary']['deviation_percent'], '-10.00')
        self.assertEqual(receiving['summary']['measured_count'], 1)
        self.assertEqual(next(item for item in receiving['containers'] if item['id'] == spare.pk)['measurement']['revision_id'],
                         previous['latest_revision']['id'])

    def test_supplement_and_correction_keep_baseline_and_old_versions(self):
        saved = self.post([self.row(self.tank, '85')]).json()
        updated = self.post([self.row(self.tank, '95'), self.row(self.boiler, '60')], previous=saved)
        self.assertEqual(updated.status_code, 201, updated.content)
        detail = updated.json()
        self.assertEqual(detail['id'], saved['id'])
        self.assertEqual(detail['latest_revision']['number'], 2)
        self.assertEqual(detail['summary']['expected_liters'], '150.000')
        self.assertEqual(detail['summary']['difference_liters'], '5.000')
        current = next(row for row in detail['measurements'] if row['container_id'] == self.tank.pk)
        self.assertEqual(current['previous_liters'], '85.000')
        self.assertEqual(current['expected_liters'], '100.000')
        self.assertEqual(detail['revisions'][1]['measurements'][0]['actual_liters'], '85.000')
        stale_version = self.post([self.row(self.boiler, '62')], previous=saved)
        self.assertEqual(stale_version.status_code, 409)
        supplemental = self.make_container('receiving_tank', 50, number=992)
        final = self.post([self.row(supplemental, '45')], previous=detail).json()
        self.assertEqual(final['summary']['measured_count'], 3)
        self.assertEqual(final['summary']['difference_liters'], '0.000')

    def test_stale_balance_and_later_movement_prevent_overwrite(self):
        saved = self.post([self.row(self.tank, '90')]).json()
        stale = self.row(self.tank, '87')
        self.transfer()
        self.assertEqual(self.post([stale, self.row(self.boiler, '20')]).status_code, 409)
        self.assertEqual(self.post([self.row(self.tank, '87')], previous=saved).status_code, 409)
        self.tank.refresh_from_db()
        self.boiler.refresh_from_db()
        self.assertEqual(self.tank.current_volume_liters, 85)
        self.assertEqual(self.boiler.current_volume_liters, 55)
        self.assertEqual(ContainerReconciliationRevision.objects.count(), 1)
        fresh = self.post([self.row(self.tank, '87')])
        self.assertEqual(fresh.status_code, 201, fresh.content)

    def test_shared_line_product_and_zero_baseline(self):
        mixer = self.make_container('chemical_mixer')
        finishing = self.make_container('finishing_mixer', 50, 'diesel')
        self.assertEqual(self.post([self.row(mixer, '5')]).status_code, 400)
        self.assertEqual(self.post([self.row(mixer, '5', 'spindle')]).status_code, 400)
        saved = self.post([self.row(mixer, '5', 'spindle'), self.row(finishing, '0')])
        self.assertEqual(saved.status_code, 201, saved.content)
        mixing = self.post([self.row(finishing, '5', 'diesel')])
        self.assertEqual(mixing.status_code, 400)
        mixer.refresh_from_db()
        finishing.refresh_from_db()
        self.assertEqual(mixer.oil_product, 'spindle')
        self.assertEqual(finishing.oil_product, '')
        row = next(row for row in saved.json()['measurements'] if row['container_id'] == mixer.pk)
        self.assertIsNone(row['deviation_percent'])
        self.assertEqual(row['difference_liters'], '5.000')

    def test_invalid_rows_and_scope_reject_entire_submission(self):
        inactive = self.make_container('chemical_mixer', active=False)
        tank = self.row(self.tank, '75')
        for actual in ('-1', '201', '0.0001', 'NaN', 'Infinity', True, []):
            with self.subTest(actual=actual):
                self.assertEqual(self.post([tank, self.row(self.boiler, actual)]).status_code, 400)
        self.assertEqual(self.post([tank, tank]).status_code, 400)
        self.assertEqual(self.post([tank, self.row(inactive, '0')]).status_code, 409)
        manufacturing = self.make_container('concentrate_reactor')
        self.assertEqual(self.post([tank, self.row(manufacturing, '0')]).status_code, 409)
        self.tank.refresh_from_db()
        self.assertEqual(self.tank.current_volume_liters, 100)
        self.assertFalse(ContainerReconciliation.objects.exists())

    def test_reconciled_movements_and_measured_empty_equipment_remain_in_history(self):
        movement_id = self.transfer()
        saved = self.post([self.row(self.tank, '0')])
        self.assertEqual(saved.status_code, 201)
        reversal = self.client.post(f'/api/processing/movements/{movement_id}/compensate/', json.dumps({
            'reason': 'Ошибочный перелив',
        }), content_type='application/json', **self.headers)
        self.assertEqual(reversal.status_code, 400)
        self.assertIn('сверке', reversal.json()['detail'])
        deletion = self.client.delete(f'/api/processing/containers/{self.tank.pk}/', **self.headers)
        self.assertEqual(deletion.status_code, 400)
        self.assertFalse(MaterialMovement.objects.get(pk=movement_id).is_compensated)


class ConcurrentReconciliationTests(ReconciliationFixture, TransactionTestCase):
    def test_stale_parallel_submission_cannot_overwrite_a_saved_reconciliation(self):
        first = self.row(self.tank, '80')
        second = {**first, 'actual_liters': '60'}
        barrier = Barrier(2)

        def submit(row):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                return self.post([row]).status_code
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            self.assertEqual(sorted(executor.map(submit, [first, second])), [201, 409])
        self.assertEqual(ContainerMeasurement.objects.count(), 1)
        self.tank.refresh_from_db()
        self.assertEqual(self.tank.current_volume_liters, ContainerMeasurement.objects.get().actual_liters)
