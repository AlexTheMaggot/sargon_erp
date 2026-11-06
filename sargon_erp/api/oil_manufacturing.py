from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.models import ProtectedError, Sum
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from .models import (
    InventoryItem, MaterialMovement, OilGrade, OilManufacturingBatch, ProductionContainer,
    Warehouse, WarehouseBalance, WarehouseDocument, WarehouseDocumentLine, WarehouseMovement,
)
from .oil_processing import lock_oil_line


MANUFACTURING_STEPS = {
    'concentrate-loading': ('Приготовление концентрата', ProductionContainer.KIND_CONCENTRATE_REACTOR),
    'oil-blending': ('Загрузка блендингового смесителя', ProductionContainer.KIND_OIL_BLENDER),
    'oil-tank-loading': ('Перелив масла в продуктовый бак', ProductionContainer.KIND_FINISHED_OIL_TANK),
    'oil-filling': ('Розлив товарного масла', None),
}
MANUFACTURING_CONTAINERS = {
    'concentrate-reactors': ProductionContainer.KIND_CONCENTRATE_REACTOR,
    'oil-blenders': ProductionContainer.KIND_OIL_BLENDER,
    'finished-oil-tanks': ProductionContainer.KIND_FINISHED_OIL_TANK,
}


def _helpers():
    from . import views
    return views


def _identifier(value):
    if type(value) is not int or value <= 0:
        raise ValueError('Выберите все обязательные источники и оборудование.')
    return value


def _liters(value):
    result = _helpers()._volume_value(value)
    if result is None:
        raise ValueError('Укажите положительный объём с точностью до 0,001 л.')
    return result


def _serialize_batch(batch):
    return {
        'id': batch.pk, 'number': batch.number, 'equipment_id': batch.equipment_id,
        'equipment_name': batch.equipment.display_name, 'kind': batch.equipment.kind,
        'oil_grade_id': batch.oil_grade_id, 'grade_name': batch.grade_snapshot,
        'status': batch.status, 'status_label': batch.get_status_display(),
        'input_liters': str(batch.input_liters), 'output_liters': str(batch.output_liters),
        'polypropylene_quantity': str(batch.polypropylene_quantity),
        'created_at': batch.created_at.isoformat(),
        'completed_at': batch.completed_at.isoformat() if batch.completed_at else '',
        'created_by': batch.created_by.get_username() if batch.created_by else '',
    }


def _batches():
    return OilManufacturingBatch.objects.select_related('equipment', 'oil_grade', 'created_by')


def _container_rows(kind, user):
    return [_helpers()._serialize_container(item, user) for item in ProductionContainer.objects.filter(
        kind=kind, is_active=True,
    ).select_related('oil_grade')]


def _reference_data(step, user):
    result = {}
    if step in ('concentrate-loading', 'oil-blending'):
        result['base_tanks'] = _container_rows(ProductionContainer.KIND_FINISHED_SPINDLE_TANK, user)
        result['equipment'] = [item for item in _container_rows(MANUFACTURING_STEPS[step][1], user) if not item['active_batch']]
    if step == 'concentrate-loading':
        items = InventoryItem.objects.filter(
            production_material=InventoryItem.MATERIAL_POLYPROPYLENE, is_active=True,
            unit__is_active=True, category__is_active=True,
        ).select_related('unit', 'category').prefetch_related('permanent_warehouses')
        balances = {(row.warehouse_id, row.item_id): row.quantity for row in WarehouseBalance.objects.filter(item__in=items)}
        warehouses, materials = {}, []
        for item in items:
            if item.unit.symbol.lower() not in ('кг', 'kg'):
                continue
            for warehouse in item.permanent_warehouses.all():
                if warehouse.is_active:
                    warehouses[warehouse.pk] = {'id': warehouse.pk, 'name': warehouse.name}
                    materials.append({'id': item.pk, 'name': item.name, 'warehouse_id': warehouse.pk,
                                      'decimal_places': item.unit.decimal_places,
                                      'quantity': str(balances.get((warehouse.pk, item.pk), Decimal('0.00')))})
        result.update(warehouses=list(warehouses.values()), materials=materials)
    if step == 'oil-blending':
        result['concentrate_batches'] = [_serialize_batch(batch) for batch in _batches().filter(
            equipment__kind=ProductionContainer.KIND_CONCENTRATE_REACTOR,
            equipment__is_active=True, status=OilManufacturingBatch.STATUS_OPEN,
        )]
        result['grades'] = list(OilGrade.objects.filter(is_active=True).values('id', 'name'))
    if step in ('oil-tank-loading', 'oil-filling'):
        result['tanks'] = _container_rows(ProductionContainer.KIND_FINISHED_OIL_TANK, user)
    if step == 'oil-tank-loading':
        result['blender_batches'] = [_serialize_batch(batch) for batch in _batches().filter(
            equipment__kind=ProductionContainer.KIND_OIL_BLENDER, equipment__is_active=True, status=OilManufacturingBatch.STATUS_OPEN,
        )]
    return result


def _movement(kind, user, volume, source=None, destination=None, source_batch=None, destination_batch=None, grade=None):
    return MaterialMovement.objects.create(
        movement_number=_helpers()._movement_number(), movement_type=kind,
        source_container=source, destination_container=destination,
        source_oil_batch=source_batch, destination_oil_batch=destination_batch, oil_grade=grade,
        product_name=grade.name if grade else 'Концентрат' if source_batch else 'Веретенка',
        volume_liters=volume, created_by=user,
        source_snapshot=source.display_name if source else '',
        destination_snapshot=destination.display_name if destination else 'Розлив',
    )


def _remove_base(tank, volume, user, destination, batch):
    if tank.kind != ProductionContainer.KIND_FINISHED_SPINDLE_TANK or not tank.is_active:
        raise ValueError('Выберите активный бак готовой веретенки.')
    if volume > tank.current_volume_liters:
        raise ValueError('В баке готовой веретенки недостаточно масла.')
    kind = MaterialMovement.TYPE_SPINDLE_TO_CONCENTRATE if destination.kind == ProductionContainer.KIND_CONCENTRATE_REACTOR else MaterialMovement.TYPE_SPINDLE_TO_BLENDER
    movement = _movement(kind, user, volume, tank, destination, destination_batch=batch)
    movement.source_volume_before = tank.current_volume_liters
    tank.current_volume_liters -= volume
    movement.source_volume_after = tank.current_volume_liters
    movement.save(update_fields=['source_volume_before', 'source_volume_after'])
    tank.save(update_fields=['current_volume_liters', 'updated_at'])


def _issue_polypropylene(body, user):
    helpers = _helpers()
    warehouse = Warehouse.objects.filter(pk=_identifier(body.get('warehouse_id')), is_active=True).first()
    item = InventoryItem.objects.select_for_update(of=('self',)).select_related('unit', 'category').filter(pk=_identifier(body.get('item_id'))).first()
    if warehouse is None or item is None or not item.is_active or not item.category.is_active or not item.unit.is_active:
        raise ValueError('Выберите активный склад и полипропилен.')
    if item.production_material != InventoryItem.MATERIAL_POLYPROPYLENE or item.unit.symbol.lower() not in ('кг', 'kg') or not item.permanent_warehouses.filter(pk=warehouse.pk).exists():
        raise ValueError('Полипропилен должен храниться на выбранном складе и учитываться в кг.')
    raw_quantity = helpers._decimal_value(body.get('polypropylene_quantity'))
    if raw_quantity is None or not raw_quantity.is_finite() or not 0 < raw_quantity < Decimal('10000000000000000'):
        raise ValueError('Укажите положительное количество полипропилена с точностью единицы измерения.')
    quantity = helpers._warehouse_quantity(raw_quantity, item.unit)
    if quantity is None:
        raise ValueError('Укажите положительное количество полипропилена с точностью единицы измерения.')
    balance = helpers._locked_warehouse_balance(warehouse, item)
    unit_cost = helpers._remove_from_warehouse_balance(balance, quantity)
    if quantity * unit_cost >= Decimal('1000000000000000000'):
        raise ValueError('Стоимость загрузки превышает допустимый размер складского движения.')
    now = timezone.now()
    document = WarehouseDocument.objects.create(
        number=helpers._next_warehouse_document_number(WarehouseDocument.TYPE_ISSUE, now),
        document_type=WarehouseDocument.TYPE_ISSUE, status=WarehouseDocument.STATUS_POSTED,
        document_date=now, source_warehouse=warehouse, purpose='Приготовление концентрата',
        production_target=WarehouseDocument.TARGET_OIL_CONCENTRATE,
        idempotency_key=f'concentrate:{helpers._movement_number()}',
        created_by=user, posted_by=user, posted_at=now,
    )
    WarehouseDocumentLine.objects.create(document=document, item=item, quantity=quantity)
    helpers._create_warehouse_movement(document, warehouse, item, WarehouseMovement.TYPE_ISSUE, -quantity, unit_cost, user)
    return document, quantity


def _locked_batch(batch_id, kind):
    batch = OilManufacturingBatch.objects.select_for_update(of=('self',)).select_related('equipment', 'oil_grade').filter(pk=batch_id).first()
    if batch is None or batch.equipment.kind != kind or batch.status != OilManufacturingBatch.STATUS_OPEN or not batch.equipment.is_active:
        raise ValueError('Выберите открытую партию активного оборудования.')
    return batch


def _check_measured_output(batch, volume):
    if batch.output_liters + volume > batch.equipment.capacity_liters:
        raise ValueError('Суммарный измеренный выход партии превышает вместимость оборудования.')


def _create_batch(step, body, user, key):
    equipment_id = _identifier(body.get('equipment_id'))
    tank_id = _identifier(body.get('source_tank_id'))
    base_volume = _liters(body.get('base_liters'))
    containers = {row.pk: row for row in ProductionContainer.objects.select_for_update().filter(pk__in=[equipment_id, tank_id]).order_by('pk')}
    equipment, tank = containers.get(equipment_id), containers.get(tank_id)
    if equipment is None or equipment.kind != MANUFACTURING_STEPS[step][1] or not equipment.is_active or tank is None:
        raise ValueError('Выберите активное оборудование и бак готовой веретенки.')
    if OilManufacturingBatch.objects.filter(equipment=equipment, status=OilManufacturingBatch.STATUS_OPEN).exists():
        raise ValueError('В оборудовании уже открыта партия. Завершите её после полного опорожнения.')
    grade, source_batch, concentrate_volume = None, None, Decimal('0.000')
    if step == 'oil-blending':
        grade = OilGrade.objects.filter(pk=_identifier(body.get('oil_grade_id')), is_active=True).first()
        if grade is None:
            raise ValueError('Выберите активную марку масла.')
        source_batch = _locked_batch(_identifier(body.get('concentrate_batch_id')), ProductionContainer.KIND_CONCENTRATE_REACTOR)
        concentrate_volume = _liters(body.get('concentrate_liters'))
        _check_measured_output(source_batch, concentrate_volume)
    if base_volume + concentrate_volume > equipment.capacity_liters:
        raise ValueError('Загрузка жидких компонентов превышает вместимость оборудования.')
    batch = OilManufacturingBatch.objects.create(
        number=f'BATCH-{_helpers()._movement_number()}', equipment=equipment,
        oil_grade=grade, grade_snapshot=grade.name if grade else '',
        input_liters=base_volume + concentrate_volume, created_by=user,
        idempotency_key=key, request_snapshot={'step': step, 'body': body},
    )
    _remove_base(tank, base_volume, user, equipment, batch)
    if source_batch:
        _movement(MaterialMovement.TYPE_CONCENTRATE_TO_BLENDER, user, concentrate_volume,
                  source_batch.equipment, equipment, source_batch, batch)
        source_batch.output_liters += concentrate_volume
        source_batch.save(update_fields=['output_liters'])
    else:
        document, quantity = _issue_polypropylene(body, user)
        batch.material_document, batch.polypropylene_quantity = document, quantity
        batch.save(update_fields=['material_document', 'polypropylene_quantity'])
    return batch


def _transfer_or_fill(step, body, user, key):
    volume = _liters(body.get('volume_liters'))
    tank_id = _identifier(body.get('tank_id'))
    tank = ProductionContainer.objects.select_for_update(of=('self',)).select_related('oil_grade').filter(pk=tank_id).first()
    if tank is None or tank.kind != ProductionContainer.KIND_FINISHED_OIL_TANK or not tank.is_active:
        raise ValueError('Выберите активный бак товарного масла.')
    if step == 'oil-filling':
        if tank.current_volume_liters < volume:
            raise ValueError('В продуктовом баке недостаточно масла.')
        movement = _movement(MaterialMovement.TYPE_OIL_FILLING, user, volume, source=tank, grade=tank.oil_grade)
        movement.source_volume_before = tank.current_volume_liters
        tank.current_volume_liters -= volume
        movement.source_volume_after = tank.current_volume_liters
    else:
        batch = _locked_batch(_identifier(body.get('batch_id')), ProductionContainer.KIND_OIL_BLENDER)
        if batch.oil_grade_id != tank.oil_grade_id:
            raise ValueError('Марка масла партии не соответствует марке продуктового бака.')
        _check_measured_output(batch, volume)
        if tank.current_volume_liters + volume > tank.capacity_liters:
            raise ValueError('В продуктовом баке недостаточно свободного места.')
        movement = _movement(MaterialMovement.TYPE_BLENDER_TO_OIL_TANK, user, volume,
                             batch.equipment, tank, source_batch=batch, grade=batch.oil_grade)
        movement.destination_volume_before = tank.current_volume_liters
        tank.current_volume_liters += volume
        movement.destination_volume_after = tank.current_volume_liters
        batch.output_liters += volume
        batch.save(update_fields=['output_liters'])
    tank.save(update_fields=['current_volume_liters', 'updated_at'])
    movement.idempotency_key = key
    movement.reason = json_snapshot(step, body)
    movement.save(update_fields=['source_volume_before', 'source_volume_after', 'destination_volume_before', 'destination_volume_after', 'idempotency_key', 'reason'])
    return movement


def json_snapshot(step, body):
    import json
    return json.dumps({'step': step, 'body': body}, sort_keys=True, ensure_ascii=False)


@csrf_exempt
def manufacturing_view(request, step):
    helpers = _helpers()
    if step not in MANUFACTURING_STEPS:
        return JsonResponse({'detail': 'Неизвестная производственная операция.'}, status=404)
    user, error = helpers._require_processing_permission(request, step)
    if error:
        return error
    if request.method == 'GET':
        kind = MANUFACTURING_STEPS[step][1]
        is_batch = step in ('concentrate-loading', 'oil-blending')
        rows = _batches().filter(equipment__kind=kind) if is_batch else MaterialMovement.objects.filter(
            movement_type=MaterialMovement.TYPE_OIL_FILLING if step == 'oil-filling' else MaterialMovement.TYPE_BLENDER_TO_OIL_TANK,
        ).select_related('created_by')
        serializer = _serialize_batch if is_batch else helpers._serialize_movement
        return JsonResponse({**_reference_data(step, user), 'items': [serializer(row) for row in rows.order_by('-created_at', '-id')]})
    if request.method != 'POST':
        return helpers._method_not_allowed()
    body = helpers._json_body(request)
    if not isinstance(body, dict):
        return helpers._invalid_json_body()
    body = dict(body)
    key = body.pop('idempotency_key', None)
    if not isinstance(key, str) or not key.strip() or len(key) > 80:
        return JsonResponse({'detail': 'Valid idempotency key is required.'}, status=400)
    try:
        with transaction.atomic():
            lock_oil_line()
            batch = _batches().filter(idempotency_key=key).first()
            movement = MaterialMovement.objects.filter(idempotency_key=key).select_related('created_by').first()
            if batch or movement:
                same = (batch.created_by_id == user.pk and batch.request_snapshot == {'step': step, 'body': body}) if batch else (
                    movement.created_by_id == user.pk and movement.reason == json_snapshot(step, body)
                )
                if not same:
                    return JsonResponse({'detail': 'Ключ повторного запроса уже использован для другой операции.'}, status=409)
                return JsonResponse(_serialize_batch(batch) if batch else helpers._serialize_movement(movement))
            is_batch = step in ('concentrate-loading', 'oil-blending')
            result = _create_batch(step, body, user, key) if is_batch else _transfer_or_fill(step, body, user, key)
            helpers._audit_operation('oil_production_created', 'oil_batch' if is_batch else 'material_movement', result.pk, user, {'operation': step})
            return JsonResponse(_serialize_batch(result) if is_batch else helpers._serialize_movement(result), status=201)
    except (ValueError, ArithmeticError) as exc:
        return JsonResponse({'detail': str(exc)}, status=400)
    except IntegrityError:
        return JsonResponse({'detail': 'Не удалось провести операцию. Обновите данные и повторите запрос.'}, status=409)


@csrf_exempt
def batch_action_view(request, batch_id, action):
    helpers = _helpers()
    user, error = helpers._require_auth(request)
    if error:
        return error
    if request.method != 'POST':
        return helpers._method_not_allowed()
    with transaction.atomic():
        lock_oil_line()
        batch = _batches().select_for_update(of=('self',)).filter(pk=batch_id).first()
        if batch is None:
            return JsonResponse({'detail': 'Партия не найдена.'}, status=404)
        code = 'concentrate-loading' if batch.equipment.kind == ProductionContainer.KIND_CONCENTRATE_REACTOR else 'oil-blending'
        if not (helpers._is_admin(user) or helpers._has_permission(user, code, 'create')):
            return helpers._permission_denied()
        if action == 'cancel':
            if not helpers._is_admin(user):
                return helpers._permission_denied()
            body = helpers._json_body(request)
            reason = body.get('reason') if isinstance(body, dict) else None
            if not isinstance(reason, str) or not reason.strip() or len(reason) > 1000:
                return JsonResponse({'detail': 'Укажите причину отмены до 1000 символов.'}, status=400)
            try:
                with transaction.atomic():
                    _cancel_batch(batch, user, reason.strip())
            except ValueError as exc:
                return JsonResponse({'detail': str(exc)}, status=400)
            return JsonResponse(_serialize_batch(batch))
        if action != 'complete':
            return helpers._method_not_allowed()
        if batch.status != OilManufacturingBatch.STATUS_OPEN:
            return JsonResponse({'detail': 'Партия уже закрыта.'}, status=423)
        body = helpers._json_body(request)
        if not isinstance(body, dict) or body.get('equipment_empty') is not True or batch.output_liters <= 0:
            return JsonResponse({'detail': 'Подтвердите полное опорожнение оборудования после фактического перелива.'}, status=400)
        batch.status, batch.completed_at = OilManufacturingBatch.STATUS_COMPLETED, timezone.now()
        batch.save(update_fields=['status', 'completed_at'])
        helpers._audit_operation('oil_batch_completed', 'oil_batch', batch.pk, user)
        return JsonResponse(_serialize_batch(batch))


@csrf_exempt
def manufacturing_containers_view(request, path):
    kind = MANUFACTURING_CONTAINERS.get(path)
    if kind is None:
        return JsonResponse({'detail': 'Production container not found.'}, status=404)
    return _helpers()._production_containers_view(request, kind)


@csrf_exempt
def grades_view(request, grade_id=None):
    helpers = _helpers()
    user, error = helpers._require_processing_permission(request, 'used-oil-processing', 'view')
    if error:
        return error
    if request.method == 'GET':
        if grade_id:
            grade = OilGrade.objects.filter(pk=grade_id).values('id', 'name', 'is_active').first()
            return JsonResponse(grade) if grade else JsonResponse({'detail': 'Марка масла не найдена.'}, status=404)
        return JsonResponse({'items': list(OilGrade.objects.values('id', 'name', 'is_active'))})
    if not helpers._is_admin(user):
        return helpers._permission_denied()
    if request.method not in ('POST', 'PATCH', 'DELETE'):
        return helpers._method_not_allowed()
    if (grade_id is None and request.method != 'POST') or (grade_id is not None and request.method == 'POST'):
        return helpers._method_not_allowed()
    try:
        with transaction.atomic():
            lock_oil_line()
            grade = OilGrade.objects.filter(pk=grade_id).first() if grade_id else None
            if grade_id and grade is None:
                return JsonResponse({'detail': 'Марка масла не найдена.'}, status=404)
            if request.method == 'DELETE':
                if grade is None:
                    return helpers._method_not_allowed()
                grade.delete()
                return JsonResponse({'deleted': True})
            body = helpers._json_body(request)
            if not isinstance(body, dict):
                return helpers._invalid_json_body()
            name = body.get('name', grade.name if grade else '')
            active = body.get('is_active', grade.is_active if grade else True)
            if not isinstance(name, str) or not 1 <= len(name.strip()) <= 120 or type(active) is not bool:
                raise ValueError('Укажите название марки до 120 символов и корректную активность.')
            if grade and not active and (grade.containers.filter(current_volume_liters__gt=0).exists() or grade.batches.filter(status='open').exists()):
                raise ValueError('Нельзя отключить марку с остатком или открытой производственной партией.')
            if grade is None:
                grade = OilGrade()
            grade.name, grade.is_active = name.strip(), active
            grade.save()
            return JsonResponse({'id': grade.pk, 'name': grade.name, 'is_active': grade.is_active}, status=201 if request.method == 'POST' else 200)
    except ProtectedError:
        return JsonResponse({'detail': 'Марка используется в производстве или баках и не может быть удалена.'}, status=400)
    except IntegrityError:
        return JsonResponse({'detail': 'Марка масла с таким названием уже существует.'}, status=409)
    except ValueError as exc:
        return JsonResponse({'detail': str(exc)}, status=400)


def _reverse_record(movement, user, reason):
    result = MaterialMovement.objects.create(
        movement_number=_helpers()._movement_number(), movement_type=MaterialMovement.TYPE_COMPENSATION,
        source_container=movement.destination_container, destination_container=movement.source_container,
        source_oil_batch=movement.destination_oil_batch, destination_oil_batch=movement.source_oil_batch,
        oil_grade=movement.oil_grade, product_name=movement.product_name, volume_liters=movement.volume_liters,
        created_by=user, compensates=movement, reason=reason,
        source_snapshot=movement.destination_snapshot, destination_snapshot=movement.source_snapshot,
    )
    movement.is_compensated = True
    movement.save(update_fields=['is_compensated'])
    _helpers()._audit_operation('movement_compensated', 'material_movement', movement.pk, user, {
        'movement_number': movement.movement_number, 'compensation_number': result.movement_number, 'reason': reason,
    })
    return result


def compensate_manufacturing_movement(movement, user, reason):
    if movement.movement_type not in (MaterialMovement.TYPE_BLENDER_TO_OIL_TANK, MaterialMovement.TYPE_OIL_FILLING):
        return None, 'Отменяйте загрузки через производственную партию, пока из неё не было переливов.'
    tank_id = movement.destination_container_id if movement.movement_type == MaterialMovement.TYPE_BLENDER_TO_OIL_TANK else movement.source_container_id
    tank = ProductionContainer.objects.select_for_update().filter(pk=tank_id).first()
    if tank is None or not tank.is_active or tank.oil_grade_id != movement.oil_grade_id:
        return None, 'Бак отключён или его марка изменилась. Обратный перелив запрещён.'
    before = tank.current_volume_liters
    if movement.movement_type == MaterialMovement.TYPE_BLENDER_TO_OIL_TANK:
        batch = OilManufacturingBatch.objects.select_for_update().get(pk=movement.source_oil_batch_id)
        if batch.status != OilManufacturingBatch.STATUS_OPEN or tank.current_volume_liters < movement.volume_liters:
            return None, 'Нельзя отменить перелив: партия закрыта или в баке недостаточно масла.'
        tank.current_volume_liters -= movement.volume_liters
        batch.output_liters -= movement.volume_liters
        batch.save(update_fields=['output_liters'])
    else:
        if tank.current_volume_liters + movement.volume_liters > tank.capacity_liters:
            return None, 'Компенсация переполнит продуктовый бак.'
        tank.current_volume_liters += movement.volume_liters
    tank.save(update_fields=['current_volume_liters', 'updated_at'])
    result = _reverse_record(movement, user, reason)
    if movement.movement_type == MaterialMovement.TYPE_BLENDER_TO_OIL_TANK:
        result.source_volume_before, result.source_volume_after = before, tank.current_volume_liters
    else:
        result.destination_volume_before, result.destination_volume_after = before, tank.current_volume_liters
    result.save(update_fields=['source_volume_before', 'source_volume_after', 'destination_volume_before', 'destination_volume_after'])
    return result, None


def _cancel_batch(batch, user, reason):
    if batch.status != OilManufacturingBatch.STATUS_OPEN or batch.output_liters > 0:
        raise ValueError('Отменить можно только открытую партию без фактических переливов.')
    for movement in batch.incoming_movements.filter(is_compensated=False, compensates__isnull=True).select_related('source_container', 'source_oil_batch', 'oil_grade').order_by('pk'):
        if movement.source_oil_batch_id:
            source_batch = OilManufacturingBatch.objects.select_for_update().get(pk=movement.source_oil_batch_id)
            if source_batch.status != OilManufacturingBatch.STATUS_OPEN or source_batch.output_liters < movement.volume_liters:
                raise ValueError('Нельзя вернуть концентрат в уже закрытую исходную партию.')
            source_batch.output_liters -= movement.volume_liters
            source_batch.save(update_fields=['output_liters'])
        else:
            tank = ProductionContainer.objects.select_for_update().get(pk=movement.source_container_id)
            if not tank.is_active or tank.current_volume_liters + movement.volume_liters > tank.capacity_liters:
                raise ValueError('Возврат основы переполнит бак или бак отключён.')
            tank.current_volume_liters += movement.volume_liters
            tank.save(update_fields=['current_volume_liters', 'updated_at'])
        _reverse_record(movement, user, reason)
    if batch.material_document_id:
        document = WarehouseDocument.objects.select_for_update().get(pk=batch.material_document_id)
        if document.status != WarehouseDocument.STATUS_POSTED:
            raise ValueError('Связанный складской расход уже отменён.')
        for movement in document.movements.filter(movement_type=WarehouseMovement.TYPE_ISSUE).select_related('warehouse', 'item'):
            balance = _helpers()._locked_warehouse_balance(movement.warehouse, movement.item)
            _helpers()._add_to_warehouse_balance(balance, -movement.quantity_delta, movement.unit_cost)
            _helpers()._create_warehouse_movement(document, movement.warehouse, movement.item,
                                                WarehouseMovement.TYPE_REVERSAL, -movement.quantity_delta, movement.unit_cost, user)
        document.status, document.cancelled_at = WarehouseDocument.STATUS_CANCELLED, timezone.now()
        document.save(update_fields=['status', 'cancelled_at'])
    batch.status, batch.completed_at = OilManufacturingBatch.STATUS_CANCELLED, timezone.now()
    batch.save(update_fields=['status', 'completed_at'])
    _helpers()._audit_operation('oil_batch_cancelled', 'oil_batch', batch.pk, user, {'reason': reason})


def manufacturing_overview():
    helpers = _helpers()
    equipment = ProductionContainer.objects.filter(kind__in=ProductionContainer.OIL_BATCH_KINDS, is_active=True).order_by('number')
    active_batches = {batch.equipment_id: batch for batch in _batches().filter(status=OilManufacturingBatch.STATUS_OPEN)}
    vessels = {'concentrate_reactor': [], 'oil_blender': []}
    for container in equipment:
        batch = active_batches.get(container.pk)
        vessels[container.kind].append({
            'id': container.pk, 'name': container.display_name, 'capacity_liters': str(container.capacity_liters),
            'active_batch': _serialize_batch(batch) if batch else None,
        })
    tanks = helpers._overview_container_items(ProductionContainer.KIND_FINISHED_OIL_TANK, MaterialMovement.TYPE_BLENDER_TO_OIL_TANK)
    grades = {tank.pk: tank.oil_grade.name for tank in ProductionContainer.objects.filter(kind=ProductionContainer.KIND_FINISHED_OIL_TANK).select_related('oil_grade')}
    for tank in tanks:
        tank['grade_name'] = grades[tank['id']]
    polypropylene = WarehouseBalance.objects.filter(
        warehouse__is_active=True, item__is_active=True, item__production_material=InventoryItem.MATERIAL_POLYPROPYLENE,
    ).aggregate(total=Sum('quantity'))['total'] or Decimal('0.00')
    fillings = MaterialMovement.objects.filter(movement_type=MaterialMovement.TYPE_OIL_FILLING, is_compensated=False)
    return {
        **vessels, 'tanks': tanks, 'polypropylene_kg': str(polypropylene),
        'filled_today_liters': str(fillings.filter(moved_at__date=timezone.localdate()).aggregate(total=Sum('volume_liters'))['total'] or Decimal('0.000')),
        'filled_total_liters': str(fillings.aggregate(total=Sum('volume_liters'))['total'] or Decimal('0.000')),
    }
