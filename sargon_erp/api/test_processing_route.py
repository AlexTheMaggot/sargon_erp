import json
from importlib import import_module
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase

from .auth import create_access_token
from .models import AccessGroup, GroupModuleAccess, MaterialMovement, Module, Permission, ProductionContainer, UserProfile


class ProcessingRouteTests(TestCase):
    def setUp(self):
        admin = get_user_model().objects.create_superuser('route-admin')
        self.headers = {'HTTP_AUTHORIZATION': f'Bearer {create_access_token(admin)}'}
        self.containers = {}
        for kind in ('receiving_tank', 'preheating_boiler', 'processing_workshop', 'raw_diesel_tank',
                     'raw_spindle_tank', 'chemical_mixer', 'finishing_mixer', 'finishing_filter',
                     'finished_diesel_tank', 'finished_spindle_tank'):
            self.containers[kind] = ProductionContainer.objects.create(
                kind=kind, number=920, system_code=f'route-{kind}', capacity_liters=None if kind == 'finishing_filter' else 1000,
                current_volume_liters=100 if kind == 'receiving_tank' else 0,
            )

    def post(self, path, body):
        return self.client.post(f'/api/processing/{path}/', data=json.dumps({
            'volume_liters': '25.125', 'idempotency_key': str(uuid4()), **body,
        }), content_type='application/json', **self.headers)

    def oil_post(self, step, source, destination):
        return self.post(f'oil-movements/{step}', {
            'source_id': self.containers[source].pk, 'destination_id': self.containers[destination].pk,
        })

    def test_complete_reordered_chain_for_both_products(self):
        for product in ('diesel', 'spindle'):
            with self.subTest(product=product):
                for path, source_field, source_kind, destination_field, destination_kind in (
                    ('tank-to-boiler', 'source_tank_id', 'receiving_tank', 'destination_boiler_id', 'preheating_boiler'),
                    ('boiler-to-workshop', 'source_boiler_id', 'preheating_boiler', 'destination_workshop_id', 'processing_workshop'),
                ):
                    response = self.post(f'movements/{path}', {
                        source_field: self.containers[source_kind].pk,
                        destination_field: self.containers[destination_kind].pk,
                    })
                    self.assertEqual(response.status_code, 201, response.content)
                loading_id = response.json()['id']
                reactor_id = self.containers['processing_workshop'].pk
                for number in range(1, 2 if product == 'diesel' else 3):
                    opened = self.post('receiver-runs', {
                        'reactor_id': reactor_id, 'number': number, 'loading_id': loading_id, 'action': 'open',
                    })
                    self.assertEqual(opened.status_code, 201, opened.content)
                    run_id = opened.json()['id']
                    closed = self.post('receiver-runs', {
                        'reactor_id': reactor_id, 'number': number, 'run_id': run_id, 'action': 'close',
                    })
                    self.assertEqual(closed.status_code, 200, closed.content)
                transfer = self.post(f'movements/workshop-to-raw-{product}-tank', {
                    'receiver_run_id': run_id, 'destination_tank_id': self.containers[f'raw_{product}_tank'].pk,
                })
                self.assertEqual(transfer.status_code, 201, transfer.content)
                for step, source, destination in (
                    ('chemical-mixer-loading', f'raw_{product}_tank', 'chemical_mixer'),
                    ('finishing-mixer-loading', 'chemical_mixer', 'finishing_mixer'),
                    ('finished-product-loading', 'finishing_mixer', f'finished_{product}_tank'),
                ):
                    response = self.oil_post(step, source, destination)
                    self.assertEqual(response.status_code, 201, response.content)
                    self.assertEqual(response.json()['oil_product'], product)
        for kind, container in self.containers.items():
            container.refresh_from_db()
            expected = '49.750' if kind == 'receiving_tank' else '25.125' if kind.startswith('finished_') else '0.000'
            self.assertEqual(str(container.current_volume_liters), expected, kind)
        self.assertEqual(MaterialMovement.objects.count(), 12)

    def test_previous_routes_cannot_bypass_new_stages(self):
        for path in ('boiler-to-chemical-mixer', 'chemical-mixer-to-workshop'):
            self.assertEqual(self.post(f'movements/{path}', {}).status_code, 404)
        self.assertEqual(self.oil_post('finishing-mixer-loading', 'raw_diesel_tank', 'finishing_mixer').status_code, 400)
        self.assertEqual(self.oil_post('chemical-mixer-loading', 'preheating_boiler', 'chemical_mixer').status_code, 400)
        self.assertFalse(MaterialMovement.objects.exists())

    def test_each_loading_module_exposes_only_its_reference_data(self):
        operator = get_user_model().objects.create_user('route-operator')
        group = AccessGroup.objects.create(name='Route isolated operator')
        UserProfile.objects.update_or_create(user=operator, defaults={'group': group})
        self.headers = {'HTTP_AUTHORIZATION': f'Bearer {create_access_token(operator)}'}
        access = GroupModuleAccess.objects.create(group=group, module=Module.objects.get(code='chemical-mixer-loading'))
        access.permissions.add(Permission.objects.get(code='view'))
        for path in ('chemical-mixers', 'raw-diesel-tanks', 'raw-spindle-tanks'):
            self.assertEqual(self.client.get(f'/api/processing/{path}/', **self.headers).status_code, 200)
        for path in ('preheating-boilers', 'workshops', 'oil-containers/finishing-mixers'):
            self.assertEqual(self.client.get(f'/api/processing/{path}/', **self.headers).status_code, 403)
        self.assertEqual(self.oil_post('chemical-mixer-loading', 'raw_diesel_tank', 'chemical_mixer').status_code, 403)
        access.delete()
        access = GroupModuleAccess.objects.create(group=group, module=Module.objects.get(code='finishing-mixer-loading'))
        access.permissions.add(Permission.objects.get(code='view'))
        for path in ('chemical-mixers', 'oil-containers/finishing-mixers'):
            self.assertEqual(self.client.get(f'/api/processing/{path}/', **self.headers).status_code, 200)
        for path in ('raw-diesel-tanks', 'raw-spindle-tanks', 'preheating-boilers', 'workshops'):
            self.assertEqual(self.client.get(f'/api/processing/{path}/', **self.headers).status_code, 403)

    def test_chemical_mixer_requires_product_in_database(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            ProductionContainer.objects.filter(pk=self.containers['chemical_mixer'].pk).update(current_volume_liters=1)

    def test_legacy_movement_cannot_reintroduce_unclassified_oil(self):
        movement = MaterialMovement.objects.create(
            movement_number='LEGACY-ROUTE', movement_type='chemical_mixer_to_workshop',
            source_container=self.containers['chemical_mixer'], destination_container=self.containers['processing_workshop'],
            volume_liters=1, source_snapshot='Сохранённый источник', destination_snapshot='Сохранённый получатель',
        )
        response = self.post(f'movements/{movement.pk}/compensate', {'reason': 'Проверка старого маршрута'})
        self.assertEqual(response.status_code, 400)
        movement.refresh_from_db()
        self.assertFalse(movement.is_compensated)
        self.assertEqual(movement.source_snapshot, 'Сохранённый источник')
        self.assertEqual(MaterialMovement.objects.count(), 1)


class ProcessingRouteMigrationTests(TransactionTestCase):
    def setUp(self):
        executor = MigrationExecutor(connection)
        executor.migrate([('api', '0049_remove_separator_schema')])
        self.old_apps = executor.loader.project_state([('api', '0049_remove_separator_schema')]).apps

    def tearDown(self):
        self.old_apps.get_model('api', 'ProductionContainer').objects.filter(kind='chemical_mixer').update(current_volume_liters=0)
        MigrationExecutor(connection).migrate([('api', '0059_chemical_mixer_reagents')])
        super().tearDown()

    def test_nonempty_legacy_mixers_block_migration_without_changing_balances(self):
        container = self.old_apps.get_model('api', 'ProductionContainer').objects.create(
            kind='chemical_mixer', number=921, system_code='legacy-full-mixer', capacity_liters=100, current_volume_liters=10,
        )
        with self.assertRaisesMessage(RuntimeError, 'Empty chemical mixers'):
            MigrationExecutor(connection).migrate([('api', '0050_chemical_mixer_after_raw_products')])
        container.refresh_from_db()
        self.assertEqual(container.current_volume_liters, 10)
        self.assertEqual(container.oil_product, '')

    def test_migration_preserves_history_balances_access_and_custom_guides(self):
        movement = self.old_apps.get_model('api', 'MaterialMovement').objects.create(
            movement_number='ROUTE-HISTORY', movement_type='boiler_to_chemical_mixer', volume_liters=1,
            source_snapshot='Прежний котёл', destination_snapshot='Прежний миксер',
        )
        group = self.old_apps.get_model('api', 'AccessGroup').objects.create(name='Saved route group')
        module, _ = self.old_apps.get_model('api', 'Module').objects.get_or_create(
            code='chemical-mixer-loading', defaults={'name': 'Загрузка химического миксера'},
        )
        access = self.old_apps.get_model('api', 'GroupModuleAccess').objects.create(group=group, module=module)
        seed = import_module('api.migrations.0031_seed_knowledge_base')
        previous = import_module('api.migrations.0048_remove_separator')
        next_migration = import_module('api.migrations.0051_refresh_processing_route_guides')
        article_model = self.old_apps.get_model('api', 'KnowledgeArticle')
        expected = []
        for category, title, summary, content in seed.ARTICLES:
            title, summary, content = previous.updated_guide(title, summary, content)
            updated = next_migration.updated_content(content)
            if updated == content:
                continue
            section, _ = self.old_apps.get_model('api', 'KnowledgeCategory').objects.get_or_create(name=category)
            article = article_model.objects.create(category=section, title=title, summary=summary, content=content)
            if title == 'Как устроена система SHENOLL':
                article.content = 'Инструкция изменена пользователем.'
                article.save(update_fields=['content'])
                updated = article.content
            expected.append((article.pk, updated))
        MigrationExecutor(connection).migrate([('api', '0051_refresh_processing_route_guides')])
        movement.refresh_from_db()
        self.assertEqual(movement.movement_type, 'boiler_to_chemical_mixer')
        self.assertEqual(movement.source_snapshot, 'Прежний котёл')
        self.assertTrue(GroupModuleAccess.objects.filter(pk=access.pk).exists())
        for article_id, content in expected:
            self.assertEqual(article_model.objects.get(pk=article_id).content, content)
