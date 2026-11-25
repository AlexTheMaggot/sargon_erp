from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Exists, OuterRef
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from .models import ContainerMeasurement, MaterialMovement, ProductionContainer, ReceiverRun
from .oil_processing import lock_oil_line


MODULE_CODE = 'reactor-receivers'
REACTOR_KIND = ProductionContainer.KIND_PROCESSING_WORKSHOP
LOADING_TYPE = MaterialMovement.TYPE_BOILER_TO_REACTOR
RECEIVER_NUMBERS = (1, 2, 3, 4)
RUSSIAN_RECEIVER = 'Ресивер'
INVALID_OPERATION = 'Выберите нужное оборудование и укажите корректные данные операции.'
STALE_RECEIVER = 'Состояние ресивера изменилось. Обновите список и повторите действие.'


def _positive_id(value):
    value = str(value).strip()
    return int(value) if value.isdecimal() and len(value) <= 19 and 0 < int(value) < 2 ** 63 else None


def _key(body):
    value = body.get('idempotency_key')
    value = value.strip() if isinstance(value, str) else ''
    return value if 0 < len(value) <= 80 else ''


def _serialize_run(run):
    return {
        'id': run.pk,
        'reactor_id': run.reactor_id,
        'reactor_name': run.reactor.display_name,
        'number': run.number,
        'opened_at': run.opened_at.isoformat(),
        'closed_at': run.closed_at.isoformat() if run.closed_at else None,
        'opened_by': run.opened_by.get_username() if run.opened_by else '',
        'closed_by': run.closed_by.get_username() if run.closed_by else '',
        'status': 'open' if not run.closed_at else 'drained' if run.is_drained else 'waiting',
    }


def _runs():
    return ReceiverRun.objects.select_related('reactor', 'opened_by', 'closed_by').annotate(
        is_drained=Exists(MaterialMovement.objects.filter(receiver_run_id=OuterRef('pk'), is_compensated=False)),
    )


def _latest_loading(reactor):
    return reactor.incoming_movements.filter(movement_type=LOADING_TYPE, is_compensated=False).order_by('-pk').first()


def _current_runs(reactor):
    return list(_runs().filter(reactor=reactor).order_by('number', '-pk').distinct('number'))


def _next_receiver(loading, runs):
    if loading is None:
        return None
    latest = max(runs, key=lambda run: run.pk, default=None)
    if latest is None or loading.pk != latest.loading_id:
        return 1
    return 2 if latest.number == 4 else latest.number + 1


def last_reactor_measurement(reactor):
    return reactor.measurements.select_related('revision').order_by('-pk').first()


def _serialize_reactor(reactor, measurement):
    return {
        'id': reactor.pk,
        'number': reactor.number,
        'name': reactor.display_name,
        'capacity_liters': str(reactor.capacity_liters),
        'measured_liters': str(measurement.actual_liters) if measurement else None,
        'measured_at': measurement.revision.created_at.isoformat() if measurement else None,
    }


def reactors_overview():
    reactors = ProductionContainer.objects.filter(kind=REACTOR_KIND, is_active=True)
    measurements = ContainerMeasurement.objects.filter(container__in=reactors).select_related('revision').order_by(
        'container_id', '-pk',
    ).distinct('container_id')
    by_reactor = {item.container_id: item for item in measurements}
    items = []
    for reactor in reactors:
        runs = {run.number: run for run in _current_runs(reactor)}
        items.append({
            **_serialize_reactor(reactor, by_reactor.get(reactor.pk)),
            'receivers': [{
                'number': number, 'run': _serialize_run(runs[number]) if number in runs else None,
            } for number in RECEIVER_NUMBERS],
        })
    return items


def reactor_has_pending_receivers(reactor_id):
    return _runs().filter(reactor_id=reactor_id, is_drained=False).exists()


@csrf_exempt
def reactor_receivers_view(request):
    from .views import _audit_operation, _json_body, _json_error, _method_not_allowed, _require_processing_permission

    if request.method not in ('GET', 'POST'):
        return _method_not_allowed()
    action_permission = 'view' if request.method == 'GET' else 'create'
    user, error = _require_processing_permission(request, MODULE_CODE, action_permission)
    if error:
        return error
    if request.method == 'GET':
        reactors = ProductionContainer.objects.filter(kind=REACTOR_KIND, is_active=True)
        items = [{'id': reactor.pk, 'name': reactor.display_name} for reactor in reactors]
        requested_id = request.GET.get('reactor_id')
        reactor = (next((item for item in reactors if item.pk == _positive_id(requested_id)), None)
                   if requested_id else next(iter(reactors), None))
        if reactor is None:
            return JsonResponse({'reactors': items, 'reactor': None, 'history': [], 'page': 1, 'page_count': 1})
        runs = {run.number: run for run in _current_runs(reactor)}
        loading = _latest_loading(reactor)
        page = Paginator(_runs().filter(reactor=reactor).order_by('-pk'), 10).get_page(request.GET.get('page', 1))
        return JsonResponse({
            'reactors': items,
            'reactor': {
                **_serialize_reactor(reactor, last_reactor_measurement(reactor)),
                'loading_id': loading.pk if loading else None,
                'next_receiver': _next_receiver(loading, list(runs.values())),
                'open_receiver': next((run.number for run in runs.values() if run.closed_at is None), None),
                'receivers': [{
                    'number': number, 'run': _serialize_run(runs[number]) if number in runs else None,
                } for number in RECEIVER_NUMBERS],
            },
            'history': [_serialize_run(run) for run in page],
            'page': page.number,
            'page_count': page.paginator.num_pages,
        })

    body = _json_body(request)
    if not isinstance(body, dict):
        return _json_error(INVALID_OPERATION, 400)
    reactor_id = _positive_id(body.get('reactor_id'))
    number = _positive_id(body.get('number'))
    action = body.get('action')
    key = _key(body)
    loading_id = _positive_id(body.get('loading_id'))
    run_id = _positive_id(body.get('run_id'))
    if (not reactor_id or number not in RECEIVER_NUMBERS or action not in ('open', 'close') or not key
            or (action == 'open' and not loading_id) or (action == 'close' and not run_id)):
        return _json_error(INVALID_OPERATION, 400)

    with transaction.atomic():
        lock_oil_line()
        reactor = ProductionContainer.objects.select_for_update().filter(pk=reactor_id, kind=REACTOR_KIND).first()
        key_field = 'open_key' if action == 'open' else 'close_key'
        existing = _runs().filter(**{key_field: key}).first()
        if existing:
            actor_id = existing.opened_by_id if action == 'open' else existing.closed_by_id
            if (actor_id != user.pk or existing.reactor_id != reactor_id or existing.number != number
                    or (action == 'open' and existing.loading_id != loading_id)
                    or (action == 'close' and existing.pk != run_id)):
                return _json_error('Idempotency key is already used.', 409)
            return JsonResponse(_serialize_run(existing))
        if reactor is None or not reactor.is_active:
            return _json_error(INVALID_OPERATION, 400)
        if action == 'close':
            run = _runs().filter(pk=run_id, reactor=reactor, number=number, closed_at__isnull=True).first()
            if run is None:
                return _json_error(STALE_RECEIVER, 409)
            run.closed_at, run.close_key, run.closed_by = timezone.now(), key, user
            run.save(update_fields=['closed_at', 'close_key', 'closed_by'])
        else:
            loading = _latest_loading(reactor)
            runs = _current_runs(reactor)
            previous_run = next((run for run in runs if run.number == number), None)
            if (loading is None or loading.pk != loading_id or _next_receiver(loading, runs) != number
                    or any(run.closed_at is None for run in runs) or (previous_run and not previous_run.is_drained)):
                return _json_error(STALE_RECEIVER, 409)
            run = ReceiverRun.objects.create(reactor=reactor, number=number, loading=loading, opened_by=user, open_key=key)
            run.is_drained = False
        _audit_operation(f'receiver_{action}', 'receiver_run', run.pk, user, {'reactor': reactor.display_name, 'number': number})
        return JsonResponse(_serialize_run(run), status=201 if action == 'open' else 200)


@csrf_exempt
def reactor_outlet_view(request, module_code, destination_kind, movement_type, product_name, numbers=()):
    from .views import (
        _audit_operation, _json_body, _json_error, _method_not_allowed, _movement_number,
        _require_processing_permission, _serialize_movement, _volume_value,
    )

    if request.method not in ('GET', 'POST'):
        return _method_not_allowed()
    user, error = _require_processing_permission(request, module_code, 'view' if request.method == 'GET' else 'create')
    if error:
        return error
    if request.method == 'GET':
        if not numbers:
            return _method_not_allowed()
        runs = _runs().filter(number__in=numbers, reactor__is_active=True, closed_at__isnull=False, is_drained=False)
        return JsonResponse({'items': [_serialize_run(run) for run in runs.order_by('reactor__number', 'number')]})

    body = _json_body(request)
    if not isinstance(body, dict):
        return _json_error(INVALID_OPERATION, 400)
    run_id = _positive_id(body.get('receiver_run_id')) if numbers else None
    reactor_id = _positive_id(body.get('source_workshop_id')) if not numbers else None
    tank_id = _positive_id(body.get('destination_tank_id'))
    volume = _volume_value(body.get('volume_liters'))
    key = _key(body)
    if not (run_id or reactor_id) or not tank_id or not key:
        return _json_error(INVALID_OPERATION, 400)
    if volume is None:
        return _json_error('Volume must be positive and contain up to three decimal places.', 400)

    with transaction.atomic():
        lock_oil_line()
        existing = MaterialMovement.objects.filter(idempotency_key=key).first()
        if existing:
            if (existing.created_by_id != user.pk or existing.movement_type != movement_type
                    or existing.receiver_run_id != run_id or existing.source_container_id != reactor_id
                    or existing.destination_container_id != tank_id or existing.volume_liters != volume):
                return _json_error('Idempotency key is already used.', 409)
            return JsonResponse(_serialize_movement(existing))
        run = _runs().filter(pk=run_id, number__in=numbers).first() if run_id else None
        if run_id and (run is None or not run.closed_at or run.is_drained):
            return _json_error(STALE_RECEIVER, 409)
        equipment = {
            item.pk: item for item in ProductionContainer.objects.select_for_update().filter(
                pk__in=(run.reactor_id if run else reactor_id, tank_id), is_active=True,
            ).order_by('pk')
        }
        reactor = equipment.get(run.reactor_id if run else reactor_id)
        tank = equipment.get(tank_id)
        if reactor is None or reactor.kind != REACTOR_KIND or tank is None or tank.kind != destination_kind:
            return _json_error(INVALID_OPERATION, 400)
        if not run and volume > reactor.capacity_liters:
            return _json_error('Объём движения превышает вместимость реактора.', 400)
        before = tank.current_volume_liters
        if before + volume > tank.capacity_liters:
            return _json_error('Destination tank capacity would be exceeded.', 400)

        movement = MaterialMovement.objects.create(
            movement_number=_movement_number(), movement_type=movement_type, source_container=None if run else reactor,
            receiver_run=run, destination_container=tank, product_name=product_name, volume_liters=volume, created_by=user,
            idempotency_key=key,
            source_snapshot=f'{reactor.display_name} · {RUSSIAN_RECEIVER} №{run.number}' if run else reactor.display_name,
            destination_snapshot=tank.display_name,
            destination_volume_before=before, destination_volume_after=before + volume,
        )
        tank.current_volume_liters += volume
        tank.save(update_fields=['current_volume_liters', 'updated_at'])
        if not run:
            reactor.save(update_fields=['updated_at'])
        _audit_operation('movement_created', 'material_movement', movement.pk, user, {
            'movement_number': movement.movement_number, 'volume_liters': str(volume),
        })
        return JsonResponse(_serialize_movement(movement), status=201)
