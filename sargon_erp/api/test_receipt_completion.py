import json
import threading
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from unittest.mock import AsyncMock, patch

from django.contrib.auth import get_user_model
from django.db import close_old_connections
from django.test import Client, TestCase, TransactionTestCase

from .auth import create_access_token
from .models import (
    AccessGroup, City, GroupModuleAccess, LaboratoryAnalysis, MaterialMovement,
    Module, OperationAuditLog, Permission, ProductionContainer, RawMaterialReceipt,
    ReceiptBatch, Supplier, UserProfile,
)


class ReceiptCompletionFixture:
    def setUp(self):
        self.admin = get_user_model().objects.create_superuser('receipt-admin')
        self.manager = get_user_model().objects.create_user('receipt-manager')
        self.reader = get_user_model().objects.create_user('receipt-reader')
        module, _ = Module.objects.get_or_create(code='raw-material-receiving', defaults={'name': 'Прием сырья'})
        for code in ('view', 'update'):
            Permission.objects.get_or_create(code=code, defaults={'name': code})
        for user, codes in ((self.manager, ('view', 'update')), (self.reader, ('view',))):
            group = AccessGroup.objects.create(name=user.username)
            access = GroupModuleAccess.objects.create(group=group, module=module)
            access.permissions.set(Permission.objects.filter(code__in=codes))
            UserProfile.objects.update_or_create(user=user, defaults={'group': group})
        self.supplier = Supplier.objects.create(
            company_name='Поставщик приёма', city=City.objects.create(name='Город приёма'),
            address='Адрес', phone='',
        )
        self.receipt = RawMaterialReceipt.objects.create(supplier=self.supplier)
        self.batch = ReceiptBatch.objects.create(receipt=self.receipt, sequence_number=1)
        self.analysis = LaboratoryAnalysis.objects.create(
            batch=self.batch, density=Decimal('0.8800'), current_temperature=Decimal('20'), is_approved=True,
        )
        self.tank = ProductionContainer.objects.create(
            kind=ProductionContainer.KIND_RECEIVING_TANK, number=901,
            system_code='receipt-test-901', capacity_liters=Decimal('1000'),
        )
        self.other_tank = ProductionContainer.objects.create(
            kind=ProductionContainer.KIND_RECEIVING_TANK, number=902,
            system_code='receipt-test-902', capacity_liters=Decimal('1000'),
        )

    def payload(self, quantity='100', unit='liters', volumes=('100',)):
        return {
            'is_completed': True,
            'batches': [{'id': self.batch.pk, 'input_quantity': quantity, 'input_unit': unit}],
            'distributions': [
                {'batch_id': self.batch.pk, 'tank_id': tank.pk, 'volume_liters': volume}
                for tank, volume in zip((self.tank, self.other_tank), volumes)
            ],
        }

    def complete(self, payload=None, user=None):
        return self.client.patch(
            f'/api/raw-material/receipts/{self.receipt.pk}/',
            data=json.dumps(payload if payload is not None else self.payload()), content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {create_access_token(user or self.manager)}',
        )


class ReceiptCompletionTests(ReceiptCompletionFixture, TestCase):
    def assert_not_posted(self):
        self.receipt.refresh_from_db()
        self.batch.refresh_from_db()
        self.tank.refresh_from_db()
        self.other_tank.refresh_from_db()
        self.assertFalse(self.receipt.is_completed)
        self.assertIsNone(self.receipt.completed_at)
        self.assertIsNone(self.receipt.quantity_liters)
        self.assertIsNone(self.batch.input_quantity)
        self.assertIsNone(self.batch.quantity_liters)
        self.assertEqual(self.tank.current_volume_liters, 0)
        self.assertEqual(self.other_tank.current_volume_liters, 0)
        self.assertFalse(MaterialMovement.objects.filter(receipt=self.receipt).exists())
        self.assertFalse(OperationAuditLog.objects.filter(action__in=('receipt_batch_updated', 'receipt_completed')).exists())

    def test_single_request_saves_quantity_distributions_and_completion(self):
        response = self.complete(self.payload('100.125', volumes=('40.100', '60.025')))
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(response.json()['is_completed'])
        self.assertEqual(response.json()['quantity_liters'], '100.125')
        self.assertEqual(response.json()['batches'][0]['analysis_density'], '0.8800')
        self.batch.refresh_from_db()
        self.assertEqual(self.batch.input_quantity, Decimal('100.125'))
        self.assertEqual(self.batch.quantity_liters, Decimal('100.125'))
        self.tank.refresh_from_db()
        self.other_tank.refresh_from_db()
        self.assertEqual(self.tank.current_volume_liters, Decimal('40.100'))
        self.assertEqual(self.other_tank.current_volume_liters, Decimal('60.025'))
        self.assertEqual(MaterialMovement.objects.filter(receipt=self.receipt).count(), 2)

    def test_kilograms_are_converted_and_rounded_on_the_server(self):
        response = self.complete(self.payload('1', 'kilograms', ('1.136',)))
        self.assertEqual(response.status_code, 200, response.content)
        self.batch.refresh_from_db()
        self.assertEqual(self.batch.input_quantity, Decimal('1'))
        self.assertEqual(self.batch.input_unit, 'kilograms')
        self.assertEqual(self.batch.quantity_liters, Decimal('1.136'))

    def test_invalid_distributions_are_atomic(self):
        invalid_rows = [[], None, {}, [None]]
        for amount in ('99.999', '100.001', '0', '-1', 'NaN', 'Infinity', '100.0001'):
            invalid_rows.append([{'batch_id': self.batch.pk, 'tank_id': self.tank.pk, 'volume_liters': amount}])
        invalid_rows.extend((
            [{'batch_id': self.batch.pk, 'tank_id': self.tank.pk, 'volume_liters': '50'}] * 2,
            [{'batch_id': self.batch.pk, 'tank_id': 999999, 'volume_liters': '100'}],
        ))
        for rows in invalid_rows:
            with self.subTest(rows=rows):
                response = self.complete({**self.payload(), 'distributions': rows})
                self.assertEqual(response.status_code, 400, response.content)
                self.assert_not_posted()

    def test_invalid_quantities_and_units_save_nothing(self):
        for quantity in (None, '', '0', '-1', 'NaN', 'Infinity', 'bad', '0.0001', '100000000000'):
            with self.subTest(quantity=quantity):
                self.assertEqual(self.complete(self.payload(quantity)).status_code, 400)
                self.assert_not_posted()
        for unit in ('invalid', None, [], {}):
            with self.subTest(unit=unit):
                self.assertEqual(self.complete(self.payload(unit=unit)).status_code, 400)
                self.assert_not_posted()

    def test_invalid_batch_payloads_are_rejected(self):
        foreign_receipt = RawMaterialReceipt.objects.create(supplier=self.supplier)
        foreign_batch = ReceiptBatch.objects.create(receipt=foreign_receipt, sequence_number=1)
        row = self.payload()['batches'][0]
        for rows in (None, {}, [], [None], [row, row], [{**row, 'id': foreign_batch.pk}], [{**row, 'id': True}]):
            with self.subTest(rows=rows):
                self.assertEqual(self.complete({**self.payload(), 'batches': rows}).status_code, 400)
                self.assert_not_posted()

    def test_overflow_validates_all_batches_for_the_same_tank(self):
        other = ReceiptBatch.objects.create(receipt=self.receipt, sequence_number=2)
        LaboratoryAnalysis.objects.create(batch=other, density=Decimal('0.88'), current_temperature=20, is_approved=True)
        payload = self.payload('600', volumes=('600',))
        payload['batches'].append({'id': other.pk, 'input_quantity': '600', 'input_unit': 'liters'})
        payload['distributions'].append({'batch_id': other.pk, 'tank_id': self.tank.pk, 'volume_liters': '600'})
        self.assertEqual(self.complete(payload).status_code, 400)
        self.assert_not_posted()
        other.refresh_from_db()
        self.assertIsNone(other.input_quantity)

    def test_pending_or_rejected_analysis_cannot_receive_quantity(self):
        for rejected in (False, True):
            self.analysis.is_approved = False
            self.analysis.is_rejected = rejected
            self.analysis.save()
            self.assertEqual(self.complete().status_code, 400)
            self.assert_not_posted()

    def test_pending_other_batch_blocks_completion_without_partial_save(self):
        other = ReceiptBatch.objects.create(receipt=self.receipt, sequence_number=2)
        LaboratoryAnalysis.objects.create(batch=other)
        self.assertEqual(self.complete().status_code, 400)
        self.assert_not_posted()

    def test_inactive_or_wrong_kind_tank_is_rejected(self):
        for kind, active in ((ProductionContainer.KIND_RECEIVING_TANK, False), (ProductionContainer.KIND_SEPARATOR, True)):
            with self.subTest(kind=kind, active=active):
                self.tank.kind = kind
                self.tank.is_active = active
                self.tank.save()
                self.assertEqual(self.complete().status_code, 400)
                self.assert_not_posted()

    def test_fully_rejected_receipt_closes_with_empty_batch_quantities(self):
        self.analysis.is_approved = False
        self.analysis.is_rejected = True
        self.analysis.save()
        response = self.complete({'is_completed': True, 'batches': [], 'distributions': []})
        self.assertEqual(response.status_code, 200, response.content)
        self.receipt.refresh_from_db()
        self.assertTrue(self.receipt.is_completed)
        self.assertIsNotNone(self.receipt.completed_at)
        self.assertFalse(MaterialMovement.objects.filter(receipt=self.receipt).exists())

    def test_mixed_receipt_accepts_only_approved_batches(self):
        other = ReceiptBatch.objects.create(receipt=self.receipt, sequence_number=2)
        LaboratoryAnalysis.objects.create(batch=other, is_rejected=True)
        response = self.complete()
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(response.json()['is_completed'])
        self.assertEqual(MaterialMovement.objects.filter(receipt=self.receipt).count(), 1)
        other.refresh_from_db()
        self.assertIsNone(other.input_quantity)

    def test_read_only_user_cannot_complete(self):
        self.assertEqual(self.complete(user=self.reader).status_code, 403)
        self.assert_not_posted()

    def test_completed_receipt_cannot_be_posted_twice(self):
        self.assertEqual(self.complete().status_code, 200)
        self.assertEqual(self.complete().status_code, 423)
        self.assertEqual(self.complete(user=self.admin).status_code, 200)
        self.tank.refresh_from_db()
        self.assertEqual(self.tank.current_volume_liters, 100)
        self.assertEqual(MaterialMovement.objects.filter(receipt=self.receipt).count(), 1)

    def test_websocket_completion_is_sent_after_commit_only(self):
        with patch('api.views.get_channel_layer') as get_layer:
            get_layer.return_value.group_send = AsyncMock()
            with self.captureOnCommitCallbacks(execute=True):
                self.assertEqual(self.complete().status_code, 200)
                get_layer.return_value.group_send.assert_not_called()
            get_layer.return_value.group_send.assert_awaited_once()
            event = get_layer.return_value.group_send.call_args.args[1]['payload']
            self.assertEqual(event['event'], 'receipt_completed')
            self.assertEqual(event['receipt_id'], self.receipt.pk)


class ConcurrentReceiptCompletionTests(ReceiptCompletionFixture, TransactionTestCase):
    def test_simultaneous_completion_posts_only_once(self):
        barrier = threading.Barrier(2)
        token = create_access_token(self.admin)
        payload = self.payload()

        def complete_once(number):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                return Client().patch(
                    f'/api/raw-material/receipts/{self.receipt.pk}/', data=json.dumps(payload),
                    content_type='application/json', HTTP_AUTHORIZATION=f'Bearer {token}',
                ).status_code
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            self.assertEqual(sorted(executor.map(complete_once, (1, 2))), [200, 200])
        self.tank.refresh_from_db()
        self.assertEqual(self.tank.current_volume_liters, 100)
        self.assertEqual(MaterialMovement.objects.filter(receipt=self.receipt).count(), 1)

    def test_concurrent_laboratory_rejection_cannot_change_distributed_analysis(self):
        barrier = threading.Barrier(2)
        token = create_access_token(self.admin)
        requests = (
            (f'/api/raw-material/receipts/{self.receipt.pk}/', self.payload()),
            (f'/api/laboratory/analyses/{self.analysis.pk}/', {'is_rejected': True}),
        )

        def send_request(request):
            close_old_connections()
            try:
                path, payload = request
                barrier.wait(timeout=10)
                return Client().patch(
                    path, data=json.dumps(payload), content_type='application/json',
                    HTTP_AUTHORIZATION=f'Bearer {token}',
                ).status_code
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            completion_status, analysis_status = executor.map(send_request, requests)
        self.receipt.refresh_from_db()
        self.analysis.refresh_from_db()
        self.tank.refresh_from_db()
        if completion_status == 200:
            self.assertEqual(analysis_status, 423)
            self.assertTrue(self.receipt.is_completed)
            self.assertTrue(self.analysis.is_approved)
            self.assertFalse(self.analysis.is_rejected)
            self.assertEqual(self.tank.current_volume_liters, 100)
            self.assertEqual(MaterialMovement.objects.filter(receipt=self.receipt).count(), 1)
        else:
            self.assertEqual((completion_status, analysis_status), (400, 200))
            self.assertFalse(self.receipt.is_completed)
            self.assertTrue(self.analysis.is_rejected)
            self.assertEqual(self.tank.current_volume_liters, 0)
            self.assertFalse(MaterialMovement.objects.filter(receipt=self.receipt).exists())
