from decimal import Decimal, InvalidOperation

from django.db import connection, IntegrityError, transaction
from django.db.models import Sum
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from .models import MaterialMovement, ProductionContainer


OIL_FINISHING_STEPS = {
    'sorption-loading': {
        'title': 'Загрузка масла в сорбент-систему',
        'sources': (ProductionContainer.KIND_RAW_DIESEL_TANK, ProductionContainer.KIND_RAW_SPINDLE_TANK),
        'destinations': (ProductionContainer.KIND_SORPTION_SYSTEM,),
        'movement_type': MaterialMovement.TYPE_RAW_TO_SORPTION,
    },
    'finishing-mixer-loading': {
        'title': 'Загрузка финишного миксера',
        'sources': (ProductionContainer.KIND_SORPTION_SYSTEM,),
        'destinations': (ProductionContainer.KIND_FINISHING_MIXER,),
        'movement_type': MaterialMovement.TYPE_SORPTION_TO_MIXER,
    },
    'finishing-filter-loading': {
        'title': 'Загрузка финишного фильтра',
        'sources': (ProductionContainer.KIND_FINISHING_MIXER,),
        'destinations': (ProductionContainer.KIND_FINISHING_FILTER,),
        'movement_type': MaterialMovement.TYPE_MIXER_TO_FILTER,
    },
    'finished-product-loading': {
        'title': 'Загрузка бака готовой продукции',
        'sources': (ProductionContainer.KIND_FINISHING_FILTER,),
        'destinations': (ProductionContainer.KIND_FINISHED_DIESEL_TANK, ProductionContainer.KIND_FINISHED_SPINDLE_TANK),
        'movement_type': MaterialMovement.TYPE_FILTER_TO_FINISHED_TANK,
    },
}

OIL_CONTAINER_PATHS = {
    'sorption-systems': ProductionContainer.KIND_SORPTION_SYSTEM,
    'finishing-mixers': ProductionContainer.KIND_FINISHING_MIXER,
    'finishing-filters': ProductionContainer.KIND_FINISHING_FILTER,
    'finished-diesel-tanks': ProductionContainer.KIND_FINISHED_DIESEL_TANK,
    'finished-spindle-tanks': ProductionContainer.KIND_FINISHED_SPINDLE_TANK,
}


def lock_oil_line():
    with connection.cursor() as cursor:
        cursor.execute('SELECT pg_advisory_xact_lock(%s)', [734092601])


def container_oil_product(container):
    if container.kind in (ProductionContainer.KIND_RAW_DIESEL_TANK, ProductionContainer.KIND_FINISHED_DIESEL_TANK):
        return 'diesel'
    if container.kind in (ProductionContainer.KIND_RAW_SPINDLE_TANK, ProductionContainer.KIND_FINISHED_SPINDLE_TANK):
        return 'spindle'
    return container.oil_product


def oil_transfer_error(source, destination, volume, product):
    if not product or container_oil_product(source) != product:
        return 'Продукт источника не соответствует движению.'
    if source.current_volume_liters < volume:
        return 'В источнике недостаточно продукта.'
    if destination.current_volume_liters + volume > destination.capacity_liters:
        return 'Объём превышает свободную вместимость получателя.'
    destination_product = container_oil_product(destination)
    if destination_product and destination_product != product:
        return 'Нельзя смешивать солярку и веретенку.'
    if destination.kind in ProductionContainer.SHARED_OIL_KINDS and ProductionContainer.objects.filter(
        kind__in=ProductionContainer.SHARED_OIL_KINDS, current_volume_liters__gt=0,
    ).exclude(oil_product=product).exists():
        return 'Общая линия занята другим продуктом. Сначала полностью освободите линию.'
    return None


def apply_oil_transfer(source, destination, volume, product):
    source.current_volume_liters -= volume
    destination.current_volume_liters += volume
    if source.kind in ProductionContainer.SHARED_OIL_KINDS and source.current_volume_liters == 0:
        source.oil_product = ''
    if destination.kind in ProductionContainer.SHARED_OIL_KINDS:
        destination.oil_product = product
    for container in (source, destination):
        container.save(update_fields=['current_volume_liters', 'oil_product', 'updated_at'])


@csrf_exempt
def oil_containers_view(request, container_path):
    from .views import _production_containers_view
    kind = OIL_CONTAINER_PATHS.get(container_path)
    if kind is None:
        return JsonResponse({'detail': 'Production container not found.'}, status=404)
    return _production_containers_view(request, kind)


def _idempotent_response(existing, user, config, source_id, destination_id, volume):
    from .views import _serialize_movement
    if (existing.created_by_id != user.pk or existing.movement_type != config['movement_type']
            or existing.source_container_id != source_id or existing.destination_container_id != destination_id
            or existing.volume_liters != volume):
        return JsonResponse({'detail': 'Ключ повторного запроса уже использован для другой операции.'}, status=409)
    return JsonResponse(_serialize_movement(existing))


@csrf_exempt
def oil_movements_view(request, step):
    from .views import (
        _audit_operation, _invalid_json_body, _json_body, _method_not_allowed,
        _movement_number, _require_processing_permission, _serialize_movement,
    )
    config = OIL_FINISHING_STEPS.get(step)
    if config is None:
        return JsonResponse({'detail': 'Movement not found.'}, status=404)
    user, error = _require_processing_permission(request, step)
    if error:
        return error
    if request.method == 'GET':
        try:
            page = max(1, int(request.GET.get('page', 1)))
        except ValueError:
            return JsonResponse({'detail': 'Некорректный номер страницы.'}, status=400)
        rows = MaterialMovement.objects.filter(movement_type=config['movement_type']).select_related('created_by')
        total = rows.count()
        page_count = max(1, (total + 9) // 10)
        page = min(page, page_count)
        return JsonResponse({
            'items': [_serialize_movement(row) for row in rows.order_by('-moved_at', '-id')[(page - 1) * 10:page * 10]],
            'total': total, 'page': page, 'page_count': page_count,
            'line_product': ProductionContainer.objects.filter(
                kind__in=ProductionContainer.SHARED_OIL_KINDS, current_volume_liters__gt=0,
            ).values_list('oil_product', flat=True).first() or '',
        })
    if request.method != 'POST':
        return _method_not_allowed()
    body = _json_body(request)
    if not isinstance(body, dict):
        return _invalid_json_body()
    try:
        source_id = int(body.get('source_id'))
        destination_id = int(body.get('destination_id'))
        volume = Decimal(str(body.get('volume_liters')))
        if not volume.is_finite() or not 0 < volume <= Decimal('99999999999.999') or volume != volume.quantize(Decimal('0.001')):
            raise ValueError
    except (TypeError, ValueError, InvalidOperation, OverflowError):
        return JsonResponse({'detail': 'Выберите источник, получателя и положительный объём с точностью до 0,001 л.'}, status=400)
    key = body.get('idempotency_key')
    if not isinstance(key, str) or not key.strip() or len(key) > 80:
        return JsonResponse({'detail': 'Valid idempotency key is required.'}, status=400)
    with transaction.atomic():
        lock_oil_line()
        existing = MaterialMovement.objects.filter(idempotency_key=key).select_related('created_by').first()
        if existing:
            return _idempotent_response(existing, user, config, source_id, destination_id, volume)
        containers = {container.pk: container for container in ProductionContainer.objects.select_for_update().filter(
            pk__in=[source_id, destination_id],
        ).order_by('pk')}
        source, destination = containers.get(source_id), containers.get(destination_id)
        if source is None or not source.is_active or source.kind not in config['sources']:
            return JsonResponse({'detail': 'Выберите активный источник соответствующего этапа.'}, status=400)
        if destination is None or not destination.is_active or destination.kind not in config['destinations']:
            return JsonResponse({'detail': 'Выберите активного получателя соответствующего этапа.'}, status=400)
        product = container_oil_product(source)
        error = oil_transfer_error(source, destination, volume, product)
        if error:
            return JsonResponse({'detail': error}, status=400)
        product_name = dict(ProductionContainer.OIL_PRODUCTS)[product]
        try:
            with transaction.atomic():
                movement = MaterialMovement.objects.create(
                    movement_number=_movement_number(), movement_type=config['movement_type'],
                    source_container=source, destination_container=destination, product_name=product_name,
                    oil_product=product, volume_liters=volume, created_by=user, idempotency_key=key,
                    source_snapshot=source.display_name, destination_snapshot=destination.display_name,
                    source_volume_before=source.current_volume_liters, source_volume_after=source.current_volume_liters - volume,
                    destination_volume_before=destination.current_volume_liters, destination_volume_after=destination.current_volume_liters + volume,
                    system_description=config['title'],
                )
        except IntegrityError:
            existing = MaterialMovement.objects.filter(idempotency_key=key).select_related('created_by').first()
            if existing:
                return _idempotent_response(existing, user, config, source_id, destination_id, volume)
            raise
        apply_oil_transfer(source, destination, volume, product)
        _audit_operation('movement_created', 'material_movement', movement.pk, user, {
            'movement_number': movement.movement_number, 'volume_liters': str(volume), 'product_name': product_name,
        })
        return JsonResponse(_serialize_movement(movement), status=201)


def oil_overview():
    from .views import _overview_container_items, _overview_container_totals
    result = {}
    for kind in OIL_CONTAINER_PATHS.values():
        step = next(config for config in OIL_FINISHING_STEPS.values() if kind in config['destinations'])
        items = _overview_container_items(kind, step['movement_type'])
        products = dict(ProductionContainer.objects.filter(kind=kind).values_list('pk', 'oil_product'))
        for item in items:
            item['oil_product'] = products[item['id']]
        result[kind] = {**_overview_container_totals(kind), 'items': items}
    today = timezone.localdate()
    result['separator_outputs'] = {}
    for code, name in [('water', MaterialMovement.PRODUCT_TECHNICAL_WATER), ('waste', MaterialMovement.PRODUCT_TECHNICAL_WASTE)]:
        movements = MaterialMovement.objects.filter(movement_type=MaterialMovement.TYPE_SEPARATOR_OUTPUT, product_name=name, is_compensated=False)
        result['separator_outputs'][code] = {
            'today_liters': str(movements.filter(moved_at__date=today).aggregate(total=Sum('volume_liters'))['total'] or Decimal('0.000')),
            'total_liters': str(movements.aggregate(total=Sum('volume_liters'))['total'] or Decimal('0.000')),
        }
    return result
