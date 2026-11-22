from importlib import import_module

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class RemoveSeparatorMigrationTests(TransactionTestCase):
    def setUp(self):
        executor = MigrationExecutor(connection)
        executor.migrate([('api', '0047_remove_sorbent_schema')])
        self.old_apps = executor.loader.project_state([('api', '0047_remove_sorbent_schema')]).apps

    def tearDown(self):
        self.model('ProductionContainer').objects.filter(kind='chemical_mixer').update(current_volume_liters=0)
        MigrationExecutor(connection).migrate([('api', '0051_refresh_processing_route_guides')])
        super().tearDown()

    def model(self, name):
        return self.old_apps.get_model('api', name)

    def test_cleanup_removes_only_retired_equipment_history_and_permissions(self):
        container = self.model('ProductionContainer')
        separator = container.objects.create(kind='separator', number=990, system_code='removed-separator', capacity_liters=100, current_volume_liters=10)
        boiler = container.objects.create(kind='preheating_boiler', number=990, system_code='kept-boiler', capacity_liters=1000, current_volume_liters=200)
        mixer = container.objects.create(kind='chemical_mixer', number=990, system_code='kept-mixer', capacity_liters=1000, current_volume_liters=20)
        removed = []
        movement = self.model('MaterialMovement')
        for number, kind, source, destination in (
            ('OLD-LOAD', 'boiler_to_separator', boiler, separator),
            ('OLD-MIXER', 'separator_to_chemical_mixer', separator, mixer),
            ('OLD-WATER', 'separator_output', separator, None),
        ):
            removed.append(movement.objects.create(movement_number=number, movement_type=kind, source_container=source, destination_container=destination, volume_liters=1))
        movement.objects.create(movement_number='OLD-REVERSE', movement_type='compensation', compensates=removed[0], volume_liters=1)
        kept = movement.objects.create(movement_number='KEPT', movement_type='tank_to_boiler', volume_liters=1)
        audit = self.model('OperationAuditLog')
        audit.objects.create(action='movement_created', object_type='material_movement', object_id=str(removed[0].pk))
        kept_audit = audit.objects.create(action='movement_created', object_type='material_movement', object_id=str(kept.pk))
        module = self.model('Module')
        retired_module, _ = module.objects.get_or_create(code='separator-loading', defaults={'name': 'Старая загрузка'})
        active_module, _ = module.objects.get_or_create(code='chemical-mixer-loading', defaults={'name': 'Загрузка миксера'})
        active_module.description = 'Движение очищенного масла из сепаратора в химический миксер.'
        active_module.save(update_fields=['description'])
        group = self.model('AccessGroup').objects.create(name='Тест удаления этапа', start_module=retired_module)
        self.model('GroupModuleAccess').objects.create(group=group, module=retired_module)
        access = self.model('GroupModuleAccess').objects.create(group=group, module=active_module)

        MigrationExecutor(connection).migrate([('api', '0049_remove_separator_schema')])

        from .models import AccessGroup, GroupModuleAccess, MaterialMovement, Module, OperationAuditLog, ProductionContainer
        self.assertFalse(ProductionContainer.objects.filter(kind='separator').exists())
        self.assertEqual(ProductionContainer.objects.get(pk=boiler.pk).current_volume_liters, 200)
        self.assertEqual(ProductionContainer.objects.get(pk=mixer.pk).current_volume_liters, 20)
        self.assertEqual(list(MaterialMovement.objects.values_list('pk', flat=True)), [kept.pk])
        self.assertEqual(list(OperationAuditLog.objects.values_list('pk', flat=True)), [kept_audit.pk])
        self.assertFalse(Module.objects.filter(code__in=('separator-loading', 'separator-output')).exists())
        self.assertIsNone(AccessGroup.objects.get(pk=group.pk).start_module_id)
        self.assertTrue(GroupModuleAccess.objects.filter(pk=access.pk).exists())
        self.assertIn('котла первичного прогрева', Module.objects.get(pk=active_module.pk).description)

    def test_standard_guides_are_updated_but_customized_content_is_preserved(self):
        seed = import_module('api.migrations.0031_seed_knowledge_base')
        migration = import_module('api.migrations.0048_remove_separator')
        article_model = self.model('KnowledgeArticle')
        article_model.objects.all().delete()
        expected = []
        for category, title, summary, content in seed.ARTICLES:
            updated = migration.updated_guide(title, summary, content)
            if updated == (title, summary, content):
                continue
            section, _ = self.model('KnowledgeCategory').objects.get_or_create(name=category)
            article = article_model.objects.create(category=section, title=title, summary=summary, content=content)
            if title == 'Как устроена система SHENOLL':
                article.content = 'Авторская инструкция пользователя.'
                article.save(update_fields=['content'])
                updated = title, summary, article.content
            expected.append((article.pk, updated))

        MigrationExecutor(connection).migrate([('api', '0049_remove_separator_schema')])

        from .models import KnowledgeArticle
        for article_id, values in expected:
            article = KnowledgeArticle.objects.get(pk=article_id)
            self.assertEqual((article.title, article.summary, article.content), values)
        self.assertTrue(KnowledgeArticle.objects.filter(title='Журнал производственных операций').exists())
