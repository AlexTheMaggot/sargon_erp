from importlib import import_module
from types import SimpleNamespace

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class RemoveSorbentMigrationTests(TransactionTestCase):
    def setUp(self):
        executor = MigrationExecutor(connection)
        executor.migrate([('api', '0045_update_laboratory_guide')])
        self.old_apps = executor.loader.project_state([
            ('api', '0045_update_laboratory_guide'), ('contenttypes', '0002_remove_content_type_name'),
        ]).apps

    def tearDown(self):
        MigrationExecutor(connection).migrate([('api', '0058_flow_through_finishing_filter')])
        super().tearDown()

    def test_cleanup_removes_only_retired_data_and_preserves_mixed_documents(self):
        def model(name):
            return self.old_apps.get_model('api', name)

        warehouse = model('Warehouse').objects.create(name='Склад проверки миграции')
        unit = model('UnitOfMeasure').objects.create(name='Тестовый килограмм', symbol='test-kg', decimal_places=2)
        category = model('InventoryCategory').objects.create(name='Материалы проверки миграции')
        removed = model('InventoryItem').objects.create(name='Сорбент теста', category=category, unit=unit, production_material='sorbent')
        kept = model('InventoryItem').objects.create(name='Гранулы теста', category=category, unit=unit, production_material='granules')
        removed.permanent_warehouses.add(warehouse)
        for item in (removed, kept):
            model('WarehouseBalance').objects.create(warehouse=warehouse, item=item, quantity=10, average_unit_cost=5)
        receipt = model('WarehouseDocument').objects.create(number='MIXED', document_type='receipt', status='posted', destination_warehouse=warehouse)
        for item in (removed, kept):
            model('WarehouseDocumentLine').objects.create(document=receipt, item=item, quantity=2, unit_price=5)
            model('WarehouseMovement').objects.create(document=receipt, warehouse=warehouse, item=item, movement_type='receipt', quantity_delta=2, unit_cost=5, total_value_delta=10)
        issue = model('WarehouseDocument').objects.create(
            number='OLD-ISSUE', document_type='issue', status='posted', source_warehouse=warehouse,
            production_target='sorption', idempotency_key='removed-issue',
        )
        model('WarehouseDocumentLine').objects.create(document=issue, item=removed, quantity=1)
        source = model('WarehouseMovement').objects.create(
            document=issue, warehouse=warehouse, item=removed, movement_type='issue', quantity_delta=-1, unit_cost=5, total_value_delta=-5,
        )
        system = model('ProductionContainer').objects.create(
            kind='sorption_system', number=801, system_code='removed-system', capacity_liters=100,
            current_volume_liters=10, oil_product='spindle',
        )
        mixer = model('ProductionContainer').objects.create(
            kind='finishing_mixer', number=801, system_code='kept-mixer', capacity_liters=100,
            current_volume_liters=5, oil_product='spindle',
        )
        cycle = model('SorbentMovement').objects.create(
            number='OLD-CYCLE', movement_type='tank_to_system', source_movement=source, system=system,
            quantity=1, system_snapshot='Система', item_snapshot='Сорбент', idempotency_key='old-cycle',
        )
        model('SorbentMovement').objects.create(
            number='OLD-CYCLE-REVERSE', movement_type='reversal', source_movement=source, system=system,
            quantity=1, reversal_of=cycle, system_snapshot='Система', item_snapshot='Сорбент', idempotency_key='old-cycle-reverse',
        )
        old_movement = model('MaterialMovement').objects.create(
            movement_number='OLD-OIL', movement_type='sorption_to_mixer', source_container=system,
            destination_container=mixer, volume_liters=5, is_compensated=True,
        )
        model('MaterialMovement').objects.create(
            movement_number='OLD-OIL-REVERSE', movement_type='compensation', compensates=old_movement,
            source_container=mixer, destination_container=system, volume_liters=5,
        )
        kept_movement = model('MaterialMovement').objects.create(movement_number='KEPT-OIL', movement_type='mixer_to_filter', volume_liters=5)
        removed_module, _ = model('Module').objects.get_or_create(code='sorbent-cycle', defaults={'name': 'Удаляемый модуль'})
        kept_module, _ = model('Module').objects.get_or_create(code='finishing-mixer-loading', defaults={'name': 'Финишный миксер'})
        group = model('AccessGroup').objects.create(name='Проверка удаления', start_module=removed_module)
        model('GroupModuleAccess').objects.create(group=group, module=removed_module)
        kept_access = model('GroupModuleAccess').objects.create(group=group, module=kept_module)
        model('OperationAuditLog').objects.create(action='sorbent_moved', object_type='sorbent_movement', object_id=str(cycle.pk))
        kept_audit = model('OperationAuditLog').objects.create(action='movement_created', object_type='material_movement', object_id=str(kept_movement.pk))

        MigrationExecutor(connection).migrate([('api', '0047_remove_sorbent_schema')])

        from .models import AccessGroup, GroupModuleAccess, InventoryItem, MaterialMovement, Module
        from .models import OperationAuditLog, ProductionContainer, WarehouseBalance, WarehouseDocument
        from .models import WarehouseDocumentLine, WarehouseMovement
        self.assertFalse(InventoryItem.objects.filter(pk=removed.pk).exists())
        self.assertFalse(WarehouseDocument.objects.filter(pk=issue.pk).exists())
        self.assertFalse(ProductionContainer.objects.filter(pk=system.pk).exists())
        self.assertFalse(Module.objects.filter(code__in=('sorbent-loading', 'sorbent-cycle', 'sorption-loading')).exists())
        self.assertEqual(set(WarehouseDocumentLine.objects.filter(document_id=receipt.pk).values_list('item_id', flat=True)), {kept.pk})
        self.assertEqual(WarehouseMovement.objects.filter(document_id=receipt.pk, item_id=kept.pk).count(), 1)
        balance = WarehouseBalance.objects.get(warehouse_id=warehouse.pk, item_id=kept.pk)
        self.assertEqual((balance.quantity, balance.average_unit_cost), (10, 5))
        self.assertEqual(ProductionContainer.objects.get(pk=mixer.pk).current_volume_liters, 5)
        self.assertEqual(list(MaterialMovement.objects.values_list('pk', flat=True)), [kept_movement.pk])
        self.assertIsNone(AccessGroup.objects.get(pk=group.pk).start_module_id)
        self.assertTrue(GroupModuleAccess.objects.filter(pk=kept_access.pk).exists())
        self.assertEqual(list(OperationAuditLog.objects.values_list('pk', flat=True)), [kept_audit.pk])
        self.assertNotIn('api_sorbentmovement', connection.introspection.table_names())

    def test_cleanup_is_idempotent_before_schema_removal(self):
        MigrationExecutor(connection).migrate([('api', '0046_remove_sorbent')])
        migration = import_module('api.migrations.0046_remove_sorbent')
        editor = SimpleNamespace(connection=connection)
        migration.remove_sorbent_data(self.old_apps, editor)
        migration.remove_sorbent_data(self.old_apps, editor)
        MigrationExecutor(connection).migrate([('api', '0047_remove_sorbent_schema')])
        self.assertNotIn('api_sorbentmovement', connection.introspection.table_names())
