from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from .models import InventoryItem, ProductionContainer, SorbentMovement, WarehouseDocument, WarehouseMovement
from .oil_processing import lock_oil_line


MODULE_SORBENT_CYCLE = 'sorbent-cycle'
STEPS = {
    SorbentMovement.TYPE_TO_SYSTEM: ('tank', 'system'),
    SorbentMovement.TYPE_TO_REGENERATION: ('system', 'regeneration'),
    SorbentMovement.TYPE_TO_TANK: ('regeneration', 'tank'),
}
ZERO = Decimal('0.00')


def _helpers():
    from . import views
    return views


def _sources():
    return WarehouseMovement.objects.filter(
        document__production_target=WarehouseDocument.TARGET_SORPTION,
        document__status=WarehouseDocument.STATUS_POSTED,
        movement_type=WarehouseMovement.TYPE_ISSUE, quantity_delta__lt=0,
        item__production_material=InventoryItem.MATERIAL_SORBENT,
    ).select_related('item__unit', 'document', 'warehouse').order_by('created_at', 'pk')


def _movements():
    return SorbentMovement.objects.select_related('source_movement__document', 'created_by', 'reversed_by')


def _balances(sources):
    result = {source.pk: {'tank': -source.quantity_delta, 'systems': {}} for source in sources}
    totals = SorbentMovement.objects.filter(
        source_movement_id__in=result, reversal_of__isnull=True, reversed_by__isnull=True,
    ).values('source_movement_id', 'system_id', 'movement_type').annotate(total=Sum('quantity'))
    for row in totals:
        balance = result[row['source_movement_id']]
        system = balance['systems'].setdefault(row['system_id'], {'system': ZERO, 'regeneration': ZERO})
        origin, destination = STEPS[row['movement_type']]
        for location, sign in ((origin, -1), (destination, 1)):
            if location == 'tank':
                balance['tank'] += sign * row['total']
            else:
                system[location] += sign * row['total']
    return result


def _serialize(row):
    return {
        'id': row.pk, 'number': row.number, 'movement_type': row.movement_type,
        'movement_label': row.get_movement_type_display(), 'quantity': str(row.quantity),
        'source_movement_id': row.source_movement_id, 'loading_number': row.source_movement.document.number,
        'system_id': row.system_id, 'system_name': row.system_snapshot, 'item_name': row.item_snapshot,
        'note': row.note, 'created_at': row.created_at.isoformat(),
        'created_by': row.created_by.get_username() if row.created_by else '',
        'reversal_of_id': row.reversal_of_id,
        'is_reversed': hasattr(row, 'reversed_by'),
    }


def _reference():
    sources = list(_sources())
    balances = _balances(sources)
    return {
        'sources': [{
            'id': source.pk, 'loading_number': source.document.number,
            'item_name': source.item.name, 'item_id': source.item_id,
            'decimal_places': source.item.unit.decimal_places,
            'tank_quantity': str(balances[source.pk]['tank']),
            'systems': [{
                'id': system_id, 'system_quantity': str(values['system']),
                'regeneration_quantity': str(values['regeneration']),
            } for system_id, values in balances[source.pk]['systems'].items()],
        } for source in sources],
        'systems': [{
            'id': system.pk, 'name': system.display_name, 'is_active': system.is_active,
        } for system in ProductionContainer.objects.filter(kind=ProductionContainer.KIND_SORPTION_SYSTEM)],
        'summary': sorbent_overview(sources, balances),
    }


def sorbent_overview(sources=None, balances=None):
    if sources is None:
        with transaction.atomic():
            lock_oil_line()
            return sorbent_overview(list(_sources()))
    balances = _balances(sources) if balances is None else balances
    tank, in_system, regeneration = ZERO, ZERO, ZERO
    for balance in balances.values():
        tank += balance['tank']
        in_system += sum((values['system'] for values in balance['systems'].values()), ZERO)
        regeneration += sum((values['regeneration'] for values in balance['systems'].values()), ZERO)
    return {
        'tank_kg': str(tank), 'in_system_kg': str(in_system), 'regeneration_kg': str(regeneration),
        'total_kg': str(tank + in_system + regeneration),
    }


def system_has_sorbent(system_id):
    sources = list(_sources().filter(sorbent_movements__system_id=system_id).distinct())
    return any(
        values.get('system', ZERO) > 0 or values.get('regeneration', ZERO) > 0
        for balance in _balances(sources).values()
        for candidate, values in balance['systems'].items() if candidate == system_id
    )


def loading_is_in_use(document_id):
    return SorbentMovement.objects.filter(
        source_movement__document_id=document_id, reversal_of__isnull=True, reversed_by__isnull=True,
    ).exists()


def _validated(body):
    if not isinstance(body, dict):
        raise ValueError('Некорректные данные движения сорбента.')
    for field in ('source_movement_id', 'system_id'):
        if type(body.get(field)) is not int or body[field] <= 0:
            raise ValueError('Выберите источник сорбента и сорбент-систему.')
    key, note = body.get('idempotency_key'), body.get('note', '')
    if not isinstance(key, str) or not key.strip() or len(key) > 80:
        raise ValueError('Необходим корректный ключ запроса загрузки.')
    if not isinstance(note, str) or len(note) > 1000:
        raise ValueError('Комментарий должен содержать не более 1000 символов.')
    quantity = _helpers()._decimal_value(body.get('quantity'))
    if quantity is None or not quantity.is_finite() or not ZERO < quantity < Decimal('10000000000000000') or quantity != quantity.quantize(Decimal('0.01')):
        raise ValueError('Укажите положительное количество сорбента с точностью до 0,01 кг.')
    return key.strip(), note.strip(), quantity.quantize(Decimal('0.01'))


def _replay(existing, user, step, source_id, system_id, quantity, note, reversal_of_id=None):
    if (existing.created_by_id != user.pk or existing.movement_type != step
            or existing.source_movement_id != source_id or existing.system_id != system_id
            or existing.quantity != quantity or existing.note != note or existing.reversal_of_id != reversal_of_id):
        return JsonResponse({'detail': 'Ключ повторного запроса уже использован для другой операции.'}, status=409)
    return JsonResponse(_serialize(existing))


def _check_balance(source, system, step, quantity, reverse=False):
    if source.item.unit.symbol.lower() not in ('kg', 'кг') or _helpers()._warehouse_quantity(quantity, source.item.unit) is None:
        raise ValueError('Количество сорбента должно соответствовать точности единицы измерения в кг.')
    if system.kind != ProductionContainer.KIND_SORPTION_SYSTEM:
        raise ValueError('Выберите источник сорбента и сорбент-систему.')
    origin, destination = STEPS[step]
    if reverse:
        origin, destination = destination, origin
    if destination == 'system' and not system.is_active:
        raise ValueError('Нельзя подать сорбент в неактивную систему.')
    balance = _balances([source])[source.pk]
    available = balance['tank'] if origin == 'tank' else balance['systems'].get(system.pk, {}).get(origin, ZERO)
    if quantity > available:
        raise ValueError('Недостаточно сорбента в выбранном месте хранения.')


@csrf_exempt
def sorbent_cycle_view(request):
    helpers = _helpers()
    if request.method not in ('GET', 'POST'):
        return helpers._method_not_allowed()
    user, error = helpers._require_processing_permission(request, MODULE_SORBENT_CYCLE)
    if error:
        return error
    if request.method == 'GET':
        with transaction.atomic():
            lock_oil_line()
            return JsonResponse({**_reference(), 'items': [_serialize(row) for row in _movements()]})
    body = helpers._json_body(request)
    try:
        key, note, quantity = _validated(body)
        step = body.get('movement_type')
        if not isinstance(step, str) or step not in STEPS:
            raise ValueError('Выберите этап движения сорбента.')
        with transaction.atomic():
            lock_oil_line()
            existing = _movements().filter(idempotency_key=key).first()
            if existing:
                return _replay(existing, user, step, body['source_movement_id'], body['system_id'], quantity, note)
            source = _sources().select_for_update(of=('self',)).filter(pk=body['source_movement_id']).first()
            system = ProductionContainer.objects.select_for_update().filter(pk=body['system_id']).first()
            if source is None or system is None:
                raise ValueError('Выберите источник сорбента и сорбент-систему.')
            _check_balance(source, system, step, quantity)
            row = SorbentMovement.objects.create(
                number=helpers._movement_number(), movement_type=step, source_movement=source,
                system=system, system_snapshot=system.display_name, item_snapshot=source.item.name,
                quantity=quantity, note=note, idempotency_key=key, created_by=user,
            )
            helpers._audit_operation('sorbent_moved', 'sorbent_movement', row.pk, user, {'quantity': str(quantity), 'step': step})
            return JsonResponse(_serialize(_movements().get(pk=row.pk)), status=201)
    except ValueError as exc:
        return JsonResponse({'detail': str(exc)}, status=400)


@csrf_exempt
def sorbent_reverse_view(request, movement_id):
    helpers = _helpers()
    user, error = helpers._require_admin(request)
    if error:
        return error
    if request.method != 'POST':
        return helpers._method_not_allowed()
    body = helpers._json_body(request)
    if not isinstance(body, dict):
        return helpers._invalid_json_body()
    key, reason = body.get('idempotency_key'), body.get('reason')
    if not isinstance(key, str) or not key.strip() or len(key) > 80:
        return JsonResponse({'detail': 'Необходим корректный ключ запроса загрузки.'}, status=400)
    if not isinstance(reason, str) or not reason.strip() or len(reason) > 1000:
        return JsonResponse({'detail': 'Укажите причину отмены до 1000 символов.'}, status=400)
    try:
        with transaction.atomic():
            lock_oil_line()
            original = _movements().select_for_update(of=('self',)).filter(pk=movement_id, reversal_of__isnull=True).first()
            if original is None:
                return JsonResponse({'detail': 'Движение сорбента не найдено.'}, status=404)
            existing = _movements().filter(idempotency_key=key.strip()).first()
            if existing:
                return _replay(existing, user, SorbentMovement.TYPE_REVERSAL, original.source_movement_id,
                               original.system_id, original.quantity, reason.strip(), original.pk)
            if hasattr(original, 'reversed_by'):
                return JsonResponse({'detail': 'Движение сорбента уже компенсировано.'}, status=423)
            source = _sources().select_for_update(of=('self',)).filter(pk=original.source_movement_id).first()
            if source is None:
                raise ValueError('Складская загрузка сорбента уже отменена.')
            system = ProductionContainer.objects.select_for_update().get(pk=original.system_id)
            _check_balance(source, system, original.movement_type, original.quantity, reverse=True)
            row = SorbentMovement.objects.create(
                number=helpers._movement_number(), movement_type=SorbentMovement.TYPE_REVERSAL,
                source_movement=source, system=system, quantity=original.quantity,
                system_snapshot=original.system_snapshot, item_snapshot=original.item_snapshot,
                note=reason.strip(), reversal_of=original, idempotency_key=key.strip(), created_by=user,
            )
            helpers._audit_operation('sorbent_reversed', 'sorbent_movement', row.pk, user, {'reason': reason.strip()})
            return JsonResponse(_serialize(_movements().get(pk=row.pk)), status=201)
    except ValueError as exc:
        return JsonResponse({'detail': str(exc)}, status=400)
