import json
import threading
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import close_old_connections
from django.test import Client, TestCase, TransactionTestCase
from django.utils import timezone

from .auth import create_access_token
from .models import (
    AccessGroup,
    City,
    GroupModuleAccess,
    InventoryCategory,
    InventoryItem,
    KnowledgeArticle,
    KnowledgeCategory,
    LaboratoryAnalysis,
    MaterialMovement,
    Module,
    Permission,
    ProductionContainer,
    RawMaterialReceipt,
    ReceiptBatch,
    Supplier,
    UserProfile,
    UnitOfMeasure,
    Warehouse,
    WarehouseBalance,
    WarehouseDocument,
    WarehouseMovement,
    ProductionOutput,
    ProductionOutputLine,
    ProductionMaterialUsage,
)


class LoginOptionsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        user_model = get_user_model()
        cls.active_user = user_model.objects.create_user('login-alpha', email='private@example.invalid', first_name='Private')
        user_model.objects.create_user('login-zeta', is_staff=True, is_superuser=True)
        user_model.objects.create_user('login-disabled', is_active=False)

    def test_anonymous_request_returns_only_sorted_active_usernames(self):
        response = self.client.get('/api/auth/login-options/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'items': ['login-alpha', 'login-zeta']})
        self.assertIn('no-store', response.headers['Cache-Control'])

    def test_returns_all_active_usernames_without_history_limit(self):
        user_model = get_user_model()
        user_model.objects.bulk_create([user_model(username=f'login-{index:02d}') for index in range(12)])

        response = self.client.get('/api/auth/login-options/')

        self.assertEqual(len(response.json()['items']), 14)
        self.assertEqual(response.json()['items'], sorted(response.json()['items']))

    def test_options_reflect_current_user_data(self):
        self.client.get('/api/auth/login-options/')
        self.active_user.is_active = False
        self.active_user.save(update_fields=['is_active'])
        get_user_model().objects.create_user('login-new')

        response = self.client.get('/api/auth/login-options/')

        self.assertEqual(response.json(), {'items': ['login-new', 'login-zeta']})

    def test_options_do_not_grant_access_to_user_management(self):
        self.assertEqual(self.client.get('/api/access/users/').status_code, 401)
        self.client.get('/api/auth/login-options/')
        self.assertEqual(self.client.get('/api/access/users/').status_code, 401)

    def test_unsupported_methods_are_rejected(self):
        for method in ('post', 'put', 'patch', 'delete'):
            with self.subTest(method=method):
                response = getattr(self.client, method)('/api/auth/login-options/')
                self.assertEqual(response.status_code, 405)
                self.assertEqual(response.headers['Allow'], 'GET')


class ProductionAccountingTests(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_superuser('admin', password='password')
        self.city = City.objects.create(name='Тестовый город')
        self.supplier = Supplier.objects.create(
            company_name='Тестовый поставщик',
            city=self.city,
            address='Тестовый адрес',
            phone='+000000000',
        )
        self.tank = ProductionContainer.objects.create(
            kind=ProductionContainer.KIND_RECEIVING_TANK,
            number=10,
            system_code='receiving-tank-10',
            capacity_liters=Decimal('1000.000'),
        )
        self.boiler = ProductionContainer.objects.create(
            kind=ProductionContainer.KIND_PREHEATING_BOILER,
            number=10,
            system_code='preheating-boiler-10',
            capacity_liters=Decimal('500.000'),
        )
        self.separator = ProductionContainer.objects.create(
            kind=ProductionContainer.KIND_SEPARATOR,
            number=10,
            system_code='separator-10',
            capacity_liters=Decimal('500.000'),
        )
        self.chemical_mixer = ProductionContainer.objects.create(
            kind=ProductionContainer.KIND_CHEMICAL_MIXER,
            number=10,
            system_code='chemical-mixer-10',
            capacity_liters=Decimal('500.000'),
        )
        self.processing_workshop = ProductionContainer.objects.create(
            kind=ProductionContainer.KIND_PROCESSING_WORKSHOP,
            number=10,
            system_code='processing-workshop-10',
            capacity_liters=Decimal('500.000'),
        )
        self.raw_diesel_tank = ProductionContainer.objects.create(
            kind=ProductionContainer.KIND_RAW_DIESEL_TANK,
            number=10,
            system_code='raw-diesel-tank-10',
            capacity_liters=Decimal('500.000'),
        )
        self.raw_spindle_tank = ProductionContainer.objects.create(
            kind=ProductionContainer.KIND_RAW_SPINDLE_TANK,
            number=10,
            system_code='raw-spindle-tank-10',
            capacity_liters=Decimal('500.000'),
        )

    def auth_headers(self, user=None):
        token = create_access_token(user or self.admin)
        return {'HTTP_AUTHORIZATION': f'Bearer {token}'}

    def create_receipt(self, quantities, rejected=()):
        receipt = RawMaterialReceipt.objects.create(supplier=self.supplier)
        batches = []
        for index, quantity in enumerate(quantities, start=1):
            batch = ReceiptBatch.objects.create(
                receipt=receipt,
                sequence_number=index,
                input_quantity=Decimal(quantity) if quantity is not None else None,
                input_unit=RawMaterialReceipt.UNIT_LITERS,
                quantity_liters=Decimal(quantity) if quantity is not None else None,
            )
            LaboratoryAnalysis.objects.create(
                batch=batch,
                density=Decimal('0.8800'),
                flash_point_temperature=Decimal('150.00'),
                current_temperature=Decimal('20.00'),
                water_percentage=Decimal('1.000'),
                is_approved=index not in rejected,
                is_rejected=index in rejected,
            )
            batches.append(batch)
        return receipt, batches

    def patch_json(self, path, payload, user=None):
        return self.client.patch(
            path,
            data=json.dumps(payload),
            content_type='application/json',
            **self.auth_headers(user),
        )

    def post_json(self, path, payload, user=None):
        return self.client.post(
            path,
            data=json.dumps(payload),
            content_type='application/json',
            **self.auth_headers(user),
        )

    def test_completion_distributes_one_batch_between_tanks(self):
        second_tank = ProductionContainer.objects.create(
            kind=ProductionContainer.KIND_RECEIVING_TANK,
            number=11,
            system_code='receiving-tank-11',
            capacity_liters=Decimal('1000.000'),
        )
        receipt, batches = self.create_receipt(['100.125'])

        response = self.patch_json(f'/api/raw-material/receipts/{receipt.pk}/', {
            'is_completed': True,
            'distributions': [
                {'batch_id': batches[0].pk, 'tank_id': self.tank.pk, 'volume_liters': '40.100'},
                {'batch_id': batches[0].pk, 'tank_id': second_tank.pk, 'volume_liters': '60.025'},
            ],
        })

        self.assertEqual(response.status_code, 200)
        self.tank.refresh_from_db()
        second_tank.refresh_from_db()
        self.assertEqual(self.tank.current_volume_liters, Decimal('40.100'))
        self.assertEqual(second_tank.current_volume_liters, Decimal('60.025'))
        self.assertEqual(MaterialMovement.objects.filter(receipt=receipt).count(), 2)

    def test_fully_rejected_receipt_completes_without_movements(self):
        receipt, _ = self.create_receipt([None], rejected={1})

        response = self.patch_json(f'/api/raw-material/receipts/{receipt.pk}/', {
            'is_completed': True,
            'distributions': [],
        })

        self.assertEqual(response.status_code, 200)
        receipt.refresh_from_db()
        self.assertTrue(receipt.is_completed)
        self.assertFalse(MaterialMovement.objects.filter(receipt=receipt).exists())

    def test_overflow_rolls_back_entire_completion(self):
        self.tank.capacity_liters = Decimal('50.000')
        self.tank.save(update_fields=['capacity_liters'])
        receipt, batches = self.create_receipt(['60.000'])

        response = self.patch_json(f'/api/raw-material/receipts/{receipt.pk}/', {
            'is_completed': True,
            'distributions': [
                {'batch_id': batches[0].pk, 'tank_id': self.tank.pk, 'volume_liters': '60.000'},
            ],
        })

        self.assertEqual(response.status_code, 400)
        self.tank.refresh_from_db()
        receipt.refresh_from_db()
        self.assertEqual(self.tank.current_volume_liters, Decimal('0.000'))
        self.assertFalse(receipt.is_completed)
        self.assertFalse(MaterialMovement.objects.filter(receipt=receipt).exists())

    def test_distributed_batch_is_immutable_even_for_admin(self):
        receipt, batches = self.create_receipt(['25.000'])
        self.patch_json(f'/api/raw-material/receipts/{receipt.pk}/', {
            'is_completed': True,
            'distributions': [
                {'batch_id': batches[0].pk, 'tank_id': self.tank.pk, 'volume_liters': '25.000'},
            ],
        })

        response = self.patch_json(f'/api/raw-material/batches/{batches[0].pk}/', {
            'input_quantity': '30.000',
            'input_unit': 'liters',
        })

        self.assertEqual(response.status_code, 423)
        batches[0].refresh_from_db()
        self.assertEqual(batches[0].quantity_liters, Decimal('25.000'))

    def test_tank_to_boiler_movement_is_atomic_and_idempotent(self):
        self.tank.current_volume_liters = Decimal('200.000')
        self.tank.save(update_fields=['current_volume_liters'])
        payload = {
            'source_tank_id': self.tank.pk,
            'destination_boiler_id': self.boiler.pk,
            'volume_liters': '75.125',
            'idempotency_key': 'test-operation-key',
        }

        first_response = self.post_json('/api/processing/movements/tank-to-boiler/', payload)
        second_response = self.post_json('/api/processing/movements/tank-to-boiler/', payload)

        self.assertEqual(first_response.status_code, 201)
        self.assertEqual(second_response.status_code, 200)
        self.tank.refresh_from_db()
        self.boiler.refresh_from_db()
        self.assertEqual(self.tank.current_volume_liters, Decimal('124.875'))
        self.assertEqual(self.boiler.current_volume_liters, Decimal('75.125'))
        self.assertEqual(MaterialMovement.objects.filter(idempotency_key='test-operation-key').count(), 1)

    def test_admin_compensation_reverses_movement_once(self):
        self.tank.current_volume_liters = Decimal('100.000')
        self.tank.save(update_fields=['current_volume_liters'])
        movement_response = self.post_json('/api/processing/movements/tank-to-boiler/', {
            'source_tank_id': self.tank.pk,
            'destination_boiler_id': self.boiler.pk,
            'volume_liters': '10.000',
            'idempotency_key': 'movement-to-compensate',
        })
        movement_id = movement_response.json()['id']

        first_response = self.post_json(
            f'/api/processing/movements/{movement_id}/compensate/',
            {'reason': 'Исправление ошибки оператора'},
        )
        second_response = self.post_json(
            f'/api/processing/movements/{movement_id}/compensate/',
            {'reason': 'Повтор'},
        )

        self.assertEqual(first_response.status_code, 201)
        self.assertEqual(second_response.status_code, 400)
        self.tank.refresh_from_db()
        self.boiler.refresh_from_db()
        self.assertEqual(self.tank.current_volume_liters, Decimal('100.000'))
        self.assertEqual(self.boiler.current_volume_liters, Decimal('0.000'))

    def test_boiler_to_separator_movement_updates_both_balances(self):
        self.boiler.current_volume_liters = Decimal('200.000')
        self.boiler.save(update_fields=['current_volume_liters'])
        payload = {
            'source_boiler_id': self.boiler.pk,
            'destination_separator_id': self.separator.pk,
            'volume_liters': '75.125',
            'idempotency_key': 'separator-loading-key',
        }

        first_response = self.post_json('/api/processing/movements/boiler-to-separator/', payload)
        second_response = self.post_json('/api/processing/movements/boiler-to-separator/', payload)

        self.assertEqual(first_response.status_code, 201)
        self.assertEqual(second_response.status_code, 200)
        self.boiler.refresh_from_db()
        self.separator.refresh_from_db()
        self.assertEqual(self.boiler.current_volume_liters, Decimal('124.875'))
        self.assertEqual(self.separator.current_volume_liters, Decimal('75.125'))
        self.assertEqual(MaterialMovement.objects.filter(idempotency_key='separator-loading-key').count(), 1)

    def test_separator_output_reduces_balance_and_can_be_compensated(self):
        self.separator.current_volume_liters = Decimal('120.000')
        self.separator.save(update_fields=['current_volume_liters'])

        movement_response = self.post_json('/api/processing/movements/separator-output/', {
            'source_separator_id': self.separator.pk,
            'output_type': 'water',
            'volume_liters': '20.125',
            'idempotency_key': 'separator-output-key',
        })

        self.assertEqual(movement_response.status_code, 201)
        self.assertEqual(movement_response.json()['product_name'], MaterialMovement.PRODUCT_TECHNICAL_WATER)
        self.separator.refresh_from_db()
        self.assertEqual(self.separator.current_volume_liters, Decimal('99.875'))

        compensation_response = self.post_json(
            f"/api/processing/movements/{movement_response.json()['id']}/compensate/",
            {'reason': 'Исправление ошибочной отгрузки'},
        )

        self.assertEqual(compensation_response.status_code, 201)
        self.separator.refresh_from_db()
        self.assertEqual(self.separator.current_volume_liters, Decimal('120.000'))

    def test_separator_output_rejects_fuel(self):
        self.separator.current_volume_liters = Decimal('120.000')
        self.separator.save(update_fields=['current_volume_liters'])

        response = self.post_json('/api/processing/movements/separator-output/', {
            'source_separator_id': self.separator.pk,
            'output_type': 'fuel',
            'volume_liters': '20.000',
            'idempotency_key': 'separator-fuel-output-key',
        })

        self.assertEqual(response.status_code, 400)
        self.separator.refresh_from_db()
        self.assertEqual(self.separator.current_volume_liters, Decimal('120.000'))

    def test_separator_to_chemical_mixer_updates_both_balances(self):
        self.separator.current_volume_liters = Decimal('200.000')
        self.separator.save(update_fields=['current_volume_liters'])
        payload = {
            'source_separator_id': self.separator.pk,
            'destination_mixer_id': self.chemical_mixer.pk,
            'volume_liters': '75.125',
            'idempotency_key': 'chemical-mixer-loading-key',
        }

        first_response = self.post_json('/api/processing/movements/separator-to-chemical-mixer/', payload)
        second_response = self.post_json('/api/processing/movements/separator-to-chemical-mixer/', payload)

        self.assertEqual(first_response.status_code, 201)
        self.assertEqual(second_response.status_code, 200)
        self.separator.refresh_from_db()
        self.chemical_mixer.refresh_from_db()
        self.assertEqual(self.separator.current_volume_liters, Decimal('124.875'))
        self.assertEqual(self.chemical_mixer.current_volume_liters, Decimal('75.125'))
        self.assertEqual(MaterialMovement.objects.filter(idempotency_key='chemical-mixer-loading-key').count(), 1)

        compensation_response = self.post_json(
            f"/api/processing/movements/{first_response.json()['id']}/compensate/",
            {'reason': 'Исправление загрузки миксера'},
        )

        self.assertEqual(compensation_response.status_code, 201)
        self.separator.refresh_from_db()
        self.chemical_mixer.refresh_from_db()
        self.assertEqual(self.separator.current_volume_liters, Decimal('200.000'))
        self.assertEqual(self.chemical_mixer.current_volume_liters, Decimal('0.000'))

    def test_admin_can_create_and_delete_empty_chemical_mixer(self):
        create_response = self.post_json('/api/processing/chemical-mixers/', {
            'number': 11,
            'capacity_liters': '1000',
            'is_active': True,
        })

        self.assertEqual(create_response.status_code, 201)
        mixer_id = create_response.json()['id']
        self.assertEqual(create_response.json()['system_code'], 'chemical-mixer-11')

        delete_response = self.client.delete(
            f'/api/processing/containers/{mixer_id}/',
            **self.auth_headers(),
        )

        self.assertEqual(delete_response.status_code, 200)
        self.assertFalse(ProductionContainer.objects.filter(pk=mixer_id).exists())

    def test_chemical_mixer_to_workshop_updates_both_balances_and_compensates(self):
        self.chemical_mixer.current_volume_liters = Decimal('200.000')
        self.chemical_mixer.save(update_fields=['current_volume_liters'])
        payload = {
            'source_mixer_id': self.chemical_mixer.pk,
            'destination_workshop_id': self.processing_workshop.pk,
            'volume_liters': '75.125',
            'idempotency_key': 'processing-workshop-loading-key',
        }

        first_response = self.post_json('/api/processing/movements/chemical-mixer-to-workshop/', payload)
        second_response = self.post_json('/api/processing/movements/chemical-mixer-to-workshop/', payload)

        self.assertEqual(first_response.status_code, 201)
        self.assertEqual(second_response.status_code, 200)
        self.chemical_mixer.refresh_from_db()
        self.processing_workshop.refresh_from_db()
        self.assertEqual(self.chemical_mixer.current_volume_liters, Decimal('124.875'))
        self.assertEqual(self.processing_workshop.current_volume_liters, Decimal('75.125'))

        compensation_response = self.post_json(
            f"/api/processing/movements/{first_response.json()['id']}/compensate/",
            {'reason': 'Исправление загрузки цеха'},
        )

        self.assertEqual(compensation_response.status_code, 201)
        self.chemical_mixer.refresh_from_db()
        self.processing_workshop.refresh_from_db()
        self.assertEqual(self.chemical_mixer.current_volume_liters, Decimal('200.000'))
        self.assertEqual(self.processing_workshop.current_volume_liters, Decimal('0.000'))

    def test_admin_can_create_and_delete_empty_processing_workshop(self):
        create_response = self.post_json('/api/processing/workshops/', {
            'number': 11,
            'capacity_liters': '1000',
            'is_active': True,
        })

        self.assertEqual(create_response.status_code, 201)
        workshop_id = create_response.json()['id']
        self.assertEqual(create_response.json()['system_code'], 'processing-workshop-11')

        delete_response = self.client.delete(
            f'/api/processing/containers/{workshop_id}/',
            **self.auth_headers(),
        )

        self.assertEqual(delete_response.status_code, 200)
        self.assertFalse(ProductionContainer.objects.filter(pk=workshop_id).exists())

    def test_workshop_loads_raw_diesel_and_spindle_tanks_independently(self):
        self.processing_workshop.current_volume_liters = Decimal('200.000')
        self.processing_workshop.save(update_fields=['current_volume_liters'])

        diesel_response = self.post_json('/api/processing/movements/workshop-to-raw-diesel-tank/', {
            'source_workshop_id': self.processing_workshop.pk,
            'destination_tank_id': self.raw_diesel_tank.pk,
            'volume_liters': '60.125',
            'idempotency_key': 'raw-diesel-loading-key',
        })
        spindle_response = self.post_json('/api/processing/movements/workshop-to-raw-spindle-tank/', {
            'source_workshop_id': self.processing_workshop.pk,
            'destination_tank_id': self.raw_spindle_tank.pk,
            'volume_liters': '40.000',
            'idempotency_key': 'raw-spindle-loading-key',
        })

        self.assertEqual(diesel_response.status_code, 201)
        self.assertEqual(spindle_response.status_code, 201)
        self.assertEqual(diesel_response.json()['product_name'], 'Сырая солярка')
        self.assertEqual(spindle_response.json()['product_name'], 'Сырая веретенка')
        self.processing_workshop.refresh_from_db()
        self.raw_diesel_tank.refresh_from_db()
        self.raw_spindle_tank.refresh_from_db()
        self.assertEqual(self.processing_workshop.current_volume_liters, Decimal('99.875'))
        self.assertEqual(self.raw_diesel_tank.current_volume_liters, Decimal('60.125'))
        self.assertEqual(self.raw_spindle_tank.current_volume_liters, Decimal('40.000'))

        compensation_response = self.post_json(
            f"/api/processing/movements/{diesel_response.json()['id']}/compensate/",
            {'reason': 'Исправление загрузки бака солярки'},
        )

        self.assertEqual(compensation_response.status_code, 201)
        self.processing_workshop.refresh_from_db()
        self.raw_diesel_tank.refresh_from_db()
        self.assertEqual(self.processing_workshop.current_volume_liters, Decimal('160.000'))
        self.assertEqual(self.raw_diesel_tank.current_volume_liters, Decimal('0.000'))

    def test_admin_can_create_separate_raw_product_tanks(self):
        diesel_response = self.post_json('/api/processing/raw-diesel-tanks/', {
            'number': 11,
            'capacity_liters': '1000',
            'is_active': True,
        })
        spindle_response = self.post_json('/api/processing/raw-spindle-tanks/', {
            'number': 11,
            'capacity_liters': '1000',
            'is_active': True,
        })

        self.assertEqual(diesel_response.status_code, 201)
        self.assertEqual(spindle_response.status_code, 201)
        self.assertEqual(diesel_response.json()['system_code'], 'raw-diesel-tank-11')
        self.assertEqual(spindle_response.json()['system_code'], 'raw-spindle-tank-11')

    def test_processing_manager_cannot_manage_containers_or_view_journal(self):
        manager = get_user_model().objects.create_user('processing-manager', password='password')
        module, _ = Module.objects.update_or_create(
            code='used-oil-processing',
            defaults={
                'name': 'Переработка отработанного масла',
                'default_path': '/processing/receiving-tanks',
            },
        )
        view_permission, _ = Permission.objects.get_or_create(code='view', defaults={'name': 'Просмотр'})
        create_permission, _ = Permission.objects.get_or_create(code='create', defaults={'name': 'Создание'})
        group = AccessGroup.objects.create(name='Менеджер переработки', start_module=module)
        access = GroupModuleAccess.objects.create(group=group, module=module)
        access.permissions.set([view_permission, create_permission])
        UserProfile.objects.filter(user=manager).update(group=group)

        list_response = self.client.get('/api/processing/receiving-tanks/', **self.auth_headers(manager))
        create_response = self.post_json('/api/processing/receiving-tanks/', {
            'number': 20,
            'capacity_liters': 1000,
        }, manager)
        journal_response = self.client.get('/api/processing/journal/', **self.auth_headers(manager))

        self.assertEqual(list_response.status_code, 200)
        self.assertNotIn('capacity_liters', list_response.json()['items'][0])
        self.assertEqual(create_response.status_code, 403)
        self.assertEqual(journal_response.status_code, 403)

    def test_processing_form_module_grants_only_its_operation(self):
        operator = get_user_model().objects.create_user('boiler-operator', password='password')
        module = Module.objects.get(code='boiler-loading')
        group_response = self.post_json('/api/access/groups/', {
            'name': 'Операторы загрузки котла',
            'description': 'Доступ только к форме загрузки котла.',
            'module_ids': [module.pk],
            'start_module_id': module.pk,
        })
        self.assertEqual(group_response.status_code, 201)
        group = AccessGroup.objects.get(pk=group_response.json()['id'])
        access = GroupModuleAccess.objects.get(group=group, module=module)
        self.assertEqual(set(access.permissions.values_list('code', flat=True)), {'view', 'create'})
        UserProfile.objects.filter(user=operator).update(group=group)
        self.tank.current_volume_liters = Decimal('100.000')
        self.tank.save(update_fields=['current_volume_liters'])

        tank_response = self.client.get('/api/processing/receiving-tanks/', **self.auth_headers(operator))
        boiler_response = self.client.get('/api/processing/preheating-boilers/', **self.auth_headers(operator))
        separator_response = self.client.get('/api/processing/separators/', **self.auth_headers(operator))
        movement_response = self.post_json('/api/processing/movements/tank-to-boiler/', {
            'source_tank_id': self.tank.pk,
            'destination_boiler_id': self.boiler.pk,
            'volume_liters': '25.000',
            'idempotency_key': 'boiler-operator-movement',
        }, operator)
        forbidden_response = self.post_json('/api/processing/movements/boiler-to-separator/', {
            'source_boiler_id': self.boiler.pk,
            'destination_separator_id': self.separator.pk,
            'volume_liters': '10.000',
            'idempotency_key': 'boiler-operator-forbidden-movement',
        }, operator)

        self.assertEqual(tank_response.status_code, 200)
        self.assertEqual(boiler_response.status_code, 200)
        self.assertEqual(separator_response.status_code, 403)
        self.assertEqual(movement_response.status_code, 201)
        self.assertEqual(forbidden_response.status_code, 403)

    def test_overview_returns_real_receipt_and_container_totals(self):
        receipt = RawMaterialReceipt.objects.create(
            supplier=self.supplier,
            quantity_liters=Decimal('125.500'),
            is_completed=True,
            completed_at=timezone.now(),
        )
        ReceiptBatch.objects.create(receipt=receipt, sequence_number=1)
        self.tank.current_volume_liters = Decimal('300.250')
        self.tank.save(update_fields=['current_volume_liters'])
        self.boiler.current_volume_liters = Decimal('75.125')
        self.boiler.save(update_fields=['current_volume_liters'])
        self.separator.current_volume_liters = Decimal('25.500')
        self.separator.save(update_fields=['current_volume_liters'])
        self.chemical_mixer.current_volume_liters = Decimal('50.250')
        self.chemical_mixer.save(update_fields=['current_volume_liters'])
        self.processing_workshop.current_volume_liters = Decimal('40.125')
        self.processing_workshop.save(update_fields=['current_volume_liters'])
        self.raw_diesel_tank.current_volume_liters = Decimal('30.500')
        self.raw_diesel_tank.save(update_fields=['current_volume_liters'])
        self.raw_spindle_tank.current_volume_liters = Decimal('20.250')
        self.raw_spindle_tank.save(update_fields=['current_volume_liters'])

        response = self.client.get('/api/dashboard/overview/', **self.auth_headers())

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['reception']['accepted_today_liters'], '125.500')
        self.assertEqual(data['receiving_tanks']['current_volume_liters'], '300.250')
        self.assertEqual(data['preheating_boilers']['current_volume_liters'], '75.125')
        self.assertEqual(data['separators']['current_volume_liters'], '25.500')
        self.assertEqual(data['chemical_mixers']['current_volume_liters'], '50.250')
        mixer_data = next(item for item in data['chemical_mixers']['items'] if item['id'] == self.chemical_mixer.pk)
        self.assertEqual(mixer_data['current_volume_liters'], '50.250')
        self.assertEqual(mixer_data['free_volume_liters'], '449.750')
        self.assertEqual(data['processing_workshops']['current_volume_liters'], '40.125')
        workshop_data = next(
            item for item in data['processing_workshops']['items'] if item['id'] == self.processing_workshop.pk
        )
        self.assertEqual(workshop_data['current_volume_liters'], '40.125')
        self.assertEqual(workshop_data['free_volume_liters'], '459.875')
        self.assertEqual(data['raw_diesel_tanks']['current_volume_liters'], '30.500')
        self.assertEqual(data['raw_spindle_tanks']['current_volume_liters'], '20.250')


class ConcurrentMovementTests(TransactionTestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_superuser('concurrent-admin', password='password')
        self.token = create_access_token(self.admin)
        self.tank = ProductionContainer.objects.create(
            kind=ProductionContainer.KIND_RECEIVING_TANK,
            number=30,
            system_code='receiving-tank-30',
            capacity_liters=Decimal('100.000'),
            current_volume_liters=Decimal('100.000'),
        )
        self.boiler = ProductionContainer.objects.create(
            kind=ProductionContainer.KIND_PREHEATING_BOILER,
            number=30,
            system_code='preheating-boiler-30',
            capacity_liters=Decimal('100.000'),
        )

    def test_simultaneous_movements_cannot_overdraw_tank(self):
        barrier = threading.Barrier(2)

        def send_movement(operation_number):
            close_old_connections()
            client = Client()
            barrier.wait()
            response = client.post(
                '/api/processing/movements/tank-to-boiler/',
                data=json.dumps({
                    'source_tank_id': self.tank.pk,
                    'destination_boiler_id': self.boiler.pk,
                    'volume_liters': '75.000',
                    'idempotency_key': f'concurrent-operation-{operation_number}',
                }),
                content_type='application/json',
                HTTP_AUTHORIZATION=f'Bearer {self.token}',
            )
            close_old_connections()
            return response.status_code

        with ThreadPoolExecutor(max_workers=2) as executor:
            statuses = sorted(executor.map(send_movement, (1, 2)))

        self.assertEqual(statuses, [201, 400])
        self.tank.refresh_from_db()
        self.boiler.refresh_from_db()
        self.assertEqual(self.tank.current_volume_liters, Decimal('25.000'))
        self.assertEqual(self.boiler.current_volume_liters, Decimal('75.000'))
        self.assertEqual(MaterialMovement.objects.filter(movement_type=MaterialMovement.TYPE_TANK_TO_BOILER).count(), 1)

    def test_simultaneous_duplicate_requests_create_one_movement(self):
        barrier = threading.Barrier(2)

        def send_duplicate(operation_number):
            del operation_number
            close_old_connections()
            client = Client()
            barrier.wait()
            response = client.post(
                '/api/processing/movements/tank-to-boiler/',
                data=json.dumps({
                    'source_tank_id': self.tank.pk,
                    'destination_boiler_id': self.boiler.pk,
                    'volume_liters': '25.000',
                    'idempotency_key': 'same-concurrent-operation',
                }),
                content_type='application/json',
                HTTP_AUTHORIZATION=f'Bearer {self.token}',
            )
            close_old_connections()
            return response.status_code

        with ThreadPoolExecutor(max_workers=2) as executor:
            statuses = sorted(executor.map(send_duplicate, (1, 2)))

        self.assertEqual(statuses, [200, 201])
        self.tank.refresh_from_db()
        self.boiler.refresh_from_db()
        self.assertEqual(self.tank.current_volume_liters, Decimal('75.000'))
        self.assertEqual(self.boiler.current_volume_liters, Decimal('25.000'))
        self.assertEqual(MaterialMovement.objects.filter(idempotency_key='same-concurrent-operation').count(), 1)


class WarehouseAccountingTests(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_superuser('warehouse-admin', password='password')
        self.city = City.objects.create(name='Складской город')
        self.supplier = Supplier.objects.create(
            company_name='Складской поставщик',
            city=self.city,
            address='Адрес',
            phone='+998000000000',
        )
        self.category = InventoryCategory.objects.create(name='Тестовая категория')
        self.unit = UnitOfMeasure.objects.create(name='Килограмм тестовый', symbol='кг-т', decimal_places=2)
        self.item = InventoryItem.objects.create(name='Тестовый материал', category=self.category, unit=self.unit)
        self.source = Warehouse.objects.create(name='Основной склад')
        self.destination = Warehouse.objects.create(name='Второй склад')

    def headers(self, user=None):
        return {'HTTP_AUTHORIZATION': f'Bearer {create_access_token(user or self.admin)}'}

    def post_json(self, path, payload=None, user=None):
        return self.client.post(
            path,
            data=json.dumps(payload or {}),
            content_type='application/json',
            **self.headers(user),
        )

    def create_document(self, document_type, quantity, user=None, **overrides):
        payload = {
            'document_type': document_type,
            'document_date': timezone.now().isoformat(),
            'source_warehouse_id': self.source.pk,
            'destination_warehouse_id': self.destination.pk,
            'supplier_id': self.supplier.pk,
            'purpose': 'Для внутреннего использования',
            'lines': [{'item_id': self.item.pk, 'quantity': quantity, 'unit_price': '100.00'}],
            **overrides,
        }
        response = self.post_json('/api/warehouse/documents/', payload, user=user)
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()

    def post_document(self, document_id, user=None):
        return self.post_json(f'/api/warehouse/documents/{document_id}/post/', user=user)

    def receive_stock(self, quantity='10.00', unit_price='100.00'):
        document = self.create_document(
            WarehouseDocument.TYPE_RECEIPT,
            quantity,
            source_warehouse_id=None,
            destination_warehouse_id=self.source.pk,
            lines=[{'item_id': self.item.pk, 'quantity': quantity, 'unit_price': unit_price}],
        )
        response = self.post_document(document['id'])
        self.assertEqual(response.status_code, 200, response.content)
        return document

    def test_receipts_calculate_warehouse_average_and_last_price(self):
        self.receive_stock('10.00', '100.00')
        self.receive_stock('10.00', '200.00')

        balance = WarehouseBalance.objects.get(warehouse=self.source, item=self.item)
        self.item.refresh_from_db()
        self.assertEqual(balance.quantity, Decimal('20.00'))
        self.assertEqual(balance.average_unit_cost, Decimal('150.00'))
        self.assertEqual(self.item.last_purchase_price, Decimal('200.00'))

    def test_issue_cannot_create_negative_stock(self):
        self.receive_stock('5.00')
        issue = self.create_document(
            WarehouseDocument.TYPE_ISSUE,
            '6.00',
            destination_warehouse_id=None,
            supplier_id=None,
        )

        response = self.post_document(issue['id'])

        self.assertEqual(response.status_code, 400)
        balance = WarehouseBalance.objects.get(warehouse=self.source, item=self.item)
        self.assertEqual(balance.quantity, Decimal('5.00'))
        self.assertFalse(WarehouseMovement.objects.filter(document_id=issue['id']).exists())

    def test_transfer_waits_for_confirmation(self):
        self.receive_stock('10.00')
        transfer = self.create_document(
            WarehouseDocument.TYPE_TRANSFER,
            '4.00',
            supplier_id=None,
        )
        response = self.post_document(transfer['id'])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], WarehouseDocument.STATUS_IN_TRANSIT)
        self.assertEqual(WarehouseBalance.objects.get(warehouse=self.source, item=self.item).quantity, Decimal('6.00'))
        self.assertFalse(WarehouseBalance.objects.filter(warehouse=self.destination, item=self.item, quantity__gt=0).exists())

        response = self.post_json(
            f'/api/warehouse/documents/{transfer["id"]}/transfer-decision/',
            {'decision': 'confirm'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(WarehouseBalance.objects.get(warehouse=self.destination, item=self.item).quantity, Decimal('4.00'))

    def test_rejected_transfer_returns_stock(self):
        self.receive_stock('10.00')
        transfer = self.create_document(WarehouseDocument.TYPE_TRANSFER, '4.00', supplier_id=None)
        self.post_document(transfer['id'])

        response = self.post_json(
            f'/api/warehouse/documents/{transfer["id"]}/transfer-decision/',
            {'decision': 'reject'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(WarehouseBalance.objects.get(warehouse=self.source, item=self.item).quantity, Decimal('10.00'))

    def test_non_admin_can_create_but_not_post_backdated_document(self):
        user = get_user_model().objects.create_user('warehouse-user', password='password')
        group = AccessGroup.objects.create(name='Складские сотрудники')
        module, _ = Module.objects.get_or_create(
            code='warehouse-accounting',
            defaults={'name': 'Складской учёт'},
        )
        receipt_permission, _ = Permission.objects.get_or_create(code='receipt', defaults={'name': 'Поступление'})
        view_permission, _ = Permission.objects.get_or_create(code='view', defaults={'name': 'Просмотр'})
        access = GroupModuleAccess.objects.create(group=group, module=module)
        access.permissions.set([view_permission, receipt_permission])
        UserProfile.objects.filter(user=user).update(group=group)
        document = self.create_document(
            WarehouseDocument.TYPE_RECEIPT,
            '2.00',
            document_date='2025-01-10T10:00:00+05:00',
            source_warehouse_id=None,
            user=user,
        )

        response = self.post_document(document['id'], user=user)

        self.assertEqual(response.status_code, 403)

    def test_inventory_sets_actual_balance(self):
        self.receive_stock('10.00')
        inventory = self.create_document(
            WarehouseDocument.TYPE_INVENTORY,
            '7.50',
            destination_warehouse_id=None,
            supplier_id=None,
        )

        response = self.post_document(inventory['id'])

        self.assertEqual(response.status_code, 200)
        self.assertEqual(WarehouseBalance.objects.get(warehouse=self.source, item=self.item).quantity, Decimal('7.50'))

    def test_group_keeps_selected_warehouse_permissions(self):
        module = Module.objects.get(code='warehouse-accounting')
        view_permission = Permission.objects.get(code='view')
        issue_permission = Permission.objects.get(code='issue')

        response = self.post_json('/api/access/groups/', {
            'name': 'Кладовщики расхода',
            'description': 'Только просмотр и внутренний расход.',
            'module_ids': [module.pk],
            'module_permissions': {
                str(module.pk): [view_permission.pk, issue_permission.pk],
            },
            'start_module_id': module.pk,
        })

        self.assertEqual(response.status_code, 201, response.content)
        access = GroupModuleAccess.objects.get(group_id=response.json()['id'], module=module)
        self.assertEqual(set(access.permissions.values_list('code', flat=True)), {'view', 'issue'})


class ProductionLoadingTests(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_superuser('production-loading-admin')
        self.headers = {'HTTP_AUTHORIZATION': f'Bearer {create_access_token(self.admin)}'}
        self.category = InventoryCategory.objects.create(name='Производственные материалы теста')
        self.unit, _ = UnitOfMeasure.objects.get_or_create(symbol='кг', defaults={'name': 'Килограмм', 'decimal_places': 2})
        self.warehouse = Warehouse.objects.create(name='Склад производства теста')
        self.other_warehouse = Warehouse.objects.create(name='Другой склад теста')
        self.items = {}
        for material in ('granules', 'dye', 'sorbent'):
            item = InventoryItem.objects.create(name=f'Материал {material}', category=self.category, unit=self.unit, production_material=material)
            item.permanent_warehouses.add(self.warehouse)
            WarehouseBalance.objects.create(warehouse=self.warehouse, item=item, quantity='100.00', average_unit_cost='200.00')
            self.items[material] = item

    def send(self, target='canisters', lines=None, key='loading-test-key', headers=None, **extra):
        return self.client.post(
            f'/api/warehouse/production-loadings/{target}/',
            data=json.dumps({
                'source_warehouse_id': self.warehouse.pk, 'idempotency_key': key,
                'lines': lines if lines is not None else [{'item_id': self.items['granules'].pk, 'quantity': '10.00'}],
                **extra,
            }), content_type='application/json', **(headers or self.headers),
        )

    def test_loading_creates_posted_issue_with_cost_and_no_production_output(self):
        response = self.send(lines=[
            {'item_id': self.items['granules'].pk, 'quantity': '10.00'},
            {'item_id': self.items['dye'].pk, 'quantity': '0.50'},
        ])
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()['material_cost'], '2100.00')
        self.assertEqual(response.json()['lines'][0]['unit_cost'], '200.00')
        document = WarehouseDocument.objects.get(pk=response.json()['id'])
        self.assertEqual(document.status, 'posted')
        self.assertEqual(document.document_type, 'issue')
        self.assertEqual(document.production_target, 'canisters')
        self.assertEqual(document.movements.count(), 2)
        self.assertFalse(MaterialMovement.objects.exists())
        self.assertEqual(WarehouseBalance.objects.get(warehouse=self.warehouse, item=self.items['granules']).quantity, Decimal('90.00'))

    def test_shortage_rolls_back_all_materials_and_document(self):
        response = self.send(lines=[
            {'item_id': self.items['granules'].pk, 'quantity': '10.00'},
            {'item_id': self.items['dye'].pk, 'quantity': '101.00'},
        ])
        self.assertEqual(response.status_code, 400, response.content)
        self.assertFalse(WarehouseDocument.objects.exists())
        self.assertFalse(WarehouseMovement.objects.exists())
        self.assertEqual(WarehouseBalance.objects.get(warehouse=self.warehouse, item=self.items['granules']).quantity, Decimal('100.00'))

    def test_duplicate_request_does_not_issue_twice_and_changed_payload_conflicts(self):
        first = self.send()
        second = self.send()
        self.assertEqual([first.status_code, second.status_code], [201, 200])
        self.assertEqual(first.json()['id'], second.json()['id'])
        self.assertEqual(WarehouseMovement.objects.count(), 1)
        changed = self.send(lines=[{'item_id': self.items['granules'].pk, 'quantity': '11.00'}])
        self.assertEqual(changed.status_code, 409)

    def test_sorbent_and_packaging_materials_cannot_cross_directions(self):
        self.assertEqual(self.send(target='sorption').status_code, 400)
        self.assertEqual(self.send(lines=[{'item_id': self.items['sorbent'].pk, 'quantity': '10'}]).status_code, 400)
        self.assertEqual(self.send(target='sorption', lines=[{'item_id': self.items['sorbent'].pk, 'quantity': '10'}]).status_code, 201)
        self.assertEqual(self.send(target='caps', key='caps-test').status_code, 201)

    def test_unassigned_warehouse_and_invalid_quantities_are_rejected(self):
        self.assertEqual(self.send(source_warehouse_id=self.other_warehouse.pk).status_code, 400)
        for quantity in ('0', '-1', 'NaN', 'Infinity', '1.001', '1e100'):
            with self.subTest(quantity=quantity):
                self.assertEqual(self.send(lines=[{'item_id': self.items['granules'].pk, 'quantity': quantity}]).status_code, 400)
        response = self.client.post('/api/warehouse/production-loadings/canisters/', data='[]', content_type='application/json', **self.headers)
        self.assertEqual(response.status_code, 400)

    def test_permanent_position_shows_zero_before_first_movement_without_get_writes(self):
        WarehouseBalance.objects.filter(item=self.items['granules']).delete()
        before = WarehouseBalance.objects.count()
        response = self.client.get('/api/warehouse/overview/', **self.headers)
        row = next(row for row in response.json()['balances'] if row['item']['id'] == self.items['granules'].pk)
        self.assertEqual(row['quantity'], '0.00')
        self.assertTrue(row['is_permanent'])
        self.assertEqual(WarehouseBalance.objects.count(), before)
        reference = self.client.get('/api/warehouse/production-loadings/canisters/reference-data/', **self.headers).json()
        self.assertEqual({row['item']['production_material'] for row in reference['materials']}, {'granules', 'dye'})
        self.assertEqual(next(row['quantity'] for row in reference['materials'] if row['item']['id'] == self.items['granules'].pk), '0.00')

    def test_independent_module_permissions_and_admin_only_cancellation(self):
        user = get_user_model().objects.create_user('canister-loading-operator')
        group = AccessGroup.objects.create(name='Операторы загрузки теста')
        access = GroupModuleAccess.objects.create(group=group, module=Module.objects.get(code='canister-loading'))
        access.permissions.set(Permission.objects.filter(code__in=['view', 'create']))
        UserProfile.objects.filter(user=user).update(group=group)
        headers = {'HTTP_AUTHORIZATION': f'Bearer {create_access_token(user)}'}
        self.assertEqual(self.client.get('/api/warehouse/overview/', **headers).status_code, 403)
        self.assertEqual(self.client.get('/api/warehouse/production-loadings/caps/reference-data/', **headers).status_code, 403)
        self.assertEqual(self.client.get('/api/warehouse/production-loadings/canisters/reference-data/', **headers).status_code, 200)
        response = self.send(headers=headers)
        self.assertEqual(response.status_code, 201, response.content)
        cancel_url = f'/api/warehouse/documents/{response.json()["id"]}/cancel/'
        self.assertEqual(self.client.post(cancel_url, **headers).status_code, 403)
        self.assertEqual(self.client.post(cancel_url, **self.headers).status_code, 200)
        self.assertEqual(WarehouseBalance.objects.get(warehouse=self.warehouse, item=self.items['granules']).quantity, Decimal('100.00'))
        self.assertEqual(self.send(headers=headers).json()['status'], 'cancelled')
        self.assertEqual(WarehouseMovement.objects.count(), 2)
        self.assertEqual(self.client.post(cancel_url, **self.headers).status_code, 423)

    def test_item_settings_require_permanent_warehouses_and_kg(self):
        payload = {'name': 'Новый материал теста', 'category_id': self.category.pk, 'unit_id': self.unit.pk, 'production_material': 'dye', 'permanent_warehouse_ids': []}
        response = self.client.post('/api/warehouse/settings/items/', data=json.dumps(payload), content_type='application/json', **self.headers)
        self.assertEqual(response.status_code, 400)
        payload['permanent_warehouse_ids'] = [self.warehouse.pk]
        response = self.client.post('/api/warehouse/settings/items/', data=json.dumps(payload), content_type='application/json', **self.headers)
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()['permanent_warehouse_ids'], [self.warehouse.pk])
        self.assertEqual(self.client.delete(f'/api/warehouse/settings/items/{response.json()["id"]}/', **self.headers).status_code, 400)
        payload['unit_id'] = UnitOfMeasure.objects.get(symbol='л').pk
        payload['name'] = 'Неверная единица теста'
        response = self.client.post('/api/warehouse/settings/items/', data=json.dumps(payload), content_type='application/json', **self.headers)
        self.assertEqual(response.status_code, 400)


    def test_view_permission_does_not_allow_loading_and_settings_are_protected(self):
        user = get_user_model().objects.create_user('loading-viewer')
        group = AccessGroup.objects.create(name='Просмотр загрузок теста')
        access = GroupModuleAccess.objects.create(group=group, module=Module.objects.get(code='canister-loading'))
        access.permissions.set(Permission.objects.filter(code='view'))
        UserProfile.objects.filter(user=user).update(group=group)
        headers = {'HTTP_AUTHORIZATION': f'Bearer {create_access_token(user)}'}
        self.assertEqual(self.client.get('/api/warehouse/production-loadings/canisters/', **headers).status_code, 200)
        self.assertEqual(self.send(headers=headers).status_code, 403)
        self.assertEqual(self.client.get('/api/warehouse/settings/items/', **headers).status_code, 403)
        self.assertEqual(self.client.delete(f'/api/warehouse/settings/warehouses/{self.warehouse.pk}/', **self.headers).status_code, 400)
        response = self.client.patch(
            f'/api/warehouse/settings/warehouses/{self.warehouse.pk}/',
            data=json.dumps({'is_active': False}), content_type='application/json', **self.headers,
        )
        self.assertEqual(response.status_code, 400)


class ConcurrentProductionLoadingTests(TransactionTestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_superuser('parallel-loading-admin')
        self.token = create_access_token(self.admin)
        category = InventoryCategory.objects.create(name='Параллельная загрузка')
        unit, _ = UnitOfMeasure.objects.get_or_create(symbol='кг', defaults={'name': 'Килограмм', 'decimal_places': 2})
        self.warehouse = Warehouse.objects.create(name='Склад параллельной загрузки')
        self.item = InventoryItem.objects.create(name='Гранулы параллельной загрузки', category=category, unit=unit, production_material='granules')
        self.item.permanent_warehouses.add(self.warehouse)
        WarehouseBalance.objects.create(warehouse=self.warehouse, item=self.item, quantity='100.00', average_unit_cost='100.00')

    def run_parallel(self, duplicate=False):
        barrier = threading.Barrier(2)

        def send_request(number):
            close_old_connections()
            try:
                barrier.wait()
                response = Client().post(
                    '/api/warehouse/production-loadings/canisters/',
                    data=json.dumps({
                        'source_warehouse_id': self.warehouse.pk,
                        'idempotency_key': 'duplicate-loading' if duplicate else f'parallel-loading-{number}',
                        'lines': [{'item_id': self.item.pk, 'quantity': '75.00'}],
                    }), content_type='application/json', HTTP_AUTHORIZATION=f'Bearer {self.token}',
                )
                return response.status_code
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            return sorted(executor.map(send_request, (1, 2)))

    def test_concurrent_requests_cannot_overdraw_stock(self):
        self.assertEqual(self.run_parallel(), [201, 400])
        self.assertEqual(WarehouseBalance.objects.get(warehouse=self.warehouse, item=self.item).quantity, Decimal('25.00'))
        self.assertEqual(WarehouseMovement.objects.count(), 1)

    def test_concurrent_retry_issues_material_once(self):
        self.assertEqual(self.run_parallel(duplicate=True), [200, 201])
        self.assertEqual(WarehouseBalance.objects.get(warehouse=self.warehouse, item=self.item).quantity, Decimal('25.00'))
        self.assertEqual(WarehouseMovement.objects.count(), 1)


class PackagingProductionTests(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_superuser('packaging-accounting-admin')
        self.headers = {'HTTP_AUTHORIZATION': f'Bearer {create_access_token(self.admin)}'}
        category = InventoryCategory.objects.create(name='Упаковка теста')
        kg = UnitOfMeasure.objects.get(symbol='кг')
        pieces = UnitOfMeasure.objects.get(symbol='шт')
        self.warehouse = Warehouse.objects.create(name='Склад упаковки теста')
        self.raw = InventoryItem.objects.create(name='Гранулы выпуска теста', category=category, unit=kg, production_material='granules')
        self.raw.permanent_warehouses.add(self.warehouse)
        self.product = InventoryItem.objects.create(name='Канистра теста', category=category, unit=pieces, production_product='canisters')
        self.cap = InventoryItem.objects.create(name='Крышка теста', category=category, unit=pieces, production_product='caps')
        WarehouseBalance.objects.create(warehouse=self.warehouse, item=self.raw, quantity='100', average_unit_cost='200')
        loading = self.post('/api/warehouse/production-loadings/canisters/', {
            'source_warehouse_id': self.warehouse.pk, 'idempotency_key': 'packaging-loading',
            'lines': [{'item_id': self.raw.pk, 'quantity': '50'}],
        })
        self.assertEqual(loading.status_code, 201, loading.content)
        self.loading_id = loading.json()['id']
        self.source = WarehouseMovement.objects.get(document_id=self.loading_id)

    def post(self, path, body=None, headers=None):
        return self.client.post(path, data=json.dumps(body or {}), content_type='application/json', **(headers or self.headers))

    def output(self, quantity='20', key='output-test', lines=None, target='canisters', source_id=None, headers=None):
        return self.post(f'/api/warehouse/production-outputs/{target}/', {
            'idempotency_key': key,
            'lines': lines if lines is not None else [{'item_id': self.product.pk, 'disposition': 'good', 'quantity': 100}],
            'material_usages': [{'source_movement_id': source_id or self.source.pk, 'quantity': quantity}],
        }, headers=headers)

    def test_output_consumes_production_stock_without_second_warehouse_issue(self):
        response = self.output(lines=[
            {'item_id': self.product.pk, 'disposition': 'good', 'quantity': 100},
            {'item_id': self.product.pk, 'disposition': 'deviation', 'quantity': 10},
            {'item_id': self.product.pk, 'disposition': 'reject', 'quantity': 5},
        ])
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()['material_cost'], '4000.00')
        self.assertEqual(WarehouseBalance.objects.get(warehouse=self.warehouse, item=self.raw).quantity, Decimal('50.00'))
        self.assertEqual(WarehouseMovement.objects.count(), 1)
        self.assertFalse(WarehouseBalance.objects.filter(item=self.product).exists())
        reference = self.client.get('/api/warehouse/production-outputs/canisters/reference-data/', **self.headers).json()
        self.assertEqual(reference['production_balances'][0]['available_quantity'], '30.00')
        self.assertEqual(reference['production_balances'][0]['used_quantity'], '20.00')
        self.assertEqual(ProductionOutputLine.objects.count(), 3)

    def test_shortage_invalid_counts_and_wrong_products_leave_no_usage(self):
        for quantity in ('51', '0', '-1', 'NaN', 'Infinity', '1.001'):
            with self.subTest(quantity=quantity):
                self.assertEqual(self.output(quantity=quantity).status_code, 400)
        for count in (0, -1, 1.5, True, 2147483648):
            self.assertEqual(self.output(lines=[{'item_id': self.product.pk, 'disposition': 'good', 'quantity': count}]).status_code, 400)
        self.assertEqual(self.output(lines=[{'item_id': self.cap.pk, 'disposition': 'good', 'quantity': 1}]).status_code, 400)
        self.assertFalse(ProductionOutput.objects.exists())
        self.assertFalse(ProductionMaterialUsage.objects.exists())

    def test_duplicate_output_and_changed_payload(self):
        first, second = self.output(), self.output()
        self.assertEqual([first.status_code, second.status_code], [201, 200])
        self.assertEqual(first.json()['id'], second.json()['id'])
        self.assertEqual(self.output(quantity='21').status_code, 409)
        self.assertEqual(ProductionMaterialUsage.objects.count(), 1)

    def test_caps_reject_deviation_and_cannot_use_canister_sources(self):
        lines = [{'item_id': self.cap.pk, 'disposition': 'deviation', 'quantity': 1}]
        self.assertEqual(self.output(lines=lines, target='caps').status_code, 400)
        lines[0]['disposition'] = 'good'
        self.assertEqual(self.output(lines=lines, target='caps').status_code, 400)
        loading = self.post('/api/warehouse/production-loadings/caps/', {
            'source_warehouse_id': self.warehouse.pk, 'idempotency_key': 'caps-loading',
            'lines': [{'item_id': self.raw.pk, 'quantity': '10'}],
        })
        source = WarehouseMovement.objects.get(document_id=loading.json()['id'])
        self.assertEqual(self.output(target='caps', lines=lines, quantity='10', source_id=source.pk).status_code, 201)

    def test_loading_cancellation_blocked_until_output_cancelled(self):
        response = self.output()
        loading_cancel = f'/api/warehouse/documents/{self.loading_id}/cancel/'
        self.assertEqual(self.post(loading_cancel).status_code, 423)
        output_cancel = f'/api/warehouse/production-outputs/canisters/{response.json()["id"]}/cancel/'
        self.assertEqual(self.post(output_cancel).status_code, 200)
        self.assertEqual(self.post(output_cancel).status_code, 423)
        self.assertEqual(self.output().json()['is_cancelled'], True)
        self.assertEqual(self.post(loading_cancel).status_code, 200)
        self.assertEqual(self.output(key='after-cancellation').status_code, 400)
        self.assertEqual(WarehouseBalance.objects.get(warehouse=self.warehouse, item=self.raw).quantity, Decimal('100.00'))

    def test_cents_are_preserved_when_all_material_is_consumed(self):
        self.source.quantity_delta = Decimal('-0.02')
        self.source.unit_cost = Decimal('0.50')
        self.source.total_value_delta = Decimal('-0.01')
        self.source.save()
        self.assertEqual(self.output(quantity='0.01').status_code, 201)
        self.assertEqual(self.output(quantity='0.01', key='last-cent').status_code, 201)
        self.assertEqual(sum(ProductionMaterialUsage.objects.values_list('material_cost', flat=True)), Decimal('0.01'))

    def test_output_permissions_are_separate_from_loading(self):
        user = get_user_model().objects.create_user('packaging-output-operator')
        group = AccessGroup.objects.create(name='Выпуск упаковки теста')
        access = GroupModuleAccess.objects.create(group=group, module=Module.objects.get(code='canister-output'))
        access.permissions.set(Permission.objects.filter(code__in=['view', 'create']))
        UserProfile.objects.filter(user=user).update(group=group)
        headers = {'HTTP_AUTHORIZATION': f'Bearer {create_access_token(user)}'}
        self.assertEqual(self.client.get('/api/warehouse/production-outputs/canisters/reference-data/', **headers).status_code, 200)
        self.assertEqual(self.client.get('/api/warehouse/production-outputs/caps/', **headers).status_code, 403)
        self.assertEqual(self.client.get('/api/warehouse/production-loadings/canisters/', **headers).status_code, 403)
        response = self.output(headers=headers)
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(self.post(f'/api/warehouse/production-outputs/canisters/{response.json()["id"]}/cancel/', headers=headers).status_code, 403)


    def test_overview_shows_registered_output_not_warehouse_stock(self):
        response = self.output()
        overview = self.client.get('/api/dashboard/overview/', **self.headers).json()['packaging_production']
        self.assertEqual(overview['canisters']['materials']['granules']['available_quantity'], '30.00')
        self.assertEqual(overview['canisters']['output_totals']['good'], 100)
        self.assertEqual(overview['caps']['output_totals']['good'], 0)
        self.assertFalse(WarehouseBalance.objects.filter(item=self.product).exists())
        self.post(f'/api/warehouse/production-outputs/canisters/{response.json()["id"]}/cancel/')
        overview = self.client.get('/api/dashboard/overview/', **self.headers).json()['packaging_production']
        self.assertEqual(overview['canisters']['output_totals']['good'], 0)
        self.assertEqual(overview['canisters']['materials']['granules']['available_quantity'], '50.00')

    def test_product_configuration_and_history_roles_are_protected(self):
        self.output()
        for item, payload in (
            (self.raw, {'production_material': ''}),
            (self.product, {'production_product': 'caps'}),
            (self.product, {'unit_id': self.raw.unit_id}),
        ):
            response = self.client.patch(f'/api/warehouse/settings/items/{item.pk}/', data=json.dumps(payload), content_type='application/json', **self.headers)
            self.assertEqual(response.status_code, 400, response.content)
        response = self.client.patch(f'/api/warehouse/settings/units/{self.product.unit_id}/', data=json.dumps({'decimal_places': 2}), content_type='application/json', **self.headers)
        self.assertEqual(response.status_code, 400)
        response = self.client.patch(f'/api/warehouse/settings/units/{self.raw.unit_id}/', data=json.dumps({'decimal_places': 0}), content_type='application/json', **self.headers)
        self.assertEqual(response.status_code, 400)


class ConcurrentPackagingOutputTests(TransactionTestCase):
    def setUp(self):
        admin = get_user_model().objects.create_superuser('parallel-packaging-admin')
        self.headers = {'HTTP_AUTHORIZATION': f'Bearer {create_access_token(admin)}'}
        category = InventoryCategory.objects.create(name='Параллельный выпуск теста')
        kg, _ = UnitOfMeasure.objects.get_or_create(symbol='кг', defaults={'name': 'Килограмм', 'decimal_places': 2})
        pieces, _ = UnitOfMeasure.objects.get_or_create(symbol='шт', defaults={'name': 'Штука', 'decimal_places': 0})
        self.warehouse = Warehouse.objects.create(name='Склад параллельного выпуска')
        raw = InventoryItem.objects.create(name='Сырьё параллельного выпуска', category=category, unit=kg, production_material='granules')
        raw.permanent_warehouses.add(self.warehouse)
        self.product = InventoryItem.objects.create(name='Изделие параллельного выпуска', category=category, unit=pieces, production_product='canisters')
        WarehouseBalance.objects.create(warehouse=self.warehouse, item=raw, quantity='100', average_unit_cost='100')
        response = self.client.post('/api/warehouse/production-loadings/canisters/', data=json.dumps({
            'source_warehouse_id': self.warehouse.pk, 'idempotency_key': 'parallel-output-loading',
            'lines': [{'item_id': raw.pk, 'quantity': '100'}],
        }), content_type='application/json', **self.headers)
        self.loading_id = response.json()['id']
        self.source = WarehouseMovement.objects.get(document_id=self.loading_id)

    def run_parallel(self, duplicate=False, cancel=False):
        barrier = threading.Barrier(2)

        def perform(number):
            close_old_connections()
            try:
                barrier.wait()
                if cancel and number == 2:
                    return Client().post(f'/api/warehouse/documents/{self.loading_id}/cancel/', **self.headers).status_code
                return Client().post('/api/warehouse/production-outputs/canisters/', data=json.dumps({
                    'idempotency_key': 'duplicate-output' if duplicate else f'parallel-output-{number}',
                    'lines': [{'item_id': self.product.pk, 'disposition': 'good', 'quantity': 10}],
                    'material_usages': [{'source_movement_id': self.source.pk, 'quantity': '75'}],
                }), content_type='application/json', **self.headers).status_code
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            return sorted(executor.map(perform, (1, 2)))

    def test_concurrent_output_cannot_overdraw_production_material(self):
        self.assertEqual(self.run_parallel(), [201, 400])
        self.assertEqual(ProductionMaterialUsage.objects.count(), 1)
        self.assertEqual(WarehouseMovement.objects.count(), 1)

    def test_duplicate_concurrent_output_is_idempotent(self):
        self.assertEqual(self.run_parallel(duplicate=True), [200, 201])
        self.assertEqual(ProductionOutput.objects.count(), 1)

    def test_loading_cancellation_and_output_cannot_both_succeed(self):
        self.assertIn(self.run_parallel(cancel=True), ([200, 400], [201, 423]))
        if ProductionOutput.objects.exists():
            self.assertEqual(WarehouseDocument.objects.get(pk=self.loading_id).status, 'posted')
        else:
            self.assertEqual(WarehouseDocument.objects.get(pk=self.loading_id).status, 'cancelled')


class KnowledgeBaseTests(TestCase):
    def setUp(self):
        self.editor = get_user_model().objects.create_user('knowledge-editor')
        self.reader = get_user_model().objects.create_user('knowledge-reader')
        self.outsider = get_user_model().objects.create_user('knowledge-outsider')
        self.module = Module.objects.get(code='knowledge-base')
        for user, codes in (
            (self.editor, ('view', 'create', 'update', 'delete')),
            (self.reader, ('view',)),
        ):
            group = AccessGroup.objects.create(name=f'Группа {user.username}')
            access = GroupModuleAccess.objects.create(group=group, module=self.module)
            access.permissions.set(Permission.objects.filter(code__in=codes))
            UserProfile.objects.filter(user=user).update(group=group)
        self.category = KnowledgeCategory.objects.create(name='Инструкции для теста')
        self.article = KnowledgeArticle.objects.create(
            category=self.category,
            title='Порядок приёма',
            summary='Инструкция',
            content='## Заявка\n\nСоздайте заявку и дождитесь анализа.',
        )

    def request_json(self, method, path, payload=None, user=None):
        return getattr(self.client, method)(
            path,
            data=json.dumps(payload if payload is not None else {}),
            content_type='application/json',
            HTTP_AUTHORIZATION=f'Bearer {create_access_token(user or self.editor)}',
        )

    def test_seeded_guides_and_role_access_exist(self):
        self.assertEqual(self.module.default_path, '/knowledge')
        self.assertTrue(KnowledgeArticle.objects.filter(title='Оформление приёма: от заявки до бака').exists())
        for name in ('Лаборант', 'Менеджер приема сырья'):
            access = GroupModuleAccess.objects.get(group__name=name, module=self.module)
            self.assertEqual(set(access.permissions.values_list('code', flat=True)), {'view'})

    def test_reader_can_read_but_cannot_mutate_articles_or_categories(self):
        headers = {'HTTP_AUTHORIZATION': f'Bearer {create_access_token(self.reader)}'}
        response = self.client.get('/api/knowledge/articles/', **headers)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(any(item['id'] == self.article.pk for item in response.json()['items']))
        for entity, item_id in (('articles', self.article.pk), ('categories', self.category.pk)):
            path = f'/api/knowledge/{entity}/'
            for method, url in (('post', path), ('patch', f'{path}{item_id}/'), ('delete', f'{path}{item_id}/')):
                response = self.request_json(method, url, {'title': 'Подмена', 'name': 'Подмена'}, self.reader)
                self.assertEqual(response.status_code, 403)
        self.article.refresh_from_db()
        self.assertEqual(self.article.title, 'Порядок приёма')

    def test_authentication_and_module_access_are_required(self):
        for entity in ('articles', 'categories'):
            path = f'/api/knowledge/{entity}/'
            self.assertEqual(self.client.get(path).status_code, 401)
            response = self.client.get(path, HTTP_AUTHORIZATION=f'Bearer {create_access_token(self.outsider)}')
            self.assertEqual(response.status_code, 403)
        self.module.is_active = False
        self.module.save(update_fields=['is_active'])
        response = self.client.get('/api/knowledge/articles/', HTTP_AUTHORIZATION=f'Bearer {create_access_token(self.reader)}')
        self.assertEqual(response.status_code, 403)

    def test_article_crud_preserves_authorship_and_plain_text(self):
        response = self.request_json('post', '/api/knowledge/articles/', {
            'category_id': self.category.pk,
            'title': 'Новая статья',
            'summary': 'Описание',
            'content': '<script>example()</script>\n\nОбычный текст.',
        })
        self.assertEqual(response.status_code, 201, response.content)
        article = KnowledgeArticle.objects.get(pk=response.json()['id'])
        self.assertEqual(article.created_by, self.editor)
        self.assertEqual(response.json()['content'], '<script>example()</script>\n\nОбычный текст.')
        path = f'/api/knowledge/articles/{article.pk}/'
        response = self.request_json('patch', path, {'title': 'Обновлённая статья'})
        self.assertEqual(response.status_code, 200)
        article.refresh_from_db()
        self.assertEqual(article.title, 'Обновлённая статья')
        self.assertEqual(article.updated_by, self.editor)
        self.assertEqual(self.request_json('delete', path).status_code, 200)
        self.assertFalse(KnowledgeArticle.objects.filter(pk=article.pk).exists())

    def test_category_with_articles_cannot_be_deleted(self):
        path = f'/api/knowledge/categories/{self.category.pk}/'
        self.assertEqual(self.request_json('delete', path).status_code, 400)
        self.assertTrue(KnowledgeCategory.objects.filter(pk=self.category.pk).exists())
        self.article.delete()
        self.assertEqual(self.request_json('delete', path).status_code, 200)

    def test_validation_and_duplicate_categories_return_client_errors(self):
        for payload in (
            {'category_id': self.category.pk, 'title': '', 'content': 'Текст'},
            {'category_id': 999999, 'title': 'Статья', 'content': 'Текст'},
            {'category_id': '9' * 100, 'title': 'Статья', 'content': 'Текст'},
            {'category_id': self.category.pk, 'title': 'Статья', 'content': ['Неверный тип']},
            {'category_id': self.category.pk, 'title': 'Статья', 'content': ''},
            {'category_id': self.category.pk, 'title': 'x' * 201, 'content': 'Текст'},
            [],
        ):
            response = self.request_json('post', '/api/knowledge/articles/', payload)
            self.assertEqual(response.status_code, 400, response.content)
        response = self.request_json('post', '/api/knowledge/categories/', {'name': self.category.name})
        self.assertEqual(response.status_code, 400)
        response = self.request_json('post', '/api/knowledge/categories/', {'name': 'Отдельный раздел'})
        self.assertEqual(response.status_code, 201, response.content)
