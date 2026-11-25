from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.db import close_old_connections
from django.test import Client, TestCase, TransactionTestCase

from .auth import create_access_token
from .models import AccessGroup, ContainerMeasurement, GroupModuleAccess, MaterialMovement, Module, Permission, ProductionContainer, ReceiverRun, UserProfile


RECEIVERS = '/api/processing/receiver-runs/'
LOAD = '/api/processing/movements/boiler-to-workshop/'
DIESEL = '/api/processing/movements/workshop-to-raw-diesel-tank/'
SPINDLE = '/api/processing/movements/workshop-to-raw-spindle-tank/'
NIGROL = '/api/processing/movements/workshop-to-nigrol-tank/'
RECONCILIATION = '/api/processing/container-reconciliations/'


class ReactorFixture:
    def setUp(self):
        self.admin = get_user_model().objects.create_superuser('receiver-admin')
        self.headers = self.authorization(self.admin)
        self.reactor = self.make_equipment('processing_workshop', 991, 60)
        self.second = self.make_equipment('processing_workshop', 992)
        self.boiler = self.make_equipment('preheating_boiler', 991, 200)
        self.diesel = self.make_equipment('raw_diesel_tank', 991)
        self.spindle = self.make_equipment('raw_spindle_tank', 991)
        self.nigrol = self.make_equipment('nigrol_tank', 991)

    def make_equipment(self, kind, number, volume=0):
        return ProductionContainer.objects.create(kind=kind, number=number, system_code=f'test-{kind}-{number}',
                                                 capacity_liters=200, current_volume_liters=volume)

    def authorization(self, user):
        return {'HTTP_AUTHORIZATION': f'Bearer {create_access_token(user)}'}

    def post(self, path, payload, headers=None, client=None):
        return (client or self.client).post(path, {'idempotency_key': str(uuid4()), **payload},
                                            content_type='application/json', **(headers or self.headers))

    def load(self, reactor=None):
        result = self.post(LOAD, {'source_boiler_id': self.boiler.pk,
                                 'destination_workshop_id': (reactor or self.reactor).pk, 'volume_liters': '25'})
        self.assertEqual(result.status_code, 201, result.content)
        return result.json()['id']

    def receiver(self, number, loading_id, reactor=None, run_id=None, **extra):
        return self.post(RECEIVERS, {
            'reactor_id': (reactor or self.reactor).pk, 'number': number, 'loading_id': loading_id,
            'action': 'close' if run_id else 'open', 'run_id': run_id, **extra,
        })

    def open_and_close(self, number, loading):
        opened = self.receiver(number, loading)
        self.assertEqual(opened.status_code, 201, opened.content)
        run_id = opened.json()['id']
        closed = self.receiver(number, loading, run_id=run_id)
        self.assertEqual(closed.status_code, 200, closed.content)
        return run_id

    def drain(self, number, run_id, **extra):
        path, tank = (DIESEL, self.diesel) if number == 1 else (SPINDLE, self.spindle)
        return self.post(path, {'receiver_run_id': run_id, 'destination_tank_id': tank.pk, 'volume_liters': '8.125', **extra})

    def state(self, reactor=None):
        result = self.client.get(RECEIVERS, {'reactor_id': (reactor or self.reactor).pk}, **self.headers)
        self.assertEqual(result.status_code, 200)
        return result.json()['reactor']


class ReactorReceiverTests(ReactorFixture, TestCase):
    def test_strict_sequence_repeats_spindle_and_each_receiver_needs_full_drain(self):
        self.assertIsNone(self.state()['next_receiver'])
        self.assertEqual(len(self.state()['receivers']), 4)
        loading = self.load()
        self.assertEqual(self.state()['next_receiver'], 1)
        self.assertEqual(self.receiver(2, loading).status_code, 409)

        first_run = self.receiver(1, loading)
        self.assertEqual(first_run.status_code, 201)
        first_run_id = first_run.json()['id']
        self.assertEqual(self.receiver(2, loading).status_code, 409)
        self.assertEqual(self.drain(1, first_run_id).status_code, 409)
        closed = self.receiver(1, loading, run_id=first_run_id)
        self.assertEqual(closed.status_code, 200)
        self.assertLessEqual(closed.json()['opened_at'], closed.json()['closed_at'])
        self.assertEqual(closed.json()['closed_by'], self.admin.username)

        second_run = self.receiver(2, loading)
        self.assertEqual(second_run.status_code, 201)
        self.assertEqual(self.drain(1, first_run_id).status_code, 201)
        self.assertEqual(self.receiver(2, loading, run_id=second_run.json()['id']).status_code, 200)
        self.open_and_close(3, loading)
        self.open_and_close(4, loading)
        self.assertEqual(self.state()['next_receiver'], 2)
        self.assertEqual(self.receiver(1, loading).status_code, 409)
        self.assertEqual(self.receiver(2, loading).status_code, 409)
        self.assertEqual(self.drain(2, second_run.json()['id']).status_code, 201)
        self.assertEqual(self.receiver(2, loading).status_code, 201)

    def test_load_during_open_receiver_resets_next_only_in_its_reactor(self):
        loading = self.load()
        other_loading = self.load(self.second)
        self.assertEqual(self.receiver(1, other_loading, self.second).status_code, 201)
        first_run = self.open_and_close(1, loading)
        self.assertEqual(self.drain(1, first_run).status_code, 201)
        second_run = self.receiver(2, loading).json()['id']
        reloaded = self.load()
        self.assertEqual(self.state()['open_receiver'], 2)
        self.assertEqual(self.state()['next_receiver'], 1)
        self.assertEqual(self.receiver(1, reloaded).status_code, 409)
        self.assertEqual(self.receiver(2, loading, run_id=second_run).status_code, 200)
        self.assertEqual(self.receiver(3, reloaded).status_code, 409)
        self.assertEqual(self.receiver(1, loading).status_code, 409)
        self.assertEqual(self.receiver(1, reloaded).status_code, 201)
        self.assertEqual(self.state(self.second)['open_receiver'], 1)

    def test_discharge_has_one_destination_and_can_be_retried_without_double_credit(self):
        loading = self.load()
        run_id = self.open_and_close(1, loading)
        self.assertEqual(self.drain(2, run_id).status_code, 409)
        self.assertEqual(self.drain(1, run_id, destination_tank_id=self.spindle.pk).status_code, 400)
        self.assertEqual(self.drain(1, run_id, volume_liters='200.001').status_code, 400)
        key = str(uuid4())
        first = self.drain(1, run_id, idempotency_key=key)
        self.assertEqual(first.status_code, 201, first.content)
        self.assertEqual(self.drain(1, run_id, idempotency_key=key).status_code, 200)
        self.assertEqual(self.drain(1, run_id).status_code, 409)
        self.assertEqual(self.drain(1, run_id, idempotency_key=key, volume_liters='1').status_code, 409)
        self.diesel.refresh_from_db()
        self.reactor.refresh_from_db()
        self.assertEqual(self.diesel.current_volume_liters, Decimal('8.125'))
        self.assertEqual(self.reactor.current_volume_liters, 60)
        self.assertEqual(first.json()['receiver_run_id'], run_id)
        self.assertEqual(self.state()['receivers'][0]['run']['status'], 'drained')

    def test_last_actual_remains_unchanged_by_loading_nigrol_and_late_drain(self):
        loading = self.load()
        run_id = self.open_and_close(1, loading)
        self.reactor.refresh_from_db()
        saved = self.post(RECONCILIATION, {'measurements': [{
            'container_id': self.reactor.pk, 'version': self.reactor.updated_at.isoformat(), 'actual_liters': '42.125',
        }]})
        self.assertEqual(saved.status_code, 201, saved.content)
        self.assertEqual(saved.json()['summary']['comparable_count'], 0)
        row = saved.json()['measurements'][0]
        self.assertIsNone(row['expected_liters'])
        self.assertEqual(row['actual_liters'], '42.125')
        self.assertIsNone(ContainerMeasurement.objects.get().expected_liters)
        self.assertEqual(self.drain(1, run_id).status_code, 201)
        self.assertEqual(self.post(NIGROL, {
            'source_workshop_id': self.reactor.pk, 'destination_tank_id': self.nigrol.pk, 'volume_liters': '5',
        }).status_code, 201)
        self.load()
        overview = self.client.get('/api/dashboard/overview/', **self.headers).json()
        reactor = next(item for item in overview['processing_reactors']['items'] if item['id'] == self.reactor.pk)
        self.assertEqual(reactor['measured_liters'], '42.125')
        self.assertEqual(reactor['measured_at'], row['measured_at'])
        self.assertEqual(overview['nigrol_tanks']['items'][0]['current_volume_liters'], '5.000')

    def test_access_is_isolated_and_used_loading_cannot_be_cancelled(self):
        loading = self.load()
        run_id = self.open_and_close(1, loading)
        cancelled = self.post(f'/api/processing/movements/{loading}/compensate/', {'reason': 'Проверка'})
        self.assertEqual(cancelled.status_code, 400)
        operator = get_user_model().objects.create_user('receiver-outlet-operator')
        group = AccessGroup.objects.create(name='Только слив солярки')
        UserProfile.objects.update_or_create(user=operator, defaults={'group': group})
        access = GroupModuleAccess.objects.create(group=group, module=Module.objects.get(code='raw-diesel-tank-loading'))
        access.permissions.add(Permission.objects.get(code='view'))
        headers = self.authorization(operator)
        self.assertEqual(self.client.get(RECEIVERS, **headers).status_code, 403)
        self.assertEqual(self.client.get(SPINDLE, **headers).status_code, 403)
        self.assertEqual(self.client.get(DIESEL, **headers).json()['items'][0]['id'], run_id)
        payload = {'receiver_run_id': run_id, 'destination_tank_id': self.diesel.pk, 'volume_liters': '8'}
        self.assertEqual(self.post(DIESEL, payload, headers).status_code, 403)
        access.permissions.add(Permission.objects.get(code='create'))
        self.assertEqual(self.post(DIESEL, payload, headers).status_code, 201)

    def test_drain_cancellation_releases_slot_without_inventing_balance(self):
        loading = self.load()
        run_id = self.open_and_close(1, loading)
        movement = self.drain(1, run_id).json()
        response = self.post(f"/api/processing/movements/{movement['id']}/compensate/", {'reason': 'Неверный бак'})
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(self.state()['receivers'][0]['run']['status'], 'waiting')
        self.assertEqual(self.drain(1, run_id).status_code, 201)
        reloaded = self.load()
        self.assertEqual(self.receiver(1, reloaded).status_code, 201)
        current = MaterialMovement.objects.get(receiver_run_id=run_id, is_compensated=False)
        response = self.post(f'/api/processing/movements/{current.pk}/compensate/', {'reason': 'Поздняя отмена'})
        self.assertEqual(response.status_code, 400)


class ConcurrentReceiverTests(ReactorFixture, TransactionTestCase):
    def test_repeat_open_requests_produce_one_timed_record(self):
        loading = self.load()
        payload = {'reactor_id': self.reactor.pk, 'number': 1, 'loading_id': loading,
                   'action': 'open', 'idempotency_key': str(uuid4())}
        barrier = Barrier(2)

        def send():
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                return self.post(RECEIVERS, payload, client=Client()).status_code
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = [executor.submit(send), executor.submit(send)]
            self.assertEqual(sorted(result.result() for result in outcomes), [200, 201])
        self.assertEqual(ReceiverRun.objects.count(), 1)
