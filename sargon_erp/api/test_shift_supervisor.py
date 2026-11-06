import importlib
import json

from django.apps import apps
from django.contrib.auth import get_user_model
from django.test import TestCase

from .auth import create_access_token
from .models import AccessGroup, GroupModuleAccess, Module, Permission, UserProfile
from .oil_processing import OIL_CONTAINER_PATHS, OIL_FINISHING_STEPS
from .oil_manufacturing import MANUFACTURING_STEPS
from .views import _is_admin, _user_access_map, _user_start_path


class ShiftSupervisorTests(TestCase):
    def setUp(self):
        self.group = AccessGroup.objects.get(name='Начальник смены')
        self.user = get_user_model().objects.create_user('shift-supervisor-test')
        UserProfile.objects.filter(user=self.user).update(group=self.group)
        self.headers = {'HTTP_AUTHORIZATION': f'Bearer {create_access_token(self.user)}'}

    def test_seeded_permissions_and_start_page(self):
        access = _user_access_map(self.user)
        read_only = {'used-oil-processing', 'production-workspace'}
        operations = {
            'boiler-loading', 'separator-loading', 'separator-output', 'chemical-mixer-loading', 'workshop-loading',
            'raw-diesel-tank-loading', 'raw-spindle-tank-loading', 'sorption-loading', 'finishing-mixer-loading',
            'finishing-filter-loading', 'finished-product-loading', 'sorbent-loading',
            'canister-loading', 'cap-loading', 'canister-output', 'cap-output', 'sorbent-cycle',
        }
        operations.update(MANUFACTURING_STEPS)
        self.assertEqual(set(access), read_only | operations)
        for code in read_only:
            self.assertEqual(set(access[code]), {'view'})
        for code in operations:
            self.assertEqual(set(access[code]), {'view', 'create'})
        self.assertEqual(self.group.start_module.code, 'production-workspace')
        self.assertFalse(_is_admin(self.user))
        response = self.client.get('/api/auth/me/', **self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['user']['start_path'], '/production')
        self.assertFalse(response.json()['user']['is_admin'])

    def test_production_views_and_operations_are_accessible(self):
        for path in (
            '/api/processing/sorbent-cycle/',
            '/api/processing/receiving-tanks/', '/api/processing/preheating-boilers/',
            '/api/processing/separators/', '/api/processing/chemical-mixers/',
            '/api/processing/workshops/', '/api/processing/raw-diesel-tanks/', '/api/processing/raw-spindle-tanks/',
            *(f'/api/processing/oil-containers/{path}/' for path in OIL_CONTAINER_PATHS),
            *(f'/api/processing/oil-movements/{step}/' for step in OIL_FINISHING_STEPS),
            *(f'/api/oil-production/operations/{step}/' for step in MANUFACTURING_STEPS),
        ):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path, **self.headers).status_code, 200)
        for path in (
            '/api/processing/sorbent-cycle/',
            '/api/processing/movements/tank-to-boiler/', '/api/processing/movements/boiler-to-separator/',
            '/api/processing/movements/separator-output/', '/api/processing/movements/separator-to-chemical-mixer/',
            '/api/processing/movements/chemical-mixer-to-workshop/',
            '/api/processing/movements/workshop-to-raw-diesel-tank/', '/api/processing/movements/workshop-to-raw-spindle-tank/',
            *(f'/api/processing/oil-movements/{step}/' for step in OIL_FINISHING_STEPS),
            *(f'/api/oil-production/operations/{step}/' for step in MANUFACTURING_STEPS),
        ):
            with self.subTest(path=path):
                response = self.client.post(path, data='{}', content_type='application/json', **self.headers)
                self.assertEqual(response.status_code, 400)

    def test_receiving_laboratory_warehouse_and_administration_are_forbidden(self):
        for path in (
            '/api/dashboard/overview/',
            '/api/raw-material/receipts/', '/api/laboratory/analyses/', '/api/access/users/',
            '/api/access/groups/', '/api/warehouse/overview/', '/api/warehouse/settings/warehouses/',
            '/api/processing/journal/',
        ):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path, **self.headers).status_code, 403)
        for path in (
            '/api/processing/receiving-tanks/', '/api/processing/oil-containers/sorption-systems/',
            '/api/processing/movements/1/compensate/',
        ):
            with self.subTest(path=path):
                response = self.client.post(path, data=json.dumps({'number': 7, 'capacity_liters': 1000}),
                                            content_type='application/json', **self.headers)
                self.assertEqual(response.status_code, 403)

    def test_reapplying_seed_preserves_custom_permissions_and_start(self):
        migration = importlib.import_module('api.migrations.0038_seed_shift_supervisor_group')
        access = GroupModuleAccess.objects.get(group=self.group, module__code='boiler-loading')
        access.permissions.set([Permission.objects.get(code='view')])
        self.group.start_module = Module.objects.get(code='boiler-loading')
        self.group.save(update_fields=['start_module'])
        migration.seed_shift_supervisor(apps, None)
        self.group.refresh_from_db()
        self.assertEqual(self.group.start_module.code, 'boiler-loading')
        self.assertEqual(set(access.permissions.values_list('code', flat=True)), {'view'})

    def test_dashboard_permission_is_dynamic_not_based_on_group_name(self):
        group = AccessGroup.objects.create(name='Тест обзора по разрешению')
        UserProfile.objects.filter(user=self.user).update(group=group)
        user = get_user_model().objects.get(pk=self.user.pk)
        self.assertEqual(self.client.get('/api/dashboard/overview/', **self.headers).status_code, 403)
        self.assertEqual(_user_start_path(user), '/no-access')
        access = GroupModuleAccess.objects.create(group=group, module=Module.objects.get(code='dashboard'))
        access.permissions.add(Permission.objects.get(code='view'))
        self.assertEqual(self.client.get('/api/dashboard/overview/', **self.headers).status_code, 200)
        self.assertEqual(_user_start_path(get_user_model().objects.get(pk=self.user.pk)), '/welcome')
        access.module.is_active = False
        access.module.save(update_fields=['is_active'])
        self.assertEqual(self.client.get('/api/dashboard/overview/', **self.headers).status_code, 403)
        self.assertEqual(_user_start_path(get_user_model().objects.get(pk=self.user.pk)), '/no-access')

    def test_group_without_view_or_membership_has_safe_start(self):
        UserProfile.objects.filter(user=self.user).update(group=None)
        self.assertEqual(_user_start_path(get_user_model().objects.get(pk=self.user.pk)), '/no-access')
        self.assertEqual(self.client.get('/api/dashboard/overview/', **self.headers).status_code, 403)
        self.assertEqual(self.client.get('/api/auth/me/', **self.headers).json()['user']['start_path'], '/no-access')

    def test_fallback_start_honors_implicit_view_and_group_setting(self):
        self.group.start_module = None
        self.group.save(update_fields=['start_module'])
        self.group.module_access.all().delete()
        module = Module.objects.get(code='oil-blending')
        GroupModuleAccess.objects.create(group=self.group, module=module)
        self.assertEqual(_user_start_path(get_user_model().objects.get(pk=self.user.pk)), '/oil-production/oil-blending')
        self.group.start_module = module
        self.group.save(update_fields=['start_module'])
        self.assertEqual(self.client.get('/api/auth/me/', **self.headers).json()['user']['start_path'], '/oil-production/oil-blending')

    def test_dashboard_admin_override_and_anonymous_denial(self):
        self.assertEqual(self.client.get('/api/dashboard/overview/').status_code, 401)
        for flag in ('is_staff', 'is_superuser'):
            admin = get_user_model().objects.create_user(f'dashboard-{flag}', **{flag: True})
            headers = {'HTTP_AUTHORIZATION': f'Bearer {create_access_token(admin)}'}
            self.assertEqual(self.client.get('/api/dashboard/overview/', **headers).status_code, 200)
            self.assertEqual(_user_start_path(admin), '/welcome')

    def test_access_migration_preserves_other_groups_and_configures_only_production(self):
        migration = importlib.import_module('api.migrations.0043_configure_shift_supervisor_access')
        other = AccessGroup.objects.create(name='Тест сохранения другой группы', start_module=Module.objects.get(code='suppliers'))
        suppliers = GroupModuleAccess.objects.create(group=other, module=other.start_module)
        suppliers.permissions.add(Permission.objects.get(code='view'))
        migration.configure_access(apps, None)
        other.refresh_from_db()
        self.assertEqual(other.start_module.code, 'suppliers')
        self.assertEqual(set(suppliers.permissions.values_list('code', flat=True)), {'view'})
        self.assertEqual(set(other.module_access.get(module__code='dashboard').permissions.values_list('code', flat=True)), {'view'})
        self.assertFalse(self.group.module_access.filter(module__code='dashboard').exists())
        migration.configure_access(apps, None)
        self.assertEqual(other.module_access.count(), 2)

    def test_workspace_permission_does_not_grant_forms_or_overview(self):
        group = AccessGroup.objects.create(name='Тест рабочего места', start_module=Module.objects.get(code='production-workspace'))
        access = GroupModuleAccess.objects.create(group=group, module=group.start_module)
        access.permissions.add(Permission.objects.get(code='view'))
        UserProfile.objects.filter(user=self.user).update(group=group)
        self.assertEqual(self.client.get('/api/auth/me/', **self.headers).json()['user']['start_path'], '/production')
        for path in ('/api/dashboard/overview/', '/api/processing/movements/tank-to-boiler/', '/api/oil-production/operations/oil-blending/'):
            response = self.client.post(path, data='{}', content_type='application/json', **self.headers) if 'tank-to-boiler' in path else self.client.get(path, **self.headers)
            self.assertEqual(response.status_code, 403)

    def test_workspace_seed_preserves_manual_settings_and_other_groups(self):
        migration = importlib.import_module('api.migrations.0044_seed_production_workspace')
        self.group.start_module = Module.objects.get(code='oil-blending')
        self.group.save(update_fields=['start_module'])
        before = {group.pk: group.module_access.count() for group in AccessGroup.objects.exclude(pk=self.group.pk)}
        migration.seed_workspace(apps, None)
        self.group.refresh_from_db()
        self.assertEqual(self.group.start_module.code, 'oil-blending')
        self.assertEqual(before, {group.pk: group.module_access.count() for group in AccessGroup.objects.exclude(pk=self.group.pk)})
        self.assertEqual(self.group.module_access.filter(module__code='production-workspace').count(), 1)
