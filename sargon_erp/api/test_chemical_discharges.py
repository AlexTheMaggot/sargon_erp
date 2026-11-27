from decimal import Decimal
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.test import TestCase

from .auth import create_access_token
from .models import (
    AccessGroup, ChemicalMixerDischarge, GroupModuleAccess, MaterialMovement, Module,
    OperationAuditLog, Permission, ProductionContainer, UserProfile, WarehouseDocument,
)


ENDPOINT = '/api/processing/chemical-mixer-discharges/'


class ChemicalMixerDischargeTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('discharge-operator')
        self.headers = {'HTTP_AUTHORIZATION': f'Bearer {create_access_token(self.user)}'}
        UserProfile.objects.filter(user=self.user).update(group=AccessGroup.objects.get(name='Начальник смены'))
        self.mixer = ProductionContainer.objects.create(
            kind='chemical_mixer', number=91, system_code='discharge-mixer', capacity_liters=100,
            current_volume_liters=20, oil_product='diesel',
        )
        self.tank = ProductionContainer.objects.create(
            kind='receiving_tank', number=91, system_code='discharge-tank', capacity_liters=100,
        )
        self.inactive = ProductionContainer.objects.create(
            kind='chemical_mixer', number=92, system_code='discharge-inactive-mixer', capacity_liters=100, is_active=False,
        )

    def payload(self, **changes):
        return {
            'mixer_id': self.mixer.pk, 'discharge_type': 'water', 'quantity': '10.125',
            'idempotency_key': str(uuid4()), **changes,
        }

    def post(self, payload, headers=None):
        return self.client.post(ENDPOINT, payload, content_type='application/json', **(self.headers if headers is None else headers))

    def test_records_water_and_waste_without_touching_oil_or_warehouse(self):
        for kind, unit, quantity in (('water', 'л', '10.125'), ('waste', 'кг', '0.600')):
            with self.subTest(kind=kind):
                result = self.post(self.payload(discharge_type=kind, quantity=quantity))
                self.assertEqual(result.status_code, 201, result.content)
                data = result.json()
                self.assertEqual((data['discharge_type'], data['quantity_unit'], data['quantity']), (kind, unit, quantity))
                record = ChemicalMixerDischarge.objects.get(pk=data['id'])
                self.assertEqual((record.created_by, record.mixer, record.quantity), (self.user, self.mixer, Decimal(quantity)))
                audit = OperationAuditLog.objects.get(object_type='chemical_mixer_discharge', object_id=str(record.pk))
                self.assertEqual(audit.changes['quantity_unit'], unit)
        self.mixer.refresh_from_db()
        self.assertEqual(self.mixer.current_volume_liters, Decimal('20'))
        self.assertEqual(self.mixer.oil_product, 'diesel')
        self.assertFalse(MaterialMovement.objects.exists())
        self.assertFalse(WarehouseDocument.objects.exists())

    def test_retries_are_idempotent_and_conflicts_rejected(self):
        payload = self.payload()
        first = self.post(payload)
        self.assertEqual(first.status_code, 201)
        repeated = self.post(payload)
        self.assertEqual(repeated.status_code, 200)
        self.assertEqual(first.json(), repeated.json())
        for changes in ({'discharge_type': 'waste'}, {'quantity': '10.126'}):
            self.assertEqual(self.post({**payload, **changes}).status_code, 409)
        self.assertEqual(ChemicalMixerDischarge.objects.count(), 1)
        self.assertEqual(OperationAuditLog.objects.filter(object_type='chemical_mixer_discharge').count(), 1)

    def test_invalid_type_quantity_and_equipment_are_rejected(self):
        for changes in (
            {'discharge_type': 'oil'}, {'quantity': '0'}, {'quantity': '-1'},
            {'quantity': 'NaN'}, {'quantity': '1.0001'}, {'mixer_id': self.tank.pk},
            {'mixer_id': self.inactive.pk}, {'mixer_id': True},
        ):
            with self.subTest(changes=changes):
                self.assertEqual(self.post(self.payload(**changes)).status_code, 400)
        self.assertFalse(ChemicalMixerDischarge.objects.exists())

    def test_permission_and_reference_data_are_isolated(self):
        self.assertEqual(self.client.get(ENDPOINT).status_code, 401)
        viewer = get_user_model().objects.create_user('discharge-viewer')
        viewer_headers = {'HTTP_AUTHORIZATION': f'Bearer {create_access_token(viewer)}'}
        self.assertEqual(self.client.get(ENDPOINT, **viewer_headers).status_code, 403)
        group = AccessGroup.objects.create(name='Discharge viewer test')
        access = GroupModuleAccess.objects.create(group=group, module=Module.objects.get(code='chemical-mixer-discharges'))
        access.permissions.add(Permission.objects.get(code='view'))
        UserProfile.objects.filter(user=viewer).update(group=group)
        response = self.client.get(ENDPOINT, **viewer_headers)
        self.assertEqual(response.status_code, 200)
        self.assertIn({'id': self.mixer.pk, 'name': self.mixer.display_name}, response.json()['mixers'])
        for excluded in (self.tank, self.inactive):
            self.assertNotIn(excluded.pk, {item['id'] for item in response.json()['mixers']})
        self.assertEqual(self.post(self.payload(), viewer_headers).status_code, 403)
        self.assertEqual(self.client.get('/api/processing/chemical-mixers/', **viewer_headers).status_code, 403)
        self.assertEqual(self.client.delete(ENDPOINT, **self.headers).status_code, 405)
