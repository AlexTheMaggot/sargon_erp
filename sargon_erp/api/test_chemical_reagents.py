from decimal import Decimal
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.test import TestCase

from .auth import create_access_token
from .models import (
    AccessGroup, InventoryCategory, InventoryItem, MaterialMovement, ProductionContainer, UnitOfMeasure,
    UserProfile, Warehouse, WarehouseBalance, WarehouseDocument, WarehouseMovement,
)


BASE_API = '/api/warehouse/production-loadings/'
ACID_API = f'{BASE_API}chemical_acid/'
MIXER_BENTONITE_API = f'{BASE_API}chemical_bentonite/'
FILTER_BENTONITE_API = f'{BASE_API}bentonite_filter/'
ITEMS_API = '/api/warehouse/settings/items/'


class ChemicalReagentTests(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_superuser('chemical-reagents-admin')
        self.operator = get_user_model().objects.create_user('chemical-reagents-operator')
        UserProfile.objects.filter(user=self.operator).update(group=AccessGroup.objects.get(name='Начальник смены'))
        self.headers = {'HTTP_AUTHORIZATION': f'Bearer {create_access_token(self.operator)}'}
        self.admin_headers = {'HTTP_AUTHORIZATION': f'Bearer {create_access_token(self.admin)}'}
        self.warehouse = Warehouse.objects.create(name='Chemical reagent test warehouse')
        self.liters = UnitOfMeasure.objects.get(symbol='л')
        self.kilograms = UnitOfMeasure.objects.get(symbol='кг')
        self.category = InventoryCategory.objects.get(name='Сырьё')
        response = self.post(ITEMS_API, self.acid_item_payload(), self.admin_headers)
        self.assertEqual(response.status_code, 201, response.content)
        self.acid = InventoryItem.objects.get(pk=response.json()['id'])
        self.bentonite = InventoryItem.objects.create(
            name='Bentonite for both stages', category=self.category, unit=self.kilograms, production_material='bentonite',
        )
        self.bentonite.permanent_warehouses.add(self.warehouse)
        self.bentonite_balance = WarehouseBalance.objects.create(warehouse=self.warehouse, item=self.bentonite, quantity=100)
        self.mixer = ProductionContainer.objects.create(
            kind='chemical_mixer', number=91, system_code='chemical-reagents-mixer', capacity_liters=100,
        )
        self.filter = ProductionContainer.objects.create(kind='finishing_filter', number=91, system_code='chemical-reagents-filter')

    def acid_item_payload(self, **updates):
        return {
            'name': 'Кислота', 'category_id': self.category.pk, 'unit_id': self.liters.pk,
            'production_material': 'acid', 'permanent_warehouse_ids': [self.warehouse.pk], **updates,
        }

    def load_payload(self, item, quantity='1.25', **updates):
        return {
            'mixer_id': self.mixer.pk, 'source_warehouse_id': self.warehouse.pk,
            'lines': [{'item_id': item.pk, 'quantity': quantity}], 'idempotency_key': str(uuid4()), **updates,
        }

    def post(self, path, body, headers=None):
        return self.client.post(path, body, content_type='application/json', **(headers or self.headers))

    def test_acid_is_single_position_in_liters_and_visible_at_zero(self):
        result = self.client.get(ACID_API + 'reference-data/', **self.headers).json()
        item = result['materials'][0]
        self.assertEqual((item['item']['id'], item['item']['unit']['symbol'], item['quantity']), (self.acid.pk, 'л', '0.00'))
        self.assertIn({'id': self.mixer.pk, 'name': self.mixer.display_name}, result['mixers'])
        self.assertNotIn(self.filter.pk, {mixer['id'] for mixer in result['mixers']})
        self.assertFalse(self.acid.warehouse_balances.exists())
        self.assertEqual(self.post(ACID_API, self.load_payload(self.acid)).status_code, 400)
        self.assertFalse(WarehouseDocument.objects.exists())
        for unit in (self.liters, self.kilograms):
            response = self.post(ITEMS_API, self.acid_item_payload(name='Другой материал', unit_id=unit.pk), self.admin_headers)
            self.assertEqual(response.status_code, 400)

    def test_acid_can_be_loaded_into_empty_mixer_once_and_does_not_change_oil(self):
        balance = WarehouseBalance.objects.create(item=self.acid, warehouse=self.warehouse, quantity=10, average_unit_cost=2)
        payload = self.load_payload(self.acid)
        response = self.post(ACID_API, payload)
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(self.post(ACID_API, payload).status_code, 200)
        other = ProductionContainer.objects.create(
            kind='chemical_mixer', number=92, system_code='chemical-reagents-other', capacity_liters=100,
        )
        self.assertEqual(self.post(ACID_API, {**payload, 'mixer_id': other.pk}).status_code, 409)
        balance.refresh_from_db()
        self.mixer.refresh_from_db()
        self.assertEqual(balance.quantity, Decimal('8.75'))
        self.assertEqual(self.mixer.current_volume_liters, 0)
        document = WarehouseDocument.objects.get()
        self.assertEqual(document.production_mixer, self.mixer)
        self.assertEqual(document.posted_by, self.operator)
        self.assertEqual(document.movements.get().quantity_delta, Decimal('-1.25'))
        self.assertFalse(MaterialMovement.objects.exists())
        history = self.client.get(ACID_API, **self.headers).json()['items']
        self.assertEqual(history[0]['mixer_name'], self.mixer.display_name)
        self.assertNotIn('material_cost', history[0])
        self.assertEqual(self.client.delete(f'/api/processing/containers/{self.mixer.pk}/', **self.admin_headers).status_code, 400)

    def test_bentonite_uses_one_balance_and_separate_histories(self):
        self.assertEqual(self.post(MIXER_BENTONITE_API, self.load_payload(self.bentonite, '20')).status_code, 201)
        self.assertEqual(self.post(FILTER_BENTONITE_API, self.load_payload(self.bentonite, '30')).status_code, 201)
        self.bentonite_balance.refresh_from_db()
        self.assertEqual(self.bentonite_balance.quantity, 50)
        for path in (MIXER_BENTONITE_API, FILTER_BENTONITE_API):
            self.assertEqual(len(self.client.get(path, **self.headers).json()['items']), 1)
            self.assertEqual(self.client.get(path + 'reference-data/', **self.headers).json()['materials'][0]['quantity'], '50.00')
        self.assertEqual(self.client.get(ACID_API, **self.headers).json()['items'], [])
        self.assertEqual(WarehouseMovement.objects.count(), 2)

    def test_wrong_material_inactive_mixer_and_unrelated_warehouse_access_are_rejected(self):
        self.assertEqual(self.client.get(ACID_API).status_code, 401)
        self.assertEqual(self.client.get('/api/warehouse/overview/', **self.headers).status_code, 403)
        self.assertEqual(self.client.get(ITEMS_API, **self.headers).status_code, 403)
        self.assertEqual(self.post(ACID_API, self.load_payload(self.bentonite)).status_code, 400)
        self.assertEqual(self.post(MIXER_BENTONITE_API, self.load_payload(self.bentonite, mixer_id=self.filter.pk)).status_code, 400)
        self.assertEqual(self.post(MIXER_BENTONITE_API, self.load_payload(self.bentonite, lines=[
            {'item_id': self.bentonite.pk, 'quantity': '1'}, {'item_id': self.acid.pk, 'quantity': '1'},
        ])).status_code, 400)
        self.mixer.is_active = False
        self.mixer.save(update_fields=['is_active'])
        self.assertEqual(self.post(MIXER_BENTONITE_API, self.load_payload(self.bentonite)).status_code, 400)
        self.assertFalse(WarehouseDocument.objects.exists())

    def test_oil_transfer_does_not_require_reagent_records(self):
        self.mixer.current_volume_liters = 30
        self.mixer.oil_product = 'diesel'
        self.mixer.save(update_fields=['current_volume_liters', 'oil_product'])
        recipient = ProductionContainer.objects.create(
            kind='finishing_mixer', number=91, system_code='chemical-reagents-sand', capacity_liters=100,
        )
        response = self.post('/api/processing/oil-movements/finishing-mixer-loading/', {
            'source_id': self.mixer.pk, 'destination_id': recipient.pk, 'volume_liters': '30', 'idempotency_key': str(uuid4()),
        })
        self.assertEqual(response.status_code, 201, response.content)
        self.assertFalse(WarehouseDocument.objects.exists())
