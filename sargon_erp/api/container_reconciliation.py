from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP

from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Max
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from .models import ContainerMeasurement, ContainerReconciliation, ContainerReconciliationRevision, MaterialMovement, ProductionContainer
from .oil_processing import container_snapshot_label, lock_oil_line


MODULE_CODE = 'container-reconciliation'
SHARED_KINDS = ProductionContainer.SHARED_OIL_KINDS
STALE_BALANCES = 'Остатки или сверка изменились. Обновите расчётные данные и перепроверьте замеры.'
RECONCILED_MOVEMENT = 'Нельзя отменить движение, учтённое в сверке остатков.'


def movement_is_reconciled(movement):
    container_ids = [container_id for container_id in (movement.source_container_id, movement.destination_container_id) if container_id]
    return ContainerMeasurement.objects.filter(container_id__in=container_ids, movement_watermark__gte=movement.pk).exists()


def _equipment():
    return ProductionContainer.objects.filter(kind__in=ProductionContainer.RECYCLING_KINDS, is_active=True)


def _latest_measurements(queryset):
    return queryset.order_by('container_id', '-pk').distinct('container_id')


def _movement_watermarks(container_ids):
    result = defaultdict(int)
    for field in ('source_container_id', 'destination_container_id'):
        groups = MaterialMovement.objects.filter(**{f'{field}__in': container_ids}).order_by().values(field).annotate(latest=Max('pk'))
        for group in groups:
            result[group[field]] = max(result[group[field]], group['latest'])
    return result


def _summary(measurements):
    comparable = [line for line in measurements if line.expected_liters is not None]
    expected = sum((line.expected_liters for line in comparable), Decimal('0.000'))
    difference = sum((line.actual_liters - line.expected_liters for line in comparable), Decimal('0.000'))
    absolute = sum((abs(line.actual_liters - line.expected_liters) for line in comparable), Decimal('0.000'))

    def percentage(volume):
        if not expected:
            return None
        rounded = (volume * 100 / expected).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        return str(rounded or Decimal('0.00'))

    return {
        'expected_liters': str(expected),
        'actual_liters': str(expected + difference),
        'difference_liters': str(difference),
        'absolute_difference_liters': str(absolute),
        'deviation_percent': percentage(difference),
        'absolute_deviation_percent': percentage(absolute),
        'measured_count': len(measurements),
        'comparable_count': len(comparable),
    }


def _measurement(line):
    measured = {
        'container_id': line.container_id,
        'name': container_snapshot_label(line.container_name),
        'revision_id': line.revision_id,
        'measured_at': line.revision.created_at.isoformat(),
        'actual_product': line.actual_product,
        'previous_product': line.previous_product,
        'previous_liters': str(line.previous_liters),
        **_summary([line]),
    }
    if line.expected_liters is None:
        measured.update(expected_liters=None, actual_liters=str(line.actual_liters), difference_liters=None)
    return measured


def _revision(revision):
    return {
        'id': revision.pk,
        'number': revision.number,
        'created_at': revision.created_at.isoformat(),
        'operator': revision.operator_name,
        'eligible_count': revision.eligible_count,
    }


def _references():
    equipment = list(_equipment())
    reactor_kind = ProductionContainer.KIND_PROCESSING_WORKSHOP
    actual = {line.container_id: line for line in _latest_measurements(ContainerMeasurement.objects.filter(
        container_id__in=[item.pk for item in equipment if item.kind == reactor_kind],
    )).select_related('revision')}
    return [{
        'id': container.pk,
        'name': container.display_name,
        'kind': container.kind,
        'current_liters': str(container.current_volume_liters) if container.kind != reactor_kind else None,
        'last_actual_liters': str(actual[container.pk].actual_liters) if container.pk in actual else None,
        'last_measured_at': actual[container.pk].revision.created_at.isoformat() if container.pk in actual else None,
        'measurement_only': container.kind == reactor_kind,
        'capacity_liters': str(container.capacity_liters),
        'shared': container.kind in SHARED_KINDS,
        'oil_product': container.oil_product,
        'version': container.updated_at.isoformat(),
    } for container in equipment]


def _detail(reconciliation):
    revisions = list(reconciliation.revisions.order_by('-number').prefetch_related('measurements__revision'))
    latest = revisions[0]
    effective = {}
    history = []
    for revision in revisions:
        rows = list(revision.measurements.all())
        history.append({**_revision(revision), 'measurements': [_measurement(row) for row in rows]})
        for row in rows:
            effective.setdefault(row.container_id, row)
    watermarks = _movement_watermarks(effective)
    last_ids = dict(_latest_measurements(ContainerMeasurement.objects.filter(container_id__in=effective)).values_list('container_id', 'pk'))
    return {
        'id': reconciliation.pk,
        'created_at': reconciliation.created_at.isoformat(),
        'latest_revision': _revision(latest),
        'summary': _summary(list(effective.values())),
        'measurements': [{
            **_measurement(row),
            'can_correct': row.pk == last_ids[row.container_id] and watermarks[row.container_id] == row.movement_watermark,
        } for row in effective.values()],
        'revisions': history,
    }


def _positive_id(value):
    return type(value) is int and 0 < value < 2 ** 63


def _parse_submission(body):
    from .views import _volume_value

    if not isinstance(body, dict) or not isinstance(body.get('measurements'), list):
        return None
    submissions = {}
    for row in body['measurements']:
        if not isinstance(row, dict) or not _positive_id(row.get('container_id')):
            return None
        raw_volume = row.get('actual_liters')
        if raw_volume is None or (isinstance(raw_volume, str) and not raw_volume.strip()):
            continue
        volume = _volume_value(raw_volume, allow_zero=True)
        product = row.get('oil_product', '')
        version = row.get('version')
        if volume is None or product not in ('', 'diesel', 'spindle') or not isinstance(version, str) or not version:
            return None
        if row['container_id'] in submissions:
            return None
        submissions[row['container_id']] = (volume, product, version)
    return submissions


@transaction.atomic
def _save(reconciliation_id, base_revision_id, submissions, user):
    from .views import _audit_operation, _json_error

    lock_oil_line()
    reconciliation = None
    latest = None
    effective = {}
    if reconciliation_id is not None:
        reconciliation = ContainerReconciliation.objects.select_for_update().filter(pk=reconciliation_id).first()
        if reconciliation is None:
            return _json_error('Сверка не найдена.', 404)
        latest = reconciliation.revisions.order_by('-number').first()
        if latest is None or latest.pk != base_revision_id:
            return _json_error(STALE_BALANCES, 409)
        effective = {line.container_id: line for line in _latest_measurements(
            ContainerMeasurement.objects.filter(revision__reconciliation=reconciliation, container_id__in=submissions)
        )}
    containers = {container.pk: container for container in _equipment().select_for_update().filter(pk__in=submissions).order_by('pk')}
    if len(containers) != len(submissions):
        return _json_error(STALE_BALANCES, 409)
    watermarks = _movement_watermarks(containers)
    last_measurements = {line.container_id: line for line in _latest_measurements(
        ContainerMeasurement.objects.filter(container_id__in=containers).select_related('revision'),
    )}
    measurements = []
    remaining_products = set(_equipment().filter(
        kind__in=SHARED_KINDS, current_volume_liters__gt=0,
    ).exclude(pk__in=containers).order_by().values_list('oil_product', flat=True))
    for container_id, (actual, product, version) in submissions.items():
        container = containers[container_id]
        if container.updated_at.isoformat() != version:
            return _json_error(STALE_BALANCES, 409)
        if actual > container.capacity_liters:
            return _json_error('Фактический объём превышает вместимость ёмкости.', 400)
        previous = effective.get(container_id)
        last = last_measurements.get(container_id)
        watermark = watermarks[container_id]
        if previous and (last is None or last.pk != previous.pk or watermark != previous.movement_watermark):
            return _json_error('После этого замера были движения или новая сверка. Введите новый фактический замер.', 409)
        if reconciliation and not previous and last and last.revision.reconciliation_id > reconciliation.pk:
            return _json_error('После этого замера были движения или новая сверка. Введите новый фактический замер.', 409)
        expected = previous.expected_liters if previous else container.current_volume_liters
        if container.kind == ProductionContainer.KIND_PROCESSING_WORKSHOP:
            expected = None
        if container.kind in SHARED_KINDS and actual > 0:
            existing_product = container.oil_product
            product = product or existing_product
            if not product:
                return _json_error('Укажите продукт для заполненной ёмкости общей линии.', 400)
            if existing_product and product != existing_product and not (previous and expected == 0):
                return _json_error('Нельзя изменить продукт в непустой ёмкости общей линии.', 400)
            remaining_products.add(product)
        else:
            product = ''
        measurements.append(ContainerMeasurement(
            container=container, container_name=container.display_name,
            expected_liters=expected, previous_liters=container.current_volume_liters, actual_liters=actual,
            previous_product=container.oil_product, actual_product=product, movement_watermark=watermark,
        ))
    if len(remaining_products) > 1:
        return _json_error('Нельзя смешивать солярку и веретенку.', 400)

    now = timezone.now()
    if reconciliation is None:
        reconciliation = ContainerReconciliation.objects.create(created_at=now)
    eligible = set(_equipment().values_list('pk', flat=True))
    eligible.update(ContainerMeasurement.objects.filter(revision__reconciliation=reconciliation).values_list('container_id', flat=True))
    revision = ContainerReconciliationRevision.objects.create(
        reconciliation=reconciliation, number=latest.number + 1 if latest else 1,
        created_by=user, operator_name=user.get_username(), eligible_count=len(eligible), created_at=now,
    )
    changes = []
    for measurement in measurements:
        container = measurement.container
        container.current_volume_liters = measurement.actual_liters
        container.oil_product = measurement.actual_product
        container.updated_at = now
        measurement.revision = revision
        changes.append(container)
    ProductionContainer.objects.bulk_update(changes, ['current_volume_liters', 'oil_product', 'updated_at'])
    ContainerMeasurement.objects.bulk_create(measurements)
    _audit_operation('container_reconciled', 'container_reconciliation', reconciliation.pk, user, {
        'revision': revision.number, 'measured_count': len(measurements),
    })
    return JsonResponse(_detail(reconciliation), status=201)


@csrf_exempt
def container_reconciliations_view(request, reconciliation_id=None):
    from .views import (
        _has_permission, _invalid_json_body, _is_admin, _json_body, _json_error, _method_not_allowed,
        _permission_denied, _require_processing_permission,
    )

    user, error = _require_processing_permission(request, MODULE_CODE, 'view')
    if error:
        return error
    if request.method == 'GET':
        if reconciliation_id is not None:
            reconciliation = ContainerReconciliation.objects.filter(pk=reconciliation_id).first()
            if reconciliation is None:
                return _json_error('Сверка не найдена.', 404)
            return JsonResponse(_detail(reconciliation))
        walks = ContainerReconciliation.objects.annotate(
            revision_count=Count('revisions'),
        ).order_by('-pk')
        paginator = Paginator(walks, 10)
        page = paginator.get_page(request.GET.get('page', 1))
        return JsonResponse({
            'containers': _references(),
            'items': [{
                'id': walk.pk, 'created_at': walk.created_at.isoformat(), 'revision_count': walk.revision_count,
            } for walk in page],
            'page': page.number, 'page_count': paginator.num_pages, 'total': paginator.count,
        })
    if request.method != 'POST' or reconciliation_id is not None:
        return _method_not_allowed()
    body = _json_body(request)
    if not isinstance(body, dict):
        return _invalid_json_body()
    reconciliation_id, base_revision_id = body.get('reconciliation_id'), body.get('base_revision_id')
    if (reconciliation_id is None and base_revision_id is not None) or (
        reconciliation_id is not None and not (_positive_id(reconciliation_id) and _positive_id(base_revision_id))
    ):
        return _invalid_json_body()
    if not _is_admin(user) and not _has_permission(user, MODULE_CODE, 'update' if reconciliation_id is not None else 'create'):
        return _permission_denied()
    submissions = _parse_submission(body)
    if submissions is None:
        return _json_error('Укажите фактические литры с точностью до 0,001 л без повторов ёмкостей.', 400)
    if not submissions:
        return _json_error('Введите хотя бы один фактический остаток.', 400)
    return _save(reconciliation_id, base_revision_id, submissions, user)


def reconciliation_overview():
    latest = ContainerReconciliationRevision.objects.order_by('-reconciliation_id', '-number').first()
    if latest is None:
        return {'latest': None, 'stages': {}}
    equipment = defaultdict(list)
    for container in _equipment():
        equipment[container.kind].append(container)
    active_ids = [container.pk for containers in equipment.values() for container in containers]
    latest_lines = {line.container_id: line for line in _latest_measurements(
        ContainerMeasurement.objects.filter(container_id__in=active_ids).select_related('revision'),
    )}
    stages = {}
    for kind, containers in equipment.items():
        rows = [latest_lines[container.pk] for container in containers if container.pk in latest_lines]
        stage_walk = max((row.revision.reconciliation_id for row in rows), default=None)
        stage_rows = [row for row in rows if row.revision.reconciliation_id == stage_walk]
        stages[kind] = {
            'summary': {
                **_summary(stage_rows),
                'eligible_count': len(containers),
                'measured_at': max(row.revision.created_at for row in stage_rows).isoformat(),
            } if stage_rows else None,
            'containers': [{
                'id': container.pk, 'name': container.display_name,
                'measurement': _measurement(latest_lines[container.pk]) if container.pk in latest_lines else None,
            } for container in containers],
        }
    walk_rows = list(_latest_measurements(ContainerMeasurement.objects.filter(
        revision__reconciliation_id=latest.reconciliation_id, revision__number__lte=latest.number,
    )))
    return {'latest': {**_revision(latest), **_summary(walk_rows), 'reconciliation_id': latest.reconciliation_id}, 'stages': stages}
