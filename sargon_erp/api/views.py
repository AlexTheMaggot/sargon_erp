import json
from decimal import Decimal
from decimal import InvalidOperation
from decimal import ROUND_HALF_UP
from uuid import uuid4

import jwt
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.contrib.auth import authenticate
from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.db import transaction
from django.db.models import Max
from django.db.models import Q
from django.db.models import Sum
from django.db.models import ProtectedError
from django.http import JsonResponse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET
from django.views.decorators.http import require_POST

from .auth import create_access_token
from .auth import get_user_from_token
from .consumers import OPERATIONS_GROUP
from .models import AccessGroup
from .models import City
from .models import GroupModuleAccess
from .models import LaboratoryAnalysis
from .models import Module
from .models import MaterialMovement
from .models import OperationAuditLog
from .models import Permission
from .models import ProductionContainer
from .models import RawMaterialReceipt
from .models import ReceiptBatch
from .models import Supplier
from .models import UserProfile
from .models import InventoryCategory
from .models import InventoryItem
from .models import KnowledgeArticle
from .models import KnowledgeCategory
from .models import UnitOfMeasure
from .models import Warehouse
from .models import WarehouseBalance
from .models import WarehouseDocument
from .models import WarehouseDocumentLine
from .models import WarehouseDocumentSequence
from .models import WarehouseMovement
from .models import ProductionOutput
from .models import ProductionOutputLine
from .models import ProductionMaterialUsage
from .models import OilGrade, OilManufacturingBatch
from .oil_processing import OIL_FINISHING_STEPS, OIL_CONTAINER_PATHS
from .oil_processing import apply_oil_transfer, container_oil_product, lock_oil_line, oil_transfer_error


MODULE_ACCESS = 'access'
MODULE_DASHBOARD = 'dashboard'
MODULE_LABORATORY = 'laboratory-analysis'
MODULE_RAW_MATERIAL = 'raw-material-receiving'
MODULE_SUPPLIERS = 'suppliers'
MODULE_USED_OIL_PROCESSING = 'used-oil-processing'
MODULE_BOILER_LOADING = 'boiler-loading'
MODULE_SEPARATOR_LOADING = 'separator-loading'
MODULE_SEPARATOR_OUTPUT = 'separator-output'
MODULE_CHEMICAL_MIXER_LOADING = 'chemical-mixer-loading'
MODULE_WORKSHOP_LOADING = 'workshop-loading'
MODULE_RAW_DIESEL_TANK_LOADING = 'raw-diesel-tank-loading'
MODULE_RAW_SPINDLE_TANK_LOADING = 'raw-spindle-tank-loading'
MODULE_WAREHOUSE_ACCOUNTING = 'warehouse-accounting'
MODULE_WAREHOUSE_SETTINGS = 'warehouse-settings'
MODULE_KNOWLEDGE_BASE = 'knowledge-base'
MODULE_CANISTER_LOADING = 'canister-loading'
MODULE_CAP_LOADING = 'cap-loading'
MODULE_SORBENT_LOADING = 'sorbent-loading'
MODULE_CANISTER_OUTPUT = 'canister-output'
MODULE_CAP_OUTPUT = 'cap-output'

PROCESSING_FORM_MODULE_CODES = {
    MODULE_BOILER_LOADING,
    MODULE_SEPARATOR_LOADING,
    MODULE_SEPARATOR_OUTPUT,
    MODULE_CHEMICAL_MIXER_LOADING,
    MODULE_WORKSHOP_LOADING,
    MODULE_RAW_DIESEL_TANK_LOADING,
    MODULE_RAW_SPINDLE_TANK_LOADING,
}
PROCESSING_FORM_MODULE_CODES.update(OIL_FINISHING_STEPS)
PROCESSING_FORM_MODULE_CODES.update(('concentrate-loading', 'oil-blending', 'oil-tank-loading', 'oil-filling', 'sorbent-cycle'))

PERMISSION_APPROVE = 'approve'
PERMISSION_CREATE = 'create'
PERMISSION_VIEW = 'view'
PERMISSION_RECEIPT = 'receipt'
PERMISSION_ISSUE = 'issue'
PERMISSION_TRANSFER = 'transfer'
PERMISSION_TRANSFER_CONFIRM = 'transfer-confirm'
PERMISSION_INVENTORY = 'inventory'

VOLUME_QUANTUM = Decimal('0.001')


def _json_body(request):
    try:
        return json.loads(request.body.decode('utf-8'))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None


def _json_error(detail, status):
    return JsonResponse({'detail': detail}, status=status)


def _invalid_json_body():
    return _json_error('Invalid JSON body.', status=400)


def _method_not_allowed():
    return _json_error('Method not allowed.', status=405)


def _broadcast_operations_event(event_type, payload=None, target_module=None):
    channel_layer = get_channel_layer()
    if channel_layer is None:
        return

    async_to_sync(channel_layer.group_send)(
        OPERATIONS_GROUP,
        {
            'type': 'operations.event',
            'payload': {
                'event': event_type,
                'target_module': target_module,
                **(payload or {}),
            },
        },
    )


def _decimal_value(value):
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _get_laboratory_analysis(receipt):
    try:
        return receipt.laboratory_analysis
    except LaboratoryAnalysis.DoesNotExist:
        return None


def _get_batch_laboratory_analysis(batch):
    try:
        return batch.laboratory_analysis
    except LaboratoryAnalysis.DoesNotExist:
        return None


def _auth_user(request):
    authorization = request.headers.get('Authorization', '')
    if not authorization.startswith('Bearer '):
        return None

    token = authorization.removeprefix('Bearer ').strip()
    try:
        return get_user_from_token(token)
    except (get_user_model().DoesNotExist, jwt.PyJWTError):
        return None


def _require_auth(request):
    user = _auth_user(request)
    if user is None:
        return None, _json_error('Authentication required.', status=401)
    return user, None


def _method_permission(request):
    if request.method == 'GET':
        return 'view'
    if request.method == 'POST':
        return 'create'
    if request.method in ('PUT', 'PATCH'):
        return 'update'
    if request.method == 'DELETE':
        return 'delete'
    return None


def _user_access_map(user):
    profile, _ = UserProfile.objects.select_related('group').get_or_create(user=user)
    if profile.group is None:
        return {}

    access_rows = profile.group.module_access.select_related('module').prefetch_related('permissions')
    access_map = {}
    for access in access_rows:
        if not access.module.is_active:
            continue
        permission_codes = set(access.permissions.values_list('code', flat=True))
        if not permission_codes:
            permission_codes.add('view')
        access_map[access.module.code] = sorted(permission_codes)
    return access_map


def _user_start_path(user):
    if user.is_superuser:
        return '/welcome'

    profile, _ = UserProfile.objects.select_related('group__start_module').get_or_create(user=user)
    if profile.group is None:
        return '/welcome' if _is_admin(user) else '/no-access'

    access_map = _user_access_map(user)
    start_module = profile.group.start_module
    if (
        start_module
        and start_module.is_active
        and start_module.default_path
        and PERMISSION_VIEW in access_map.get(start_module.code, [])
    ):
        return start_module.default_path

    if _is_admin(user) or PERMISSION_VIEW in access_map.get(MODULE_DASHBOARD, []):
        return '/welcome'

    module = (
        Module.objects
        .filter(code__in=[code for code, permissions in access_map.items() if PERMISSION_VIEW in permissions], is_active=True)
        .exclude(default_path='')
        .order_by('name')
        .first()
    )
    return module.default_path if module else '/no-access'


def _has_permission(user, module_code, permission_code):
    if user.is_superuser:
        return True
    return permission_code in _user_access_map(user).get(module_code, [])


def _permission_denied():
    return _json_error('Permission denied.', status=403)


def _require_permission(request, module_code, permission_code=None):
    user, error = _require_auth(request)
    if error:
        return None, error

    required_permission = permission_code or _method_permission(request)
    if required_permission and not _has_permission(user, module_code, required_permission):
        return None, _permission_denied()
    return user, None


def _has_any_permission(user, permission_pairs):
    return any(_has_permission(user, module_code, permission_code) for module_code, permission_code in permission_pairs)


def _require_city_permission(request):
    user, error = _require_auth(request)
    if error:
        return None, error

    if request.method == 'GET':
        can_view_directory = _has_any_permission(user, [
            (MODULE_ACCESS, PERMISSION_VIEW),
            (MODULE_RAW_MATERIAL, PERMISSION_VIEW),
            (MODULE_SUPPLIERS, PERMISSION_VIEW),
        ])
        if not can_view_directory:
            return None, _permission_denied()
    elif not _has_permission(user, MODULE_ACCESS, _method_permission(request)):
        return None, _permission_denied()

    return user, None


def _require_supplier_permission(request):
    user, error = _require_auth(request)
    if error:
        return None, error

    required_permission = _method_permission(request)
    if not _has_any_permission(user, [
        (MODULE_ACCESS, required_permission),
        (MODULE_SUPPLIERS, required_permission),
    ]):
        return None, _permission_denied()

    return user, None


def _serialize_permission(permission):
    return {
        'id': permission.pk,
        'code': permission.code,
        'name': permission.name,
        'description': permission.description,
    }


def _serialize_module(module):
    return {
        'id': module.pk,
        'code': module.code,
        'name': module.name,
        'description': module.description,
        'default_path': module.default_path,
        'is_active': module.is_active,
    }


def _serialize_group(group):
    access_rows = group.module_access.select_related('module').prefetch_related('permissions')
    return {
        'id': group.pk,
        'name': group.name,
        'description': group.description,
        'modules': [
            {
                **_serialize_module(access.module),
                'permissions': [_serialize_permission(permission) for permission in access.permissions.all()],
            }
            for access in access_rows
        ],
        'module_ids': list(group.modules.values_list('id', flat=True)),
        'start_module': _serialize_module(group.start_module) if group.start_module else None,
        'start_module_id': group.start_module_id,
    }


def _serialize_user(user):
    profile, _ = UserProfile.objects.select_related('group').get_or_create(user=user)
    return {
        'id': user.pk,
        'username': user.get_username(),
        'first_name': user.first_name,
        'last_name': user.last_name,
        'email': user.email,
        'is_active': user.is_active,
        'group': _serialize_group(profile.group) if profile.group else None,
        'group_id': profile.group_id,
    }


def _serialize_current_user(user):
    return {
        'id': user.pk,
        'username': user.get_username(),
        'is_admin': _is_admin(user),
        'access': _user_access_map(user),
        'start_path': _user_start_path(user),
    }


def _serialize_city(city):
    return {
        'id': city.pk,
        'name': city.name,
    }


def _serialize_supplier(supplier):
    return {
        'id': supplier.pk,
        'company_name': supplier.company_name,
        'city': _serialize_city(supplier.city),
        'city_id': supplier.city_id,
        'address': supplier.address,
        'phone': supplier.phone,
    }


def _analysis_status(analysis):
    if analysis is None:
        return 'missing'
    if analysis.is_rejected:
        return 'rejected'
    if analysis.is_approved:
        return 'approved'
    if analysis.is_filled:
        return 'filled'
    return 'pending'


def _is_batch_locked(batch):
    analysis = _get_batch_laboratory_analysis(batch)
    return bool(batch.receipt.is_completed or (analysis and (analysis.is_rejected or (analysis.is_filled and not analysis.is_approved))))


def _serialize_batch(batch):
    analysis = _get_batch_laboratory_analysis(batch)
    is_analysis_filled = analysis.is_filled if analysis else False
    is_analysis_approved = analysis.is_approved if analysis else False
    is_analysis_rejected = analysis.is_rejected if analysis else False
    is_locked = _is_batch_locked(batch)
    is_distributed = batch.material_movements.filter(movement_type=MaterialMovement.TYPE_RECEIPT_TO_TANK).exists()
    return {
        'id': batch.pk,
        'receipt_id': batch.receipt_id,
        'sequence_number': batch.sequence_number,
        'input_quantity': str(batch.input_quantity) if batch.input_quantity is not None else '',
        'input_unit': batch.input_unit,
        'quantity_liters': str(batch.quantity_liters) if batch.quantity_liters is not None else '',
        'laboratory_analysis_id': analysis.pk if analysis else None,
        'analysis_status': _analysis_status(analysis),
        'is_analysis_filled': is_analysis_filled,
        'is_analysis_approved': is_analysis_approved,
        'is_analysis_rejected': is_analysis_rejected,
        'is_locked': is_locked,
        'is_distributed': is_distributed,
        'can_set_quantity': is_analysis_approved and not is_analysis_rejected and not is_distributed,
        'created_at': batch.created_at.isoformat(),
    }


def _serialize_receipt(receipt):
    batches = list(receipt.batches.all())
    approved_batches = [batch for batch in batches if (_get_batch_laboratory_analysis(batch) and _get_batch_laboratory_analysis(batch).is_approved)]
    rejected_batches = [batch for batch in batches if (_get_batch_laboratory_analysis(batch) and _get_batch_laboratory_analysis(batch).is_rejected)]
    pending_batches = [batch for batch in batches if _analysis_status(_get_batch_laboratory_analysis(batch)) in ('missing', 'pending', 'filled')]
    total_liters = sum((batch.quantity_liters for batch in approved_batches if batch.quantity_liters is not None), Decimal('0'))
    has_rejected_batches = bool(rejected_batches)
    has_pending_batches = bool(pending_batches)
    return {
        'id': receipt.pk,
        'supplier': _serialize_supplier(receipt.supplier),
        'supplier_id': receipt.supplier_id,
        'input_quantity': str(receipt.input_quantity) if receipt.input_quantity is not None else '',
        'input_unit': receipt.input_unit,
        'quantity_liters': str(receipt.quantity_liters or total_liters) if (receipt.quantity_liters is not None or total_liters) else '',
        'batches': [_serialize_batch(batch) for batch in batches],
        'batch_count': len(batches),
        'approved_batch_count': len(approved_batches),
        'rejected_batch_count': len(rejected_batches),
        'pending_batch_count': len(pending_batches),
        'has_rejected_batches': has_rejected_batches,
        'has_pending_batches': has_pending_batches,
        'is_completed': receipt.is_completed,
        'is_locked': receipt.is_completed,
        'can_complete': _can_complete_receipt(receipt),
        'created_at': receipt.created_at.isoformat(),
        'completed_at': receipt.completed_at.isoformat() if receipt.completed_at else '',
    }


def _serialize_laboratory_analysis(analysis):
    batch = analysis.batch
    receipt = batch.receipt if batch else analysis.receipt
    return {
        'id': analysis.pk,
        'receipt': _serialize_receipt(receipt),
        'receipt_id': receipt.pk if receipt else None,
        'batch': _serialize_batch(batch) if batch else None,
        'batch_id': batch.pk if batch else None,
        'batch_sequence_number': batch.sequence_number if batch else None,
        'density': str(analysis.density) if analysis.density is not None else '',
        'flash_point_temperature': str(analysis.flash_point_temperature) if analysis.flash_point_temperature is not None else '',
        'current_temperature': str(analysis.current_temperature) if analysis.current_temperature is not None else '',
        'water_percentage': str(analysis.water_percentage) if analysis.water_percentage is not None else '',
        'is_filled': analysis.is_filled,
        'is_approved': analysis.is_approved,
        'is_rejected': analysis.is_rejected,
        'created_at': analysis.created_at.isoformat(),
        'decided_at': analysis.decided_at.isoformat() if analysis.decided_at else '',
    }


def _calculate_quantity_liters(batch, density=None):
    if batch.input_quantity is None:
        return None

    if density is None:
        analysis = _get_batch_laboratory_analysis(batch)
        if analysis is None or not analysis.is_approved:
            return None
        density = analysis.density if analysis else None

    if batch.input_unit == RawMaterialReceipt.UNIT_LITERS:
        return batch.input_quantity.quantize(Decimal('0.001'), rounding=ROUND_HALF_UP)

    if density is None or density <= 0:
        return None

    return (batch.input_quantity / density).quantize(Decimal('0.001'), rounding=ROUND_HALF_UP)


def _sync_batch_liters(batch, density=None):
    batch.quantity_liters = _calculate_quantity_liters(batch, density)
    batch.save(update_fields=['quantity_liters'])


def _sync_receipt_liters(receipt):
    approved_batch_ids = LaboratoryAnalysis.objects.filter(
        batch__receipt=receipt,
        is_approved=True,
        is_rejected=False,
    ).values_list('batch_id', flat=True)
    receipt.quantity_liters = receipt.batches.filter(pk__in=approved_batch_ids).aggregate(total=Sum('quantity_liters'))['total']
    receipt.save(update_fields=['quantity_liters'])


def _is_receipt_locked(receipt):
    return bool(receipt.is_completed)


def _can_complete_receipt(receipt):
    batches = list(receipt.batches.all())
    if not batches or receipt.is_completed:
        return False

    for batch in batches:
        analysis = _get_batch_laboratory_analysis(batch)
        if analysis is None or not (analysis.is_approved or analysis.is_rejected):
            return False
        if analysis.is_approved:
            if batch.input_quantity is None or batch.input_quantity <= 0:
                return False
            if _calculate_quantity_liters(batch, analysis.density) is None:
                return False
    return True


def _is_admin(user):
    if user.is_superuser or user.is_staff:
        return True

    profile, _ = UserProfile.objects.select_related('group').get_or_create(user=user)
    return profile.group is not None and profile.group.name == 'Администраторы'


def _require_admin(request):
    user, error = _require_auth(request)
    if error:
        return None, error
    if not _is_admin(user):
        return None, _permission_denied()
    return user, None


def _require_processing_permission(request, module_code, permission_code=None):
    user, error = _require_auth(request)
    if error:
        return None, error
    if _is_admin(user):
        return user, None

    required_permission = permission_code or _method_permission(request)
    if required_permission and not _has_permission(user, module_code, required_permission):
        return None, _permission_denied()
    return user, None


def _can_view_processing_container(user, kind):
    module_codes_by_kind = {
        ProductionContainer.KIND_RECEIVING_TANK: [MODULE_BOILER_LOADING],
        ProductionContainer.KIND_PREHEATING_BOILER: [MODULE_BOILER_LOADING, MODULE_SEPARATOR_LOADING],
        ProductionContainer.KIND_SEPARATOR: [
            MODULE_SEPARATOR_LOADING,
            MODULE_SEPARATOR_OUTPUT,
            MODULE_CHEMICAL_MIXER_LOADING,
        ],
        ProductionContainer.KIND_CHEMICAL_MIXER: [MODULE_CHEMICAL_MIXER_LOADING, MODULE_WORKSHOP_LOADING],
        ProductionContainer.KIND_PROCESSING_WORKSHOP: [
            MODULE_WORKSHOP_LOADING,
            MODULE_RAW_DIESEL_TANK_LOADING,
            MODULE_RAW_SPINDLE_TANK_LOADING,
        ],
        ProductionContainer.KIND_RAW_DIESEL_TANK: [MODULE_RAW_DIESEL_TANK_LOADING],
        ProductionContainer.KIND_RAW_SPINDLE_TANK: [MODULE_RAW_SPINDLE_TANK_LOADING],
    }
    for code, config in OIL_FINISHING_STEPS.items():
        if kind in config['sources'] + config['destinations']:
            module_codes_by_kind.setdefault(kind, []).append(code)
    manufacturing_access = {
        ProductionContainer.KIND_FINISHED_SPINDLE_TANK: ['concentrate-loading', 'oil-blending'],
        ProductionContainer.KIND_CONCENTRATE_REACTOR: ['concentrate-loading', 'oil-blending'],
        ProductionContainer.KIND_OIL_BLENDER: ['oil-blending', 'oil-tank-loading'],
        ProductionContainer.KIND_FINISHED_OIL_TANK: ['oil-tank-loading', 'oil-filling'],
    }
    module_codes_by_kind.setdefault(kind, []).extend(manufacturing_access.get(kind, []))
    return any(
        _has_permission(user, module_code, PERMISSION_VIEW)
        for module_code in module_codes_by_kind.get(kind, [])
    )


def _volume_value(value, allow_zero=False):
    decimal_value = _decimal_value(value)
    if decimal_value is None or not decimal_value.is_finite() or not Decimal('-99999999999.999') <= decimal_value <= Decimal('99999999999.999'):
        return None
    if decimal_value != decimal_value.quantize(VOLUME_QUANTUM):
        return None
    if allow_zero and decimal_value == 0:
        return decimal_value
    return decimal_value if decimal_value > 0 else None


def _capacity_value(value):
    decimal_value = _decimal_value(value)
    if decimal_value is None or not decimal_value.is_finite() or not 0 < decimal_value <= Decimal('99999999999') or decimal_value != decimal_value.to_integral_value():
        return None
    return decimal_value.quantize(VOLUME_QUANTUM)


def _audit_operation(action, object_type, object_id, user, changes=None, result=OperationAuditLog.RESULT_SUCCESS):
    return OperationAuditLog.objects.create(
        action=action,
        object_type=object_type,
        object_id=str(object_id or ''),
        user=user,
        result=result,
        changes=changes or {},
    )


def _movement_number():
    return f'MOV-{timezone.now():%Y%m%d%H%M%S}-{uuid4().hex[:8].upper()}'


def _container_code(kind, number):
    prefixes = {
        ProductionContainer.KIND_RECEIVING_TANK: 'receiving-tank',
        ProductionContainer.KIND_PREHEATING_BOILER: 'preheating-boiler',
        ProductionContainer.KIND_SEPARATOR: 'separator',
        ProductionContainer.KIND_CHEMICAL_MIXER: 'chemical-mixer',
        ProductionContainer.KIND_PROCESSING_WORKSHOP: 'processing-workshop',
        ProductionContainer.KIND_RAW_DIESEL_TANK: 'raw-diesel-tank',
        ProductionContainer.KIND_RAW_SPINDLE_TANK: 'raw-spindle-tank',
    }
    prefix = prefixes.get(kind, kind.replace('_', '-'))
    return f'{prefix}-{number}'


def _container_has_movements(container):
    return container.incoming_movements.exists() or container.outgoing_movements.exists() or container.oil_batches.exists() or container.sorbent_movements.exists()


def _serialize_container(container, user, raw_material_options=False):
    free_volume = container.capacity_liters - container.current_volume_liters
    base = {
        'id': container.pk,
        'kind': container.kind,
        'name': container.display_name,
        'number': container.number,
        'product_name': 'Отработанное масло',
        'is_active': container.is_active,
    }
    if raw_material_options:
        return {
            **base,
            'free_volume_liters': str(free_volume),
        }

    base['current_volume_liters'] = str(container.current_volume_liters)
    base['can_receive'] = container.is_active and free_volume > 0
    base['oil_grade_id'] = container.oil_grade_id
    base['grade_name'] = container.oil_grade.name if container.oil_grade_id else ''
    if container.kind in ProductionContainer.OIL_BATCH_KINDS:
        from .oil_manufacturing import _serialize_batch
        batch = container.oil_batches.filter(status=OilManufacturingBatch.STATUS_OPEN).select_related('equipment', 'created_by').first()
        base.update({
            'volume_known': False, 'current_volume_liters': None,
            'capacity_liters': str(container.capacity_liters),
            'active_batch': _serialize_batch(batch) if batch else None,
            'can_receive': container.is_active and batch is None,
        })
    if container.kind == ProductionContainer.KIND_FINISHED_OIL_TANK:
        base.update({'capacity_liters': str(container.capacity_liters), 'free_volume_liters': str(free_volume)})
    base['oil_product'] = container_oil_product(container)
    if container.kind in OIL_CONTAINER_PATHS.values():
        base['capacity_liters'] = str(container.capacity_liters)
        base['free_volume_liters'] = str(free_volume)
        base['product_name'] = dict(ProductionContainer.OIL_PRODUCTS).get(base['oil_product'], '')
    if _is_admin(user):
        last_movement = (
            MaterialMovement.objects
            .filter(Q(source_container=container) | Q(destination_container=container))
            .order_by('-moved_at', '-id')
            .first()
        )
        base.update({
            'system_code': container.system_code,
            'capacity_liters': str(container.capacity_liters),
            'free_volume_liters': str(free_volume),
            'fill_percentage': str(
                (container.current_volume_liters * Decimal('100') / container.capacity_liters).quantize(Decimal('0.01'))
            ),
            'last_movement_at': last_movement.moved_at.isoformat() if last_movement else '',
            'has_movements': _container_has_movements(container),
            'created_at': container.created_at.isoformat(),
            'updated_at': container.updated_at.isoformat(),
        })
        loading_types = {
            ProductionContainer.KIND_PREHEATING_BOILER: MaterialMovement.TYPE_TANK_TO_BOILER,
            ProductionContainer.KIND_SEPARATOR: MaterialMovement.TYPE_BOILER_TO_SEPARATOR,
            ProductionContainer.KIND_CHEMICAL_MIXER: MaterialMovement.TYPE_SEPARATOR_TO_CHEMICAL_MIXER,
            ProductionContainer.KIND_PROCESSING_WORKSHOP: MaterialMovement.TYPE_CHEMICAL_MIXER_TO_WORKSHOP,
            ProductionContainer.KIND_RAW_DIESEL_TANK: MaterialMovement.TYPE_WORKSHOP_TO_RAW_DIESEL_TANK,
            ProductionContainer.KIND_RAW_SPINDLE_TANK: MaterialMovement.TYPE_WORKSHOP_TO_RAW_SPINDLE_TANK,
        }
        for config in OIL_FINISHING_STEPS.values():
            for kind in config['destinations']:
                loading_types[kind] = config['movement_type']
        if container.kind in loading_types:
            base['recent_loadings'] = [
                _serialize_movement(movement)
                for movement in container.incoming_movements.filter(
                    movement_type=loading_types[container.kind],
                ).select_related('created_by').order_by('-moved_at', '-id')[:10]
            ]
    return base


def _serialize_movement(movement):
    return {
        'id': movement.pk,
        'entry_type': 'movement',
        'movement_number': movement.movement_number,
        'movement_type': movement.movement_type,
        'movement_type_label': movement.get_movement_type_display(),
        'status': movement.status,
        'status_label': movement.get_status_display(),
        'source': movement.source_snapshot,
        'destination': movement.destination_snapshot,
        'product_name': movement.product_name,
        'oil_product': movement.oil_product,
        'oil_grade_id': movement.oil_grade_id,
        'volume_liters': str(movement.volume_liters),
        'moved_at': movement.moved_at.isoformat(),
        'created_at': movement.created_at.isoformat(),
        'created_by': movement.created_by.get_username() if movement.created_by else '',
        'created_by_id': movement.created_by_id,
        'receipt_snapshot': movement.receipt_snapshot,
        'batch_snapshot': movement.batch_snapshot,
        'source_volume_before': str(movement.source_volume_before) if movement.source_volume_before is not None else '',
        'source_volume_after': str(movement.source_volume_after) if movement.source_volume_after is not None else '',
        'destination_volume_before': str(movement.destination_volume_before) if movement.destination_volume_before is not None else '',
        'destination_volume_after': str(movement.destination_volume_after) if movement.destination_volume_after is not None else '',
        'reason': movement.reason,
        'is_compensated': movement.is_compensated,
        'compensates_id': movement.compensates_id,
        'can_compensate': not movement.is_compensated and movement.compensates_id is None,
    }


def _serialize_audit_log(entry):
    return {
        'id': entry.pk,
        'entry_type': 'audit',
        'action': entry.action,
        'object_type': entry.object_type,
        'object_id': entry.object_id,
        'result': entry.result,
        'user': entry.user.get_username() if entry.user else '',
        'user_id': entry.user_id,
        'changes': entry.changes,
        'created_at': entry.created_at.isoformat(),
    }


def _overview_container_totals(kind):
    queryset = ProductionContainer.objects.filter(kind=kind, is_active=True)
    totals = queryset.aggregate(
        current_volume=Sum('current_volume_liters'),
        capacity=Sum('capacity_liters'),
    )
    current_volume = totals['current_volume'] or Decimal('0.000')
    capacity = totals['capacity'] or Decimal('0.000')
    fill_percentage = (
        (current_volume * Decimal('100') / capacity).quantize(Decimal('0.01'))
        if capacity > 0
        else Decimal('0.00')
    )
    return {
        'active_count': queryset.count(),
        'current_volume_liters': str(current_volume),
        'capacity_liters': str(capacity),
        'free_volume_liters': str(capacity - current_volume),
        'fill_percentage': str(fill_percentage),
    }


def _overview_container_items(kind, loading_type):
    containers = (
        ProductionContainer.objects
        .filter(kind=kind, is_active=True)
        .annotate(
            last_loading_at=Max(
                'incoming_movements__moved_at',
                filter=Q(incoming_movements__movement_type=loading_type),
            ),
        )
        .order_by('number')
    )
    items = []
    for container in containers:
        free_volume = container.capacity_liters - container.current_volume_liters
        fill_percentage = (
            container.current_volume_liters * Decimal('100') / container.capacity_liters
        ).quantize(Decimal('0.01'))
        items.append({
            'id': container.pk,
            'number': container.number,
            'name': container.display_name,
            'current_volume_liters': str(container.current_volume_liters),
            'capacity_liters': str(container.capacity_liters),
            'free_volume_liters': str(free_volume),
            'fill_percentage': str(fill_percentage),
            'last_loading_at': container.last_loading_at.isoformat() if container.last_loading_at else '',
        })
    return items



def _boolean_value(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ('1', 'true', 'yes', 'on')
    return bool(value)


def _validate_laboratory_values(values, require_all=False):
    if require_all and any(value is None for value in values.values()):
        return 'Все лабораторные показатели должны быть корректными числами.'
    if values.get('density') is not None and values['density'] <= 0:
        return 'Плотность должна быть больше нуля.'
    if values.get('water_percentage') is not None and not Decimal('0') <= values['water_percentage'] <= Decimal('100'):
        return 'Количество воды должно быть в диапазоне от 0 до 100%.'
    return None


def _sync_group_modules(group, module_ids, module_permissions=None):
    if module_ids is None:
        return
    if not isinstance(module_ids, list):
        raise ValueError('Module identifiers must be a list.')
    if module_permissions is not None and not isinstance(module_permissions, dict):
        raise ValueError('Module permissions must be an object.')

    modules = list(Module.objects.filter(pk__in=module_ids))
    if len(modules) != len(set(module_ids)):
        raise ValueError('One or more modules do not exist.')

    GroupModuleAccess.objects.filter(group=group).exclude(module_id__in=module_ids).delete()
    for module in modules:
        access, created = GroupModuleAccess.objects.get_or_create(group=group, module=module)
        permission_ids = None
        if module_permissions is not None:
            permission_ids = module_permissions.get(str(module.pk), module_permissions.get(module.pk, []))
        if permission_ids is not None:
            if not isinstance(permission_ids, list):
                raise ValueError('Permission identifiers must be lists.')
            permissions = list(Permission.objects.filter(pk__in=permission_ids))
            if len(permissions) != len(set(permission_ids)):
                raise ValueError('One or more permissions do not exist.')
            access.permissions.set(permissions)
        elif created and module.code in PROCESSING_FORM_MODULE_CODES:
            access.permissions.set(Permission.objects.filter(code__in=[PERMISSION_VIEW, PERMISSION_CREATE]))


def _sync_group_start_module(group, start_module_id):
    if start_module_id in (None, ''):
        group.start_module = None
        group.save(update_fields=['start_module'])
        return

    start_module = Module.objects.filter(pk=start_module_id).first()
    if start_module is None:
        raise ValueError('Start module does not exist.')

    if not GroupModuleAccess.objects.filter(group=group, module=start_module).exists():
        raise ValueError('Start module must be attached to the group.')

    group.start_module = start_module
    group.save(update_fields=['start_module'])


def _complete_receipt(receipt_id, user, distributions):
    with transaction.atomic():
        receipt = (
            RawMaterialReceipt.objects
            .select_for_update()
            .select_related('supplier')
            .prefetch_related('batches__laboratory_analysis')
            .get(pk=receipt_id)
        )
        if receipt.is_completed:
            return receipt, None
        if not _can_complete_receipt(receipt):
            return None, 'Receipt can be completed only after all batches have final laboratory decisions and approved batches have quantity.'

        approved_batches = []
        for batch in receipt.batches.all():
            analysis = _get_batch_laboratory_analysis(batch)
            if analysis and analysis.is_approved and not analysis.is_rejected:
                _sync_batch_liters(batch, analysis.density)
                approved_batches.append(batch)

        if not approved_batches:
            if distributions:
                return None, 'Tank distributions are not allowed when every batch is rejected.'
            _sync_receipt_liters(receipt)
            receipt.is_completed = True
            receipt.completed_at = timezone.now()
            receipt.save(update_fields=['is_completed', 'completed_at'])
            _audit_operation(
                'receipt_completed',
                'raw_material_receipt',
                receipt.pk,
                user,
                {'total_liters': '0.000', 'movements_created': 0},
            )
            return receipt, None

        if not isinstance(distributions, list):
            return None, 'Tank distributions are required for approved batches.'

        batch_map = {batch.pk: batch for batch in approved_batches}
        normalized = []
        seen_pairs = set()
        totals_by_batch = {batch.pk: Decimal('0.000') for batch in approved_batches}
        totals_by_container = {}
        container_ids = set()

        for item in distributions:
            if not isinstance(item, dict):
                return None, 'Each tank distribution must be an object.'
            try:
                batch_id = int(item.get('batch_id'))
                container_id = int(item.get('tank_id'))
            except (TypeError, ValueError):
                return None, 'Batch and tank identifiers are required.'
            volume = _volume_value(item.get('volume_liters'))
            if batch_id not in batch_map or volume is None:
                return None, 'Every distribution must reference an approved batch and a positive volume with up to three decimals.'
            pair = (batch_id, container_id)
            if pair in seen_pairs:
                return None, 'A batch can have only one distribution row per tank.'
            seen_pairs.add(pair)
            normalized.append((batch_id, container_id, volume))
            totals_by_batch[batch_id] += volume
            totals_by_container[container_id] = totals_by_container.get(container_id, Decimal('0.000')) + volume
            container_ids.add(container_id)

        for batch in approved_batches:
            if totals_by_batch[batch.pk] != batch.quantity_liters:
                return None, f'Distributed volume for batch #{batch.sequence_number} must equal {batch.quantity_liters} liters.'

        containers = {
            container.pk: container
            for container in ProductionContainer.objects.select_for_update().filter(pk__in=sorted(container_ids))
        }
        if len(containers) != len(container_ids):
            return None, 'One or more receiving tanks do not exist.'
        for container_id, requested_volume in totals_by_container.items():
            container = containers[container_id]
            if container.kind != ProductionContainer.KIND_RECEIVING_TANK or not container.is_active:
                return None, 'Only active receiving tanks can accept material.'
            if container.current_volume_liters + requested_volume > container.capacity_liters:
                return None, f'Переполнение бака: {container.display_name}.'

        for batch_id, container_id, volume in normalized:
            batch = batch_map[batch_id]
            container = containers[container_id]
            before = container.current_volume_liters
            after = before + volume
            movement = MaterialMovement.objects.create(
                movement_number=_movement_number(),
                movement_type=MaterialMovement.TYPE_RECEIPT_TO_TANK,
                destination_container=container,
                volume_liters=volume,
                created_by=user,
                receipt=receipt,
                receipt_batch=batch,
                source_event_key=f'receipt:{receipt.pk}:batch:{batch.pk}:tank:{container.pk}',
                source_snapshot='Приём сырья',
                destination_snapshot=container.display_name,
                receipt_snapshot=f'Приём #{receipt.pk}',
                batch_snapshot=f'Партия #{batch.sequence_number}',
                destination_volume_before=before,
                destination_volume_after=after,
                system_description='Автоматическое поступление после завершения приёма.',
            )
            container.current_volume_liters = after
            container.save(update_fields=['current_volume_liters', 'updated_at'])
            _audit_operation(
                'movement_created',
                'material_movement',
                movement.pk,
                user,
                {'movement_number': movement.movement_number, 'volume_liters': str(volume)},
            )

        _sync_receipt_liters(receipt)
        receipt.is_completed = True
        receipt.completed_at = timezone.now()
        receipt.save(update_fields=['is_completed', 'completed_at'])
        _audit_operation(
            'receipt_completed',
            'raw_material_receipt',
            receipt.pk,
            user,
            {'total_liters': str(receipt.quantity_liters or Decimal('0.000')), 'movements_created': len(normalized)},
        )
        return receipt, None


def _compensate_movement(movement_id, user, reason):
    with transaction.atomic():
        lock_oil_line()
        movement = (
            MaterialMovement.objects
            .select_for_update()
            .get(pk=movement_id)
        )
        if movement.is_compensated or movement.compensates_id is not None:
            return None, 'Movement has already been compensated or is itself a compensation.'
        if not reason.strip():
            return None, 'Compensation reason is required.'
        if movement.movement_type in MaterialMovement.OIL_MANUFACTURING_TYPES:
            from .oil_manufacturing import compensate_manufacturing_movement
            return compensate_manufacturing_movement(movement, user, reason)

        container_ids = sorted(filter(None, [movement.source_container_id, movement.destination_container_id]))
        containers = {
            container.pk: container
            for container in ProductionContainer.objects.select_for_update().filter(pk__in=container_ids)
        }
        source = containers.get(movement.source_container_id)
        destination = containers.get(movement.destination_container_id)
        compensation_source_before = None
        compensation_source_after = None
        compensation_destination_before = None
        compensation_destination_after = None

        if movement.movement_type in MaterialMovement.OIL_FINISHING_TYPES:
            if source is None or destination is None:
                return None, 'Production container not found.'
            error = oil_transfer_error(destination, source, movement.volume_liters, movement.oil_product)
            if error:
                return None, error
            compensation_source_before = destination.current_volume_liters
            compensation_source_after = compensation_source_before - movement.volume_liters
            compensation_destination_before = source.current_volume_liters
            compensation_destination_after = compensation_destination_before + movement.volume_liters
            apply_oil_transfer(destination, source, movement.volume_liters, movement.oil_product)
            compensation_source = destination
            compensation_destination = source
        elif movement.movement_type == MaterialMovement.TYPE_RECEIPT_TO_TANK:
            if destination is None or destination.current_volume_liters < movement.volume_liters:
                return None, 'Compensation would create a negative receiving tank balance.'
            compensation_source_before = destination.current_volume_liters
            compensation_source_after = compensation_source_before - movement.volume_liters
            destination.current_volume_liters = compensation_source_after
            destination.save(update_fields=['current_volume_liters', 'updated_at'])
            compensation_source = destination
            compensation_destination = None
        elif movement.movement_type in (
            MaterialMovement.TYPE_TANK_TO_BOILER,
            MaterialMovement.TYPE_BOILER_TO_SEPARATOR,
            MaterialMovement.TYPE_SEPARATOR_TO_CHEMICAL_MIXER,
            MaterialMovement.TYPE_CHEMICAL_MIXER_TO_WORKSHOP,
            MaterialMovement.TYPE_WORKSHOP_TO_RAW_DIESEL_TANK,
            MaterialMovement.TYPE_WORKSHOP_TO_RAW_SPINDLE_TANK,
        ):
            if destination is None or destination.current_volume_liters < movement.volume_liters:
                return None, 'Compensation would create a negative boiler balance.'
            if source is None or source.current_volume_liters + movement.volume_liters > source.capacity_liters:
                return None, 'Compensation would overflow the receiving tank.'
            compensation_source_before = destination.current_volume_liters
            compensation_source_after = compensation_source_before - movement.volume_liters
            compensation_destination_before = source.current_volume_liters
            compensation_destination_after = compensation_destination_before + movement.volume_liters
            destination.current_volume_liters = compensation_source_after
            source.current_volume_liters = compensation_destination_after
            destination.save(update_fields=['current_volume_liters', 'updated_at'])
            source.save(update_fields=['current_volume_liters', 'updated_at'])
            compensation_source = destination
            compensation_destination = source
        elif movement.movement_type == MaterialMovement.TYPE_SEPARATOR_OUTPUT:
            if source is None or source.current_volume_liters + movement.volume_liters > source.capacity_liters:
                return None, 'Compensation would overflow the separator.'
            compensation_destination_before = source.current_volume_liters
            compensation_destination_after = compensation_destination_before + movement.volume_liters
            source.current_volume_liters = compensation_destination_after
            source.save(update_fields=['current_volume_liters', 'updated_at'])
            compensation_source = None
            compensation_destination = source
        else:
            return None, 'Compensation movements cannot be compensated.'

        compensation = MaterialMovement.objects.create(
            movement_number=_movement_number(),
            movement_type=MaterialMovement.TYPE_COMPENSATION,
            source_container=compensation_source,
            destination_container=compensation_destination,
            product_name=movement.product_name,
            oil_product=movement.oil_product,
            volume_liters=movement.volume_liters,
            created_by=user,
            compensates=movement,
            idempotency_key=f'compensation:{movement.pk}',
            source_snapshot=movement.destination_snapshot,
            destination_snapshot=movement.source_snapshot,
            receipt_snapshot=movement.receipt_snapshot,
            batch_snapshot=movement.batch_snapshot,
            source_volume_before=compensation_source_before,
            source_volume_after=compensation_source_after,
            destination_volume_before=compensation_destination_before,
            destination_volume_after=compensation_destination_after,
            reason=reason.strip(),
            system_description=f'Компенсация движения {movement.movement_number}.',
        )
        movement.is_compensated = True
        movement.save(update_fields=['is_compensated'])
        _audit_operation(
            'movement_compensated',
            'material_movement',
            movement.pk,
            user,
            {
                'movement_number': movement.movement_number,
                'compensation_number': compensation.movement_number,
                'reason': reason.strip(),
            },
        )
        return compensation, None


def _compensate_receipt_movements_before_delete(movements, user, reason):
    movement_list = list(movements.select_related('destination_container'))
    destination_ids = {movement.destination_container_id for movement in movement_list if movement.destination_container_id}
    if MaterialMovement.objects.filter(
        source_container_id__in=destination_ids,
        movement_type=MaterialMovement.TYPE_TANK_TO_BOILER,
    ).exists():
        return 'Receipt or batch cannot be deleted after material has been transferred from its receiving tank.'

    for movement in movement_list:
        if movement.is_compensated:
            continue
        _, error = _compensate_movement(movement.pk, user, reason)
        if error:
            return error
    return None


@never_cache
@require_GET
def login_options_view(request):
    user_model = get_user_model()
    usernames = user_model.objects.filter(is_active=True).order_by(user_model.USERNAME_FIELD).values_list(user_model.USERNAME_FIELD, flat=True)
    return JsonResponse({'items': list(usernames)})


@csrf_exempt
@require_POST
def login_view(request):
    body = _json_body(request)
    if body is None:
        return _invalid_json_body()

    username = body.get('username')
    password = body.get('password')
    if not username or not password:
        return JsonResponse({'detail': 'Username and password are required.'}, status=400)

    user = authenticate(request, username=username, password=password)
    if user is None:
        return JsonResponse({'detail': 'Invalid username or password.'}, status=401)

    return JsonResponse({
        'access': create_access_token(user),
        'user': _serialize_current_user(user),
    })


@require_GET
def me_view(request):
    authorization = request.headers.get('Authorization', '')
    if not authorization.startswith('Bearer '):
        return JsonResponse({'detail': 'Bearer token is required.'}, status=401)

    token = authorization.removeprefix('Bearer ').strip()
    try:
        user = get_user_from_token(token)
    except get_user_model().DoesNotExist:
        return JsonResponse({'detail': 'User does not exist.'}, status=401)
    except jwt.PyJWTError:
        return JsonResponse({'detail': 'Invalid or expired token.'}, status=401)

    return JsonResponse({
        'message': f'Привет, {user.get_username()}!',
        'user': _serialize_current_user(user),
    })


@csrf_exempt
def access_users_view(request):
    user, error = _require_permission(request, MODULE_ACCESS)
    if error:
        return error

    user_model = get_user_model()
    if request.method == 'GET':
        users = user_model.objects.select_related('access_profile__group').order_by('username')
        return JsonResponse({'items': [_serialize_user(item) for item in users]})

    if request.method == 'POST':
        body = _json_body(request)
        if body is None:
            return _invalid_json_body()

        username = body.get('username', '').strip()
        password = body.get('password', '')
        if not username or not password:
            return JsonResponse({'detail': 'Username and password are required.'}, status=400)

        try:
            new_user = user_model.objects.create_user(
                username=username,
                password=password,
                first_name=body.get('first_name', '').strip(),
                last_name=body.get('last_name', '').strip(),
                email=body.get('email', '').strip(),
                is_active=body.get('is_active', True),
            )
        except IntegrityError:
            return JsonResponse({'detail': 'User with this username already exists.'}, status=400)

        profile, _ = UserProfile.objects.get_or_create(user=new_user)
        group_id = body.get('group_id')
        if group_id:
            profile.group = AccessGroup.objects.filter(pk=group_id).first()
            if profile.group is None:
                return JsonResponse({'detail': 'Group does not exist.'}, status=400)
            profile.save()

        return JsonResponse(_serialize_user(new_user), status=201)

    return _method_not_allowed()


@csrf_exempt
def access_user_detail_view(request, user_id):
    user, error = _require_permission(request, MODULE_ACCESS)
    if error:
        return error

    user_model = get_user_model()
    target = user_model.objects.filter(pk=user_id).first()
    if target is None:
        return JsonResponse({'detail': 'User not found.'}, status=404)

    if request.method == 'GET':
        return JsonResponse(_serialize_user(target))

    if request.method in ('PUT', 'PATCH'):
        body = _json_body(request)
        if body is None:
            return _invalid_json_body()

        for field in ('first_name', 'last_name', 'email'):
            if field in body:
                setattr(target, field, body.get(field, '').strip())
        if 'username' in body:
            target.username = body.get('username', '').strip()
        if 'is_active' in body:
            target.is_active = bool(body['is_active'])
        if body.get('password'):
            target.set_password(body['password'])

        try:
            target.save()
        except IntegrityError:
            return JsonResponse({'detail': 'User with this username already exists.'}, status=400)

        profile, _ = UserProfile.objects.get_or_create(user=target)
        if 'group_id' in body:
            group_id = body.get('group_id')
            if group_id:
                profile.group = AccessGroup.objects.filter(pk=group_id).first()
                if profile.group is None:
                    return JsonResponse({'detail': 'Group does not exist.'}, status=400)
            else:
                profile.group = None
            profile.save()

        return JsonResponse(_serialize_user(target))

    if request.method == 'DELETE':
        if target.pk == user.pk:
            return JsonResponse({'detail': 'You cannot delete your own user.'}, status=400)
        target.delete()
        return JsonResponse({'deleted': True})

    return _method_not_allowed()


@csrf_exempt
def access_groups_view(request):
    user, error = _require_permission(request, MODULE_ACCESS)
    if error:
        return error

    if request.method == 'GET':
        groups = AccessGroup.objects.select_related('start_module').prefetch_related('module_access__module', 'module_access__permissions')
        return JsonResponse({'items': [_serialize_group(group) for group in groups]})

    if request.method == 'POST':
        body = _json_body(request)
        if body is None:
            return _invalid_json_body()

        try:
            group = AccessGroup.objects.create(
                name=body.get('name', '').strip(),
                description=body.get('description', '').strip(),
            )
            _sync_group_modules(group, body.get('module_ids', []), body.get('module_permissions'))
            _sync_group_start_module(group, body.get('start_module_id'))
        except IntegrityError:
            return JsonResponse({'detail': 'Group with this name already exists.'}, status=400)
        except ValueError as exc:
            return JsonResponse({'detail': str(exc)}, status=400)

        return JsonResponse(_serialize_group(group), status=201)

    return _method_not_allowed()


@csrf_exempt
def access_group_detail_view(request, group_id):
    user, error = _require_permission(request, MODULE_ACCESS)
    if error:
        return error

    group = AccessGroup.objects.select_related('start_module').filter(pk=group_id).first()
    if group is None:
        return JsonResponse({'detail': 'Group not found.'}, status=404)

    if request.method == 'GET':
        return JsonResponse(_serialize_group(group))

    if request.method in ('PUT', 'PATCH'):
        body = _json_body(request)
        if body is None:
            return _invalid_json_body()

        if 'name' in body:
            group.name = body.get('name', '').strip()
        if 'description' in body:
            group.description = body.get('description', '').strip()

        try:
            group.save()
            _sync_group_modules(group, body.get('module_ids'), body.get('module_permissions'))
            if 'start_module_id' in body:
                _sync_group_start_module(group, body.get('start_module_id'))
        except IntegrityError:
            return JsonResponse({'detail': 'Group with this name already exists.'}, status=400)
        except ValueError as exc:
            return JsonResponse({'detail': str(exc)}, status=400)

        return JsonResponse(_serialize_group(group))

    if request.method == 'DELETE':
        group.delete()
        return JsonResponse({'deleted': True})

    return _method_not_allowed()


@csrf_exempt
def access_modules_view(request):
    user, error = _require_permission(request, MODULE_ACCESS)
    if error:
        return error

    if request.method == 'GET':
        return JsonResponse({'items': [_serialize_module(module) for module in Module.objects.all()]})

    if request.method == 'POST':
        body = _json_body(request)
        if body is None:
            return _invalid_json_body()

        try:
            module = Module.objects.create(
                code=body.get('code', '').strip(),
                name=body.get('name', '').strip(),
                description=body.get('description', '').strip(),
                default_path=body.get('default_path', '').strip(),
                is_active=body.get('is_active', True),
            )
        except IntegrityError:
            return JsonResponse({'detail': 'Module with this code already exists.'}, status=400)

        return JsonResponse(_serialize_module(module), status=201)

    return _method_not_allowed()


@csrf_exempt
def access_module_detail_view(request, module_id):
    user, error = _require_permission(request, MODULE_ACCESS)
    if error:
        return error

    module = Module.objects.filter(pk=module_id).first()
    if module is None:
        return JsonResponse({'detail': 'Module not found.'}, status=404)

    if request.method == 'GET':
        return JsonResponse(_serialize_module(module))

    if request.method in ('PUT', 'PATCH'):
        body = _json_body(request)
        if body is None:
            return _invalid_json_body()

        for field in ('code', 'name', 'description', 'default_path'):
            if field in body:
                setattr(module, field, body.get(field, '').strip())
        if 'is_active' in body:
            module.is_active = bool(body['is_active'])

        try:
            module.save()
        except IntegrityError:
            return JsonResponse({'detail': 'Module with this code already exists.'}, status=400)

        return JsonResponse(_serialize_module(module))

    if request.method == 'DELETE':
        module.delete()
        return JsonResponse({'deleted': True})

    return _method_not_allowed()


@csrf_exempt
def access_permissions_view(request):
    user, error = _require_permission(request, MODULE_ACCESS)
    if error:
        return error

    if request.method == 'GET':
        return JsonResponse({'items': [_serialize_permission(permission) for permission in Permission.objects.all()]})

    if request.method == 'POST':
        body = _json_body(request)
        if body is None:
            return _invalid_json_body()

        try:
            permission = Permission.objects.create(
                code=body.get('code', '').strip(),
                name=body.get('name', '').strip(),
                description=body.get('description', '').strip(),
            )
        except IntegrityError:
            return JsonResponse({'detail': 'Permission with this code already exists.'}, status=400)

        return JsonResponse(_serialize_permission(permission), status=201)

    return _method_not_allowed()


@csrf_exempt
def access_permission_detail_view(request, permission_id):
    user, error = _require_permission(request, MODULE_ACCESS)
    if error:
        return error

    permission = Permission.objects.filter(pk=permission_id).first()
    if permission is None:
        return JsonResponse({'detail': 'Permission not found.'}, status=404)

    if request.method == 'GET':
        return JsonResponse(_serialize_permission(permission))

    if request.method in ('PUT', 'PATCH'):
        body = _json_body(request)
        if body is None:
            return _invalid_json_body()

        for field in ('code', 'name', 'description'):
            if field in body:
                setattr(permission, field, body.get(field, '').strip())

        try:
            permission.save()
        except IntegrityError:
            return JsonResponse({'detail': 'Permission with this code already exists.'}, status=400)

        return JsonResponse(_serialize_permission(permission))

    if request.method == 'DELETE':
        permission.delete()
        return JsonResponse({'deleted': True})

    return _method_not_allowed()


@csrf_exempt
def directory_cities_view(request):
    _, error = _require_city_permission(request)
    if error:
        return error

    if request.method == 'GET':
        return JsonResponse({'items': [_serialize_city(city) for city in City.objects.all()]})

    if request.method == 'POST':
        body = _json_body(request)
        if body is None:
            return _invalid_json_body()

        name = body.get('name', '').strip()
        if not name:
            return JsonResponse({'detail': 'City name is required.'}, status=400)

        try:
            city = City.objects.create(name=name)
        except IntegrityError:
            return JsonResponse({'detail': 'City with this name already exists.'}, status=400)

        return JsonResponse(_serialize_city(city), status=201)

    return _method_not_allowed()


@csrf_exempt
def directory_city_detail_view(request, city_id):
    _, error = _require_city_permission(request)
    if error:
        return error

    city = City.objects.filter(pk=city_id).first()
    if city is None:
        return JsonResponse({'detail': 'City not found.'}, status=404)

    if request.method == 'GET':
        return JsonResponse(_serialize_city(city))

    if request.method in ('PUT', 'PATCH'):
        body = _json_body(request)
        if body is None:
            return _invalid_json_body()

        name = body.get('name', '').strip()
        if not name:
            return JsonResponse({'detail': 'City name is required.'}, status=400)

        city.name = name
        try:
            city.save()
        except IntegrityError:
            return JsonResponse({'detail': 'City with this name already exists.'}, status=400)

        return JsonResponse(_serialize_city(city))

    if request.method == 'DELETE':
        try:
            city.delete()
        except ProtectedError:
            return JsonResponse({'detail': 'City is used by suppliers and cannot be deleted.'}, status=400)
        return JsonResponse({'deleted': True})

    return _method_not_allowed()


@csrf_exempt
def directory_suppliers_view(request):
    _, error = _require_supplier_permission(request)
    if error:
        return error

    if request.method == 'GET':
        suppliers = Supplier.objects.select_related('city')
        return JsonResponse({'items': [_serialize_supplier(supplier) for supplier in suppliers]})

    if request.method == 'POST':
        body = _json_body(request)
        if body is None:
            return _invalid_json_body()

        company_name = body.get('company_name', '').strip()
        address = body.get('address', '').strip()
        phone = body.get('phone', '').strip()
        city_id = body.get('city_id')

        if not company_name or not city_id or not address or not phone:
            return JsonResponse({'detail': 'Company name, city, address and phone are required.'}, status=400)

        city = City.objects.filter(pk=city_id).first()
        if city is None:
            return JsonResponse({'detail': 'City does not exist.'}, status=400)

        supplier = Supplier.objects.create(
            company_name=company_name,
            city=city,
            address=address,
            phone=phone,
        )

        return JsonResponse(_serialize_supplier(supplier), status=201)

    return _method_not_allowed()


@csrf_exempt
def directory_supplier_detail_view(request, supplier_id):
    _, error = _require_supplier_permission(request)
    if error:
        return error

    supplier = Supplier.objects.select_related('city').filter(pk=supplier_id).first()
    if supplier is None:
        return JsonResponse({'detail': 'Supplier not found.'}, status=404)

    if request.method == 'GET':
        return JsonResponse(_serialize_supplier(supplier))

    if request.method in ('PUT', 'PATCH'):
        body = _json_body(request)
        if body is None:
            return _invalid_json_body()

        if 'company_name' in body:
            supplier.company_name = body.get('company_name', '').strip()
        if 'address' in body:
            supplier.address = body.get('address', '').strip()
        if 'phone' in body:
            supplier.phone = body.get('phone', '').strip()
        if 'city_id' in body:
            city = City.objects.filter(pk=body.get('city_id')).first()
            if city is None:
                return JsonResponse({'detail': 'City does not exist.'}, status=400)
            supplier.city = city

        if not supplier.company_name or not supplier.city_id or not supplier.address or not supplier.phone:
            return JsonResponse({'detail': 'Company name, city, address and phone are required.'}, status=400)

        supplier.save()
        return JsonResponse(_serialize_supplier(supplier))

    if request.method == 'DELETE':
        supplier.delete()
        return JsonResponse({'deleted': True})

    return _method_not_allowed()


@csrf_exempt
def raw_material_receipts_view(request):
    user, error = _require_permission(request, MODULE_RAW_MATERIAL)
    if error:
        return error

    if request.method == 'GET':
        receipts = RawMaterialReceipt.objects.select_related('supplier__city').prefetch_related('batches__laboratory_analysis')
        return JsonResponse({'items': [_serialize_receipt(receipt) for receipt in receipts]})

    if request.method == 'POST':
        body = _json_body(request)
        if body is None:
            return _invalid_json_body()

        supplier = Supplier.objects.select_related('city').filter(pk=body.get('supplier_id')).first()
        if supplier is None:
            return JsonResponse({'detail': 'Supplier does not exist.'}, status=400)

        if 'input_quantity' in body or 'input_unit' in body:
            return JsonResponse({'detail': 'Quantity can be set only after laboratory analysis approval.'}, status=400)

        receipt = RawMaterialReceipt.objects.create(supplier=supplier)
        batch = ReceiptBatch.objects.create(receipt=receipt, sequence_number=1)
        LaboratoryAnalysis.objects.create(batch=batch)
        _audit_operation(
            'receipt_created',
            'raw_material_receipt',
            receipt.pk,
            user,
            {'supplier_id': supplier.pk, 'batch_id': batch.pk},
        )
        _broadcast_operations_event(
            'receipt_created',
            {'receipt_id': receipt.pk, 'batch_id': batch.pk},
        )

        return JsonResponse(_serialize_receipt(receipt), status=201)

    return _method_not_allowed()


@csrf_exempt
def raw_material_receipt_detail_view(request, receipt_id):
    user, error = _require_permission(request, MODULE_RAW_MATERIAL)
    if error:
        return error

    receipt = RawMaterialReceipt.objects.select_related('supplier__city').prefetch_related('batches__laboratory_analysis').filter(pk=receipt_id).first()
    if receipt is None:
        return JsonResponse({'detail': 'Raw material receipt not found.'}, status=404)

    if request.method == 'GET':
        return JsonResponse(_serialize_receipt(receipt))

    if request.method in ('PUT', 'PATCH'):
        body = _json_body(request)
        if body is None:
            return _invalid_json_body()

        if _is_receipt_locked(receipt) and not _is_admin(user):
            return JsonResponse({'detail': 'Receipt is locked.'}, status=423)

        if body.get('is_completed'):
            completed_receipt, completion_error = _complete_receipt(receipt.pk, user, body.get('distributions'))
            if completion_error:
                return JsonResponse({'detail': completion_error}, status=400)
            _broadcast_operations_event(
                'receipt_completed',
                {'receipt_id': receipt.pk},
            )
            completed_receipt = (
                RawMaterialReceipt.objects
                .select_related('supplier__city')
                .prefetch_related('batches__laboratory_analysis')
                .get(pk=completed_receipt.pk)
            )
            return JsonResponse(_serialize_receipt(completed_receipt))

        if 'supplier_id' in body:
            if str(body.get('supplier_id')) != str(receipt.supplier_id):
                return JsonResponse({'detail': 'Supplier cannot be changed after receipt creation.'}, status=400)

        receipt.save()
        _broadcast_operations_event(
            'receipt_updated',
            {'receipt_id': receipt.pk},
        )
        return JsonResponse(_serialize_receipt(receipt))

    if request.method == 'DELETE':
        if _is_receipt_locked(receipt) and not _is_admin(user):
            return JsonResponse({'detail': 'Receipt is locked.'}, status=423)
        with transaction.atomic():
            movements = MaterialMovement.objects.filter(
                receipt=receipt,
                movement_type=MaterialMovement.TYPE_RECEIPT_TO_TANK,
            )
            compensation_error = _compensate_receipt_movements_before_delete(
                movements,
                user,
                f'Удаление приёма #{receipt.pk}.',
            )
            if compensation_error:
                return JsonResponse({'detail': compensation_error}, status=423)
            _audit_operation('receipt_deleted', 'raw_material_receipt', receipt.pk, user)
            deleted_receipt_id = receipt.pk
            receipt.delete()
        _broadcast_operations_event(
            'receipt_deleted',
            {'receipt_id': deleted_receipt_id},
        )
        return JsonResponse({'deleted': True})

    return _method_not_allowed()


@csrf_exempt
def raw_material_receipt_batches_view(request, receipt_id):
    user, error = _require_permission(request, MODULE_RAW_MATERIAL)
    if error:
        return error

    receipt = RawMaterialReceipt.objects.select_related('supplier__city').filter(pk=receipt_id).first()
    if receipt is None:
        return JsonResponse({'detail': 'Raw material receipt not found.'}, status=404)

    if request.method == 'GET':
        batches = receipt.batches.select_related('laboratory_analysis')
        return JsonResponse({'items': [_serialize_batch(batch) for batch in batches]})

    if request.method == 'POST':
        if receipt.is_completed:
            return JsonResponse({'detail': 'Receipt is completed.'}, status=423)

        next_sequence_number = (receipt.batches.aggregate(max_number=Max('sequence_number'))['max_number'] or 0) + 1
        batch = ReceiptBatch.objects.create(receipt=receipt, sequence_number=next_sequence_number)
        LaboratoryAnalysis.objects.create(batch=batch)
        _audit_operation(
            'receipt_batch_created',
            'receipt_batch',
            batch.pk,
            user,
            {'receipt_id': receipt.pk, 'sequence_number': batch.sequence_number},
        )
        _broadcast_operations_event(
            'batch_created',
            {'receipt_id': receipt.pk, 'batch_id': batch.pk},
        )
        return JsonResponse(_serialize_batch(batch), status=201)

    return _method_not_allowed()


@csrf_exempt
def raw_material_batch_detail_view(request, batch_id):
    user, error = _require_permission(request, MODULE_RAW_MATERIAL)
    if error:
        return error

    batch = ReceiptBatch.objects.select_related('receipt__supplier__city').filter(pk=batch_id).first()
    if batch is None:
        return JsonResponse({'detail': 'Receipt batch not found.'}, status=404)

    if request.method == 'GET':
        return JsonResponse(_serialize_batch(batch))

    if request.method in ('PUT', 'PATCH'):
        body = _json_body(request)
        if body is None:
            return _invalid_json_body()

        if batch.material_movements.filter(movement_type=MaterialMovement.TYPE_RECEIPT_TO_TANK).exists():
            return JsonResponse({'detail': 'Distributed batch cannot be changed.'}, status=423)

        if _is_batch_locked(batch) and not _is_admin(user):
            return JsonResponse({'detail': 'Batch is locked.'}, status=423)

        analysis = _get_batch_laboratory_analysis(batch)
        if analysis is None or not analysis.is_approved:
            return JsonResponse({'detail': 'Quantity can be set only after laboratory analysis approval.'}, status=400)

        if 'input_quantity' in body:
            input_quantity = _decimal_value(body.get('input_quantity'))
            if input_quantity is None or input_quantity <= 0:
                return JsonResponse({'detail': 'Quantity must be a positive number.'}, status=400)
            batch.input_quantity = input_quantity

        if 'input_unit' in body:
            input_unit = body.get('input_unit')
            if input_unit not in dict(RawMaterialReceipt.UNIT_CHOICES):
                return JsonResponse({'detail': 'Invalid quantity unit.'}, status=400)
            batch.input_unit = input_unit

        batch.save()
        _sync_batch_liters(batch)
        _sync_receipt_liters(batch.receipt)
        _audit_operation(
            'receipt_batch_updated',
            'receipt_batch',
            batch.pk,
            user,
            {
                'input_quantity': str(batch.input_quantity),
                'input_unit': batch.input_unit,
                'quantity_liters': str(batch.quantity_liters),
            },
        )
        _broadcast_operations_event(
            'batch_updated',
            {'receipt_id': batch.receipt_id, 'batch_id': batch.pk},
        )
        return JsonResponse(_serialize_batch(batch))

    if request.method == 'DELETE':
        if _is_batch_locked(batch) and not _is_admin(user):
            return JsonResponse({'detail': 'Batch is locked.'}, status=423)
        if batch.receipt.batches.count() <= 1:
            return JsonResponse({'detail': 'Receipt must have at least one batch.'}, status=400)
        with transaction.atomic():
            movements = MaterialMovement.objects.filter(
                receipt_batch=batch,
                movement_type=MaterialMovement.TYPE_RECEIPT_TO_TANK,
            )
            compensation_error = _compensate_receipt_movements_before_delete(
                movements,
                user,
                f'Удаление партии #{batch.sequence_number} приёма #{batch.receipt_id}.',
            )
            if compensation_error:
                return JsonResponse({'detail': compensation_error}, status=423)
            receipt_id = batch.receipt_id
            deleted_batch_id = batch.pk
            _audit_operation('receipt_batch_deleted', 'receipt_batch', batch.pk, user, {'receipt_id': receipt_id})
            batch.delete()
            _sync_receipt_liters(RawMaterialReceipt.objects.get(pk=receipt_id))
        _broadcast_operations_event(
            'batch_deleted',
            {'receipt_id': receipt_id, 'batch_id': deleted_batch_id},
        )
        return JsonResponse({'deleted': True})

    return _method_not_allowed()


@csrf_exempt
def laboratory_analyses_view(request):
    user, error = _require_permission(request, MODULE_LABORATORY)
    if error:
        return error

    if request.method == 'GET':
        analyses = LaboratoryAnalysis.objects.select_related('batch__receipt__supplier__city', 'receipt__supplier__city')
        return JsonResponse({'items': [_serialize_laboratory_analysis(analysis) for analysis in analyses]})

    if request.method == 'POST':
        return JsonResponse({'detail': 'Laboratory analysis is created automatically with receipt.'}, status=405)

    return _method_not_allowed()


@csrf_exempt
def laboratory_analysis_detail_view(request, analysis_id):
    user, error = _require_permission(request, MODULE_LABORATORY)
    if error:
        return error

    analysis = LaboratoryAnalysis.objects.select_related('batch__receipt__supplier__city', 'receipt__supplier__city').filter(pk=analysis_id).first()
    if analysis is None:
        return JsonResponse({'detail': 'Laboratory analysis not found.'}, status=404)

    if request.method == 'GET':
        return JsonResponse(_serialize_laboratory_analysis(analysis))

    if request.method in ('PUT', 'PATCH'):
        body = _json_body(request)
        if body is None:
            return _invalid_json_body()

        if analysis.batch and analysis.batch.material_movements.filter(
            movement_type=MaterialMovement.TYPE_RECEIPT_TO_TANK,
        ).exists():
            return JsonResponse({'detail': 'Analysis of a distributed batch cannot be changed.'}, status=423)

        if (analysis.is_approved or analysis.is_rejected) and not _is_admin(user):
            return JsonResponse({'detail': 'Laboratory analysis cannot be changed after status is set.'}, status=423)

        decision_fields = {'is_approved', 'is_rejected'}
        if decision_fields.intersection(body) and not _has_permission(user, MODULE_LABORATORY, PERMISSION_APPROVE):
            return _permission_denied()

        for field in ('density', 'flash_point_temperature', 'current_temperature', 'water_percentage'):
            if field in body:
                value = _decimal_value(body.get(field))
                setattr(analysis, field, value)

        if 'is_approved' in body:
            analysis.is_approved = _boolean_value(body.get('is_approved'))
            if analysis.is_approved:
                analysis.is_rejected = False
        if 'is_rejected' in body:
            analysis.is_rejected = _boolean_value(body.get('is_rejected'))
            if analysis.is_rejected:
                analysis.is_approved = False

        if decision_fields.intersection(body):
            analysis.decided_at = timezone.now() if analysis.is_approved or analysis.is_rejected else None

        values = {
            'density': analysis.density,
            'flash_point_temperature': analysis.flash_point_temperature,
            'current_temperature': analysis.current_temperature,
            'water_percentage': analysis.water_percentage,
        }
        validation_error = _validate_laboratory_values(values, require_all=analysis.is_approved)
        if validation_error:
            return JsonResponse({'detail': validation_error}, status=400)
        if analysis.is_approved and not analysis.is_filled:
            return JsonResponse({'detail': 'Laboratory analysis must be filled before approval.'}, status=400)

        analysis.save()
        if analysis.batch:
            _sync_batch_liters(analysis.batch, analysis.density if analysis.is_approved and not analysis.is_rejected else None)
            _sync_receipt_liters(analysis.batch.receipt)
        event_type = 'laboratory_decision_changed' if 'is_approved' in body or 'is_rejected' in body else 'laboratory_analysis_updated'
        _audit_operation(
            event_type,
            'laboratory_analysis',
            analysis.pk,
            user,
            {
                'receipt_id': analysis.batch.receipt_id if analysis.batch else analysis.receipt_id,
                'batch_id': analysis.batch_id,
                'is_approved': analysis.is_approved,
                'is_rejected': analysis.is_rejected,
            },
        )
        _broadcast_operations_event(
            event_type,
            {
                'analysis_id': analysis.pk,
                'receipt_id': analysis.batch.receipt_id if analysis.batch else analysis.receipt_id,
                'batch_id': analysis.batch_id,
                'is_approved': analysis.is_approved,
                'is_rejected': analysis.is_rejected,
            },
        )
        return JsonResponse(_serialize_laboratory_analysis(analysis))

    if request.method == 'DELETE':
        return JsonResponse({'detail': 'Laboratory analysis cannot be deleted separately from receipt.'}, status=405)

    return _method_not_allowed()


@transaction.atomic
def _production_containers_view(request, kind):
    user, error = _require_auth(request)
    if error:
        return error

    if request.method == 'GET':
        can_process = (
            _is_admin(user)
            or _has_permission(user, MODULE_USED_OIL_PROCESSING, PERMISSION_VIEW)
            or _can_view_processing_container(user, kind)
        )
        can_receive = kind == ProductionContainer.KIND_RECEIVING_TANK and _has_permission(user, MODULE_RAW_MATERIAL, PERMISSION_VIEW)
        if not can_process and not can_receive:
            return _permission_denied()

        containers = ProductionContainer.objects.filter(kind=kind).select_related('oil_grade')
        if not _is_admin(user):
            containers = containers.filter(is_active=True)
        raw_options = request.GET.get('purpose') == 'receipt' and can_receive
        return JsonResponse({'items': [_serialize_container(container, user, raw_options) for container in containers]})

    if not _is_admin(user):
        return _permission_denied()
    if request.method != 'POST':
        return _method_not_allowed()

    lock_oil_line()
    body = _json_body(request)
    if not isinstance(body, dict):
        return _invalid_json_body()
    try:
        number = int(body.get('number'))
    except (TypeError, ValueError):
        number = 0
    capacity = _capacity_value(body.get('capacity_liters'))
    if number <= 0 or capacity is None:
        return JsonResponse({'detail': 'Number and positive integer capacity are required.'}, status=400)

    oil_grade = None
    if kind == ProductionContainer.KIND_FINISHED_OIL_TANK:
        oil_grade = OilGrade.objects.filter(pk=body.get('oil_grade_id'), is_active=True).first() if type(body.get('oil_grade_id')) is int else None
        if oil_grade is None:
            return JsonResponse({'detail': 'Выберите активную марку масла.'}, status=400)

    try:
        container = ProductionContainer.objects.create(
            kind=kind,
            number=number,
            system_code=_container_code(kind, number),
            capacity_liters=capacity,
            oil_grade=oil_grade,
            is_active=_boolean_value(body.get('is_active', True)),
        )
    except IntegrityError:
        return JsonResponse({'detail': 'Container with this number already exists.'}, status=409)

    _audit_operation(
        'container_created',
        'production_container',
        container.pk,
        user,
        {'kind': kind, 'number': number, 'capacity_liters': str(capacity)},
    )
    return JsonResponse(_serialize_container(container, user), status=201)


@csrf_exempt
def receiving_tanks_view(request):
    return _production_containers_view(request, ProductionContainer.KIND_RECEIVING_TANK)


@csrf_exempt
def preheating_boilers_view(request):
    return _production_containers_view(request, ProductionContainer.KIND_PREHEATING_BOILER)


@csrf_exempt
def separators_view(request):
    return _production_containers_view(request, ProductionContainer.KIND_SEPARATOR)


@csrf_exempt
def chemical_mixers_view(request):
    return _production_containers_view(request, ProductionContainer.KIND_CHEMICAL_MIXER)


@csrf_exempt
def processing_workshops_view(request):
    return _production_containers_view(request, ProductionContainer.KIND_PROCESSING_WORKSHOP)


@csrf_exempt
def raw_diesel_tanks_view(request):
    return _production_containers_view(request, ProductionContainer.KIND_RAW_DIESEL_TANK)


@csrf_exempt
def raw_spindle_tanks_view(request):
    return _production_containers_view(request, ProductionContainer.KIND_RAW_SPINDLE_TANK)


@csrf_exempt
@transaction.atomic
def production_container_detail_view(request, container_id):
    user, error = _require_admin(request)
    if error:
        return error

    lock_oil_line()
    container = ProductionContainer.objects.select_for_update().filter(pk=container_id).first()
    if container is None:
        return JsonResponse({'detail': 'Production container not found.'}, status=404)
    if request.method == 'GET':
        return JsonResponse(_serialize_container(container, user))

    if request.method in ('PUT', 'PATCH'):
        body = _json_body(request)
        if not isinstance(body, dict):
            return _invalid_json_body()

        number = container.number
        capacity = container.capacity_liters
        is_active = container.is_active
        if 'number' in body:
            try:
                number = int(body.get('number'))
            except (TypeError, ValueError):
                number = 0
        if 'capacity_liters' in body:
            capacity = _capacity_value(body.get('capacity_liters'))
        if 'is_active' in body:
            is_active = _boolean_value(body.get('is_active'))

        if number <= 0 or capacity is None:
            return JsonResponse({'detail': 'Number and positive integer capacity are required.'}, status=400)
        if capacity < container.current_volume_liters:
            return JsonResponse({'detail': 'Вместимость не может быть меньше текущего объёма.'}, status=400)
        if not is_active and container.current_volume_liters > 0:
            return JsonResponse({'detail': 'Filled container cannot be deactivated.'}, status=400)
        if not is_active and container.kind == ProductionContainer.KIND_SORPTION_SYSTEM:
            from .sorbent import system_has_sorbent
            if system_has_sorbent(container.pk):
                return JsonResponse({'detail': 'Сначала верните весь сорбент системы и участка очистки в бак.'}, status=400)
        batch = container.oil_batches.filter(status=OilManufacturingBatch.STATUS_OPEN).first()
        if batch and (not is_active or capacity < max(batch.input_liters, batch.output_liters)):
            return JsonResponse({'detail': 'Нельзя отключить оборудование с открытой партией или уменьшить его вместимость ниже загрузки и выхода.'}, status=400)
        if container.kind == ProductionContainer.KIND_FINISHED_OIL_TANK and 'oil_grade_id' in body:
            grade = OilGrade.objects.filter(pk=body.get('oil_grade_id'), is_active=True).first() if type(body.get('oil_grade_id')) is int else None
            if grade is None:
                return JsonResponse({'detail': 'Выберите активную марку масла.'}, status=400)
            if grade.pk != container.oil_grade_id and container.current_volume_liters > 0:
                return JsonResponse({'detail': 'Нельзя изменить марку непустого бака.'}, status=400)
            container.oil_grade = grade

        old_values = {
            'number': container.number,
            'capacity_liters': str(container.capacity_liters),
            'is_active': container.is_active,
        }
        container.number = number
        container.system_code = _container_code(container.kind, number)
        container.capacity_liters = capacity
        container.is_active = is_active
        try:
            container.save()
        except IntegrityError:
            return JsonResponse({'detail': 'Container with this number already exists.'}, status=409)

        _audit_operation(
            'container_updated',
            'production_container',
            container.pk,
            user,
            {
                'before': old_values,
                'after': {
                    'number': container.number,
                    'capacity_liters': str(container.capacity_liters),
                    'is_active': container.is_active,
                },
            },
        )
        return JsonResponse(_serialize_container(container, user))

    if request.method == 'DELETE':
        if container.oil_batches.filter(status=OilManufacturingBatch.STATUS_OPEN).exists():
            return JsonResponse({'detail': 'Оборудование занято открытой партией.'}, status=400)
        if container.current_volume_liters > 0:
            return JsonResponse({'detail': 'Non-empty container cannot be deleted.'}, status=400)
        if _container_has_movements(container):
            return JsonResponse({'detail': 'Container with movement history can only be deactivated.'}, status=400)
        container_snapshot = container.display_name
        container.delete()
        _audit_operation(
            'container_deleted',
            'production_container',
            container_id,
            user,
            {'name': container_snapshot},
        )
        return JsonResponse({'deleted': True})

    return _method_not_allowed()


@csrf_exempt
def tank_to_boiler_movements_view(request):
    user, error = _require_processing_permission(request, MODULE_BOILER_LOADING, PERMISSION_CREATE)
    if error:
        return error
    if request.method != 'POST':
        return _method_not_allowed()

    body = _json_body(request)
    if body is None:
        return _invalid_json_body()
    try:
        source_id = int(body.get('source_tank_id'))
        destination_id = int(body.get('destination_boiler_id'))
    except (TypeError, ValueError):
        return JsonResponse({'detail': 'Source tank and destination boiler are required.'}, status=400)
    volume = _volume_value(body.get('volume_liters'))
    idempotency_key = str(body.get('idempotency_key') or '').strip()
    if volume is None:
        return JsonResponse({'detail': 'Volume must be positive and contain up to three decimal places.'}, status=400)
    if not idempotency_key or len(idempotency_key) > 80:
        return JsonResponse({'detail': 'Valid idempotency key is required.'}, status=400)

    existing = MaterialMovement.objects.filter(idempotency_key=idempotency_key).first()
    if existing:
        if existing.created_by_id != user.pk:
            return JsonResponse({'detail': 'Idempotency key is already used.'}, status=409)
        return JsonResponse(_serialize_movement(existing))

    with transaction.atomic():
        containers = {
            container.pk: container
            for container in ProductionContainer.objects.select_for_update().filter(pk__in=sorted([source_id, destination_id]))
        }
        source = containers.get(source_id)
        destination = containers.get(destination_id)
        existing = MaterialMovement.objects.filter(idempotency_key=idempotency_key).first()
        if existing:
            if existing.created_by_id != user.pk:
                return JsonResponse({'detail': 'Idempotency key is already used.'}, status=409)
            return JsonResponse(_serialize_movement(existing))
        if source is None or source.kind != ProductionContainer.KIND_RECEIVING_TANK or not source.is_active:
            return JsonResponse({'detail': 'Active receiving tank does not exist.'}, status=400)
        if destination is None or destination.kind != ProductionContainer.KIND_PREHEATING_BOILER or not destination.is_active:
            return JsonResponse({'detail': 'Active preheating boiler does not exist.'}, status=400)
        if source.current_volume_liters < volume:
            _audit_operation(
                'movement_rejected',
                'material_movement',
                '',
                user,
                {'reason': 'insufficient_source_volume', 'source_id': source_id, 'volume_liters': str(volume)},
                OperationAuditLog.RESULT_REJECTED,
            )
            return JsonResponse({'detail': 'Insufficient receiving tank volume.'}, status=400)
        if destination.current_volume_liters + volume > destination.capacity_liters:
            _audit_operation(
                'movement_rejected',
                'material_movement',
                '',
                user,
                {'reason': 'destination_overflow', 'destination_id': destination_id, 'volume_liters': str(volume)},
                OperationAuditLog.RESULT_REJECTED,
            )
            return JsonResponse({'detail': 'Boiler capacity would be exceeded.'}, status=400)

        source_before = source.current_volume_liters
        destination_before = destination.current_volume_liters
        source_after = source_before - volume
        destination_after = destination_before + volume
        try:
            with transaction.atomic():
                movement = MaterialMovement.objects.create(
                    movement_number=_movement_number(),
                    movement_type=MaterialMovement.TYPE_TANK_TO_BOILER,
                    source_container=source,
                    destination_container=destination,
                    volume_liters=volume,
                    created_by=user,
                    idempotency_key=idempotency_key,
                    source_snapshot=source.display_name,
                    destination_snapshot=destination.display_name,
                    source_volume_before=source_before,
                    source_volume_after=source_after,
                    destination_volume_before=destination_before,
                    destination_volume_after=destination_after,
                    system_description='Ручная загрузка котла из приёмного бака.',
                )
        except IntegrityError:
            existing = MaterialMovement.objects.filter(idempotency_key=idempotency_key).first()
            if existing and existing.created_by_id == user.pk:
                return JsonResponse(_serialize_movement(existing))
            return JsonResponse({'detail': 'Movement could not be created.'}, status=409)

        source.current_volume_liters = source_after
        destination.current_volume_liters = destination_after
        source.save(update_fields=['current_volume_liters', 'updated_at'])
        destination.save(update_fields=['current_volume_liters', 'updated_at'])
        _audit_operation(
            'movement_created',
            'material_movement',
            movement.pk,
            user,
            {'movement_number': movement.movement_number, 'volume_liters': str(volume)},
        )
        return JsonResponse(_serialize_movement(movement), status=201)


@csrf_exempt
def boiler_to_separator_movements_view(request):
    user, error = _require_processing_permission(request, MODULE_SEPARATOR_LOADING, PERMISSION_CREATE)
    if error:
        return error
    if request.method != 'POST':
        return _method_not_allowed()

    body = _json_body(request)
    if body is None:
        return _invalid_json_body()
    try:
        source_id = int(body.get('source_boiler_id'))
        destination_id = int(body.get('destination_separator_id'))
    except (TypeError, ValueError):
        return JsonResponse({'detail': 'Source boiler and destination separator are required.'}, status=400)
    volume = _volume_value(body.get('volume_liters'))
    idempotency_key = str(body.get('idempotency_key') or '').strip()
    if volume is None:
        return JsonResponse({'detail': 'Volume must be positive and contain up to three decimal places.'}, status=400)
    if not idempotency_key or len(idempotency_key) > 80:
        return JsonResponse({'detail': 'Valid idempotency key is required.'}, status=400)

    existing = MaterialMovement.objects.filter(idempotency_key=idempotency_key).first()
    if existing:
        if existing.created_by_id != user.pk:
            return JsonResponse({'detail': 'Idempotency key is already used.'}, status=409)
        return JsonResponse(_serialize_movement(existing))

    with transaction.atomic():
        containers = {
            container.pk: container
            for container in ProductionContainer.objects.select_for_update().filter(
                pk__in=sorted([source_id, destination_id]),
            )
        }
        source = containers.get(source_id)
        destination = containers.get(destination_id)
        existing = MaterialMovement.objects.filter(idempotency_key=idempotency_key).first()
        if existing:
            if existing.created_by_id != user.pk:
                return JsonResponse({'detail': 'Idempotency key is already used.'}, status=409)
            return JsonResponse(_serialize_movement(existing))
        if source is None or source.kind != ProductionContainer.KIND_PREHEATING_BOILER or not source.is_active:
            return JsonResponse({'detail': 'Active preheating boiler does not exist.'}, status=400)
        if destination is None or destination.kind != ProductionContainer.KIND_SEPARATOR or not destination.is_active:
            return JsonResponse({'detail': 'Active separator does not exist.'}, status=400)
        if source.current_volume_liters < volume:
            _audit_operation(
                'movement_rejected',
                'material_movement',
                '',
                user,
                {'reason': 'insufficient_source_volume', 'source_id': source_id, 'volume_liters': str(volume)},
                OperationAuditLog.RESULT_REJECTED,
            )
            return JsonResponse({'detail': 'Insufficient preheating boiler volume.'}, status=400)
        if destination.current_volume_liters + volume > destination.capacity_liters:
            _audit_operation(
                'movement_rejected',
                'material_movement',
                '',
                user,
                {'reason': 'destination_overflow', 'destination_id': destination_id, 'volume_liters': str(volume)},
                OperationAuditLog.RESULT_REJECTED,
            )
            return JsonResponse({'detail': 'Separator capacity would be exceeded.'}, status=400)

        source_before = source.current_volume_liters
        destination_before = destination.current_volume_liters
        source_after = source_before - volume
        destination_after = destination_before + volume
        try:
            with transaction.atomic():
                movement = MaterialMovement.objects.create(
                    movement_number=_movement_number(),
                    movement_type=MaterialMovement.TYPE_BOILER_TO_SEPARATOR,
                    source_container=source,
                    destination_container=destination,
                    volume_liters=volume,
                    created_by=user,
                    idempotency_key=idempotency_key,
                    source_snapshot=source.display_name,
                    destination_snapshot=destination.display_name,
                    source_volume_before=source_before,
                    source_volume_after=source_after,
                    destination_volume_before=destination_before,
                    destination_volume_after=destination_after,
                    system_description='Ручная загрузка сепаратора из котла первичного прогрева.',
                )
        except IntegrityError:
            existing = MaterialMovement.objects.filter(idempotency_key=idempotency_key).first()
            if existing and existing.created_by_id == user.pk:
                return JsonResponse(_serialize_movement(existing))
            return JsonResponse({'detail': 'Movement could not be created.'}, status=409)

        source.current_volume_liters = source_after
        destination.current_volume_liters = destination_after
        source.save(update_fields=['current_volume_liters', 'updated_at'])
        destination.save(update_fields=['current_volume_liters', 'updated_at'])
        _audit_operation(
            'movement_created',
            'material_movement',
            movement.pk,
            user,
            {'movement_number': movement.movement_number, 'volume_liters': str(volume)},
        )
        return JsonResponse(_serialize_movement(movement), status=201)


@csrf_exempt
def separator_output_movements_view(request):
    user, error = _require_processing_permission(request, MODULE_SEPARATOR_OUTPUT, PERMISSION_CREATE)
    if error:
        return error
    if request.method != 'POST':
        return _method_not_allowed()

    body = _json_body(request)
    if body is None:
        return _invalid_json_body()
    try:
        separator_id = int(body.get('source_separator_id'))
    except (TypeError, ValueError):
        return JsonResponse({'detail': 'Source separator is required.'}, status=400)
    products = {
        'water': MaterialMovement.PRODUCT_TECHNICAL_WATER,
        'technical_waste': MaterialMovement.PRODUCT_TECHNICAL_WASTE,
    }
    output_type = str(body.get('output_type') or '').strip()
    product_name = products.get(output_type)
    volume = _volume_value(body.get('volume_liters'))
    idempotency_key = str(body.get('idempotency_key') or '').strip()
    if product_name is None:
        return JsonResponse({'detail': 'Only technical water or technical waste can be shipped.'}, status=400)
    if volume is None:
        return JsonResponse({'detail': 'Volume must be positive and contain up to three decimal places.'}, status=400)
    if not idempotency_key or len(idempotency_key) > 80:
        return JsonResponse({'detail': 'Valid idempotency key is required.'}, status=400)

    existing = MaterialMovement.objects.filter(idempotency_key=idempotency_key).first()
    if existing:
        if existing.created_by_id != user.pk:
            return JsonResponse({'detail': 'Idempotency key is already used.'}, status=409)
        return JsonResponse(_serialize_movement(existing))

    with transaction.atomic():
        separator = (
            ProductionContainer.objects
            .select_for_update()
            .filter(pk=separator_id, kind=ProductionContainer.KIND_SEPARATOR, is_active=True)
            .first()
        )
        existing = MaterialMovement.objects.filter(idempotency_key=idempotency_key).first()
        if existing:
            if existing.created_by_id != user.pk:
                return JsonResponse({'detail': 'Idempotency key is already used.'}, status=409)
            return JsonResponse(_serialize_movement(existing))
        if separator is None:
            return JsonResponse({'detail': 'Active separator does not exist.'}, status=400)
        if separator.current_volume_liters < volume:
            _audit_operation(
                'movement_rejected',
                'material_movement',
                '',
                user,
                {'reason': 'insufficient_separator_volume', 'separator_id': separator_id, 'volume_liters': str(volume)},
                OperationAuditLog.RESULT_REJECTED,
            )
            return JsonResponse({'detail': 'Insufficient separator volume.'}, status=400)

        source_before = separator.current_volume_liters
        source_after = source_before - volume
        try:
            with transaction.atomic():
                movement = MaterialMovement.objects.create(
                    movement_number=_movement_number(),
                    movement_type=MaterialMovement.TYPE_SEPARATOR_OUTPUT,
                    source_container=separator,
                    product_name=product_name,
                    volume_liters=volume,
                    created_by=user,
                    idempotency_key=idempotency_key,
                    source_snapshot=separator.display_name,
                    destination_snapshot=product_name,
                    source_volume_before=source_before,
                    source_volume_after=source_after,
                    system_description=f'Ручная отгрузка из сепаратора: {product_name}.',
                )
        except IntegrityError:
            existing = MaterialMovement.objects.filter(idempotency_key=idempotency_key).first()
            if existing and existing.created_by_id == user.pk:
                return JsonResponse(_serialize_movement(existing))
            return JsonResponse({'detail': 'Movement could not be created.'}, status=409)

        separator.current_volume_liters = source_after
        separator.save(update_fields=['current_volume_liters', 'updated_at'])
        _audit_operation(
            'movement_created',
            'material_movement',
            movement.pk,
            user,
            {
                'movement_number': movement.movement_number,
                'product_name': product_name,
                'volume_liters': str(volume),
            },
        )
        return JsonResponse(_serialize_movement(movement), status=201)


@csrf_exempt
def separator_to_chemical_mixer_movements_view(request):
    user, error = _require_processing_permission(request, MODULE_CHEMICAL_MIXER_LOADING, PERMISSION_CREATE)
    if error:
        return error
    if request.method != 'POST':
        return _method_not_allowed()

    body = _json_body(request)
    if body is None:
        return _invalid_json_body()
    try:
        source_id = int(body.get('source_separator_id'))
        destination_id = int(body.get('destination_mixer_id'))
    except (TypeError, ValueError):
        return JsonResponse({'detail': 'Source separator and destination chemical mixer are required.'}, status=400)
    volume = _volume_value(body.get('volume_liters'))
    idempotency_key = str(body.get('idempotency_key') or '').strip()
    if volume is None:
        return JsonResponse({'detail': 'Volume must be positive and contain up to three decimal places.'}, status=400)
    if not idempotency_key or len(idempotency_key) > 80:
        return JsonResponse({'detail': 'Valid idempotency key is required.'}, status=400)

    existing = MaterialMovement.objects.filter(idempotency_key=idempotency_key).first()
    if existing:
        if existing.created_by_id != user.pk:
            return JsonResponse({'detail': 'Idempotency key is already used.'}, status=409)
        return JsonResponse(_serialize_movement(existing))

    with transaction.atomic():
        containers = {
            container.pk: container
            for container in ProductionContainer.objects.select_for_update().filter(
                pk__in=sorted([source_id, destination_id]),
            )
        }
        source = containers.get(source_id)
        destination = containers.get(destination_id)
        existing = MaterialMovement.objects.filter(idempotency_key=idempotency_key).first()
        if existing:
            if existing.created_by_id != user.pk:
                return JsonResponse({'detail': 'Idempotency key is already used.'}, status=409)
            return JsonResponse(_serialize_movement(existing))
        if source is None or source.kind != ProductionContainer.KIND_SEPARATOR or not source.is_active:
            return JsonResponse({'detail': 'Active separator does not exist.'}, status=400)
        if destination is None or destination.kind != ProductionContainer.KIND_CHEMICAL_MIXER or not destination.is_active:
            return JsonResponse({'detail': 'Active chemical mixer does not exist.'}, status=400)
        if source.current_volume_liters < volume:
            _audit_operation(
                'movement_rejected',
                'material_movement',
                '',
                user,
                {'reason': 'insufficient_separator_volume', 'source_id': source_id, 'volume_liters': str(volume)},
                OperationAuditLog.RESULT_REJECTED,
            )
            return JsonResponse({'detail': 'Insufficient separator volume.'}, status=400)
        if destination.current_volume_liters + volume > destination.capacity_liters:
            _audit_operation(
                'movement_rejected',
                'material_movement',
                '',
                user,
                {'reason': 'chemical_mixer_overflow', 'destination_id': destination_id, 'volume_liters': str(volume)},
                OperationAuditLog.RESULT_REJECTED,
            )
            return JsonResponse({'detail': 'Chemical mixer capacity would be exceeded.'}, status=400)

        source_before = source.current_volume_liters
        destination_before = destination.current_volume_liters
        source_after = source_before - volume
        destination_after = destination_before + volume
        try:
            with transaction.atomic():
                movement = MaterialMovement.objects.create(
                    movement_number=_movement_number(),
                    movement_type=MaterialMovement.TYPE_SEPARATOR_TO_CHEMICAL_MIXER,
                    source_container=source,
                    destination_container=destination,
                    product_name='Очищенное отработанное масло',
                    volume_liters=volume,
                    created_by=user,
                    idempotency_key=idempotency_key,
                    source_snapshot=source.display_name,
                    destination_snapshot=destination.display_name,
                    source_volume_before=source_before,
                    source_volume_after=source_after,
                    destination_volume_before=destination_before,
                    destination_volume_after=destination_after,
                    system_description='Ручная загрузка химического миксера из сепаратора.',
                )
        except IntegrityError:
            existing = MaterialMovement.objects.filter(idempotency_key=idempotency_key).first()
            if existing and existing.created_by_id == user.pk:
                return JsonResponse(_serialize_movement(existing))
            return JsonResponse({'detail': 'Movement could not be created.'}, status=409)

        source.current_volume_liters = source_after
        destination.current_volume_liters = destination_after
        source.save(update_fields=['current_volume_liters', 'updated_at'])
        destination.save(update_fields=['current_volume_liters', 'updated_at'])
        _audit_operation(
            'movement_created',
            'material_movement',
            movement.pk,
            user,
            {'movement_number': movement.movement_number, 'volume_liters': str(volume)},
        )
        return JsonResponse(_serialize_movement(movement), status=201)


@csrf_exempt
def chemical_mixer_to_workshop_movements_view(request):
    user, error = _require_processing_permission(request, MODULE_WORKSHOP_LOADING, PERMISSION_CREATE)
    if error:
        return error
    if request.method != 'POST':
        return _method_not_allowed()

    body = _json_body(request)
    if body is None:
        return _invalid_json_body()
    try:
        source_id = int(body.get('source_mixer_id'))
        destination_id = int(body.get('destination_workshop_id'))
    except (TypeError, ValueError):
        return JsonResponse({'detail': 'Source chemical mixer and destination processing workshop are required.'}, status=400)
    volume = _volume_value(body.get('volume_liters'))
    idempotency_key = str(body.get('idempotency_key') or '').strip()
    if volume is None:
        return JsonResponse({'detail': 'Volume must be positive and contain up to three decimal places.'}, status=400)
    if not idempotency_key or len(idempotency_key) > 80:
        return JsonResponse({'detail': 'Valid idempotency key is required.'}, status=400)

    existing = MaterialMovement.objects.filter(idempotency_key=idempotency_key).first()
    if existing:
        if existing.created_by_id != user.pk:
            return JsonResponse({'detail': 'Idempotency key is already used.'}, status=409)
        return JsonResponse(_serialize_movement(existing))

    with transaction.atomic():
        containers = {
            container.pk: container
            for container in ProductionContainer.objects.select_for_update().filter(
                pk__in=sorted([source_id, destination_id]),
            )
        }
        source = containers.get(source_id)
        destination = containers.get(destination_id)
        existing = MaterialMovement.objects.filter(idempotency_key=idempotency_key).first()
        if existing:
            if existing.created_by_id != user.pk:
                return JsonResponse({'detail': 'Idempotency key is already used.'}, status=409)
            return JsonResponse(_serialize_movement(existing))
        if source is None or source.kind != ProductionContainer.KIND_CHEMICAL_MIXER or not source.is_active:
            return JsonResponse({'detail': 'Active chemical mixer does not exist.'}, status=400)
        if destination is None or destination.kind != ProductionContainer.KIND_PROCESSING_WORKSHOP or not destination.is_active:
            return JsonResponse({'detail': 'Active processing workshop does not exist.'}, status=400)
        if source.current_volume_liters < volume:
            _audit_operation(
                'movement_rejected',
                'material_movement',
                '',
                user,
                {'reason': 'insufficient_chemical_mixer_volume', 'source_id': source_id, 'volume_liters': str(volume)},
                OperationAuditLog.RESULT_REJECTED,
            )
            return JsonResponse({'detail': 'В химическом миксере недостаточно сырья.'}, status=400)
        if destination.current_volume_liters + volume > destination.capacity_liters:
            _audit_operation(
                'movement_rejected',
                'material_movement',
                '',
                user,
                {'reason': 'processing_workshop_overflow', 'destination_id': destination_id, 'volume_liters': str(volume)},
                OperationAuditLog.RESULT_REJECTED,
            )
            return JsonResponse({'detail': 'Processing workshop capacity would be exceeded.'}, status=400)

        source_before = source.current_volume_liters
        destination_before = destination.current_volume_liters
        source_after = source_before - volume
        destination_after = destination_before + volume
        try:
            with transaction.atomic():
                movement = MaterialMovement.objects.create(
                    movement_number=_movement_number(),
                    movement_type=MaterialMovement.TYPE_CHEMICAL_MIXER_TO_WORKSHOP,
                    source_container=source,
                    destination_container=destination,
                    product_name='Химически подготовленное масло',
                    volume_liters=volume,
                    created_by=user,
                    idempotency_key=idempotency_key,
                    source_snapshot=source.display_name,
                    destination_snapshot=destination.display_name,
                    source_volume_before=source_before,
                    source_volume_after=source_after,
                    destination_volume_before=destination_before,
                    destination_volume_after=destination_after,
                    system_description='Ручная загрузка цеха переработки из химического миксера.',
                )
        except IntegrityError:
            existing = MaterialMovement.objects.filter(idempotency_key=idempotency_key).first()
            if existing and existing.created_by_id == user.pk:
                return JsonResponse(_serialize_movement(existing))
            return JsonResponse({'detail': 'Movement could not be created.'}, status=409)

        source.current_volume_liters = source_after
        destination.current_volume_liters = destination_after
        source.save(update_fields=['current_volume_liters', 'updated_at'])
        destination.save(update_fields=['current_volume_liters', 'updated_at'])
        _audit_operation(
            'movement_created',
            'material_movement',
            movement.pk,
            user,
            {'movement_number': movement.movement_number, 'volume_liters': str(volume)},
        )
        return JsonResponse(_serialize_movement(movement), status=201)


def _workshop_to_raw_tank_movement_view(request, module_code, destination_kind, movement_type, product_name):
    user, error = _require_processing_permission(request, module_code, PERMISSION_CREATE)
    if error:
        return error
    if request.method != 'POST':
        return _method_not_allowed()

    body = _json_body(request)
    if body is None:
        return _invalid_json_body()
    try:
        source_id = int(body.get('source_workshop_id'))
        destination_id = int(body.get('destination_tank_id'))
    except (TypeError, ValueError):
        return JsonResponse({'detail': 'Source processing workshop and destination tank are required.'}, status=400)
    volume = _volume_value(body.get('volume_liters'))
    idempotency_key = str(body.get('idempotency_key') or '').strip()
    if volume is None:
        return JsonResponse({'detail': 'Volume must be positive and contain up to three decimal places.'}, status=400)
    if not idempotency_key or len(idempotency_key) > 80:
        return JsonResponse({'detail': 'Valid idempotency key is required.'}, status=400)

    existing = MaterialMovement.objects.filter(idempotency_key=idempotency_key).first()
    if existing:
        if existing.created_by_id != user.pk:
            return JsonResponse({'detail': 'Idempotency key is already used.'}, status=409)
        return JsonResponse(_serialize_movement(existing))

    with transaction.atomic():
        containers = {
            container.pk: container
            for container in ProductionContainer.objects.select_for_update().filter(
                pk__in=sorted([source_id, destination_id]),
            )
        }
        source = containers.get(source_id)
        destination = containers.get(destination_id)
        existing = MaterialMovement.objects.filter(idempotency_key=idempotency_key).first()
        if existing:
            if existing.created_by_id != user.pk:
                return JsonResponse({'detail': 'Idempotency key is already used.'}, status=409)
            return JsonResponse(_serialize_movement(existing))
        if source is None or source.kind != ProductionContainer.KIND_PROCESSING_WORKSHOP or not source.is_active:
            return JsonResponse({'detail': 'Active processing workshop does not exist.'}, status=400)
        if destination is None or destination.kind != destination_kind or not destination.is_active:
            return JsonResponse({'detail': 'Active destination tank does not exist.'}, status=400)
        if source.current_volume_liters < volume:
            _audit_operation(
                'movement_rejected',
                'material_movement',
                '',
                user,
                {'reason': 'insufficient_processing_workshop_volume', 'source_id': source_id, 'volume_liters': str(volume)},
                OperationAuditLog.RESULT_REJECTED,
            )
            return JsonResponse({'detail': 'Insufficient processing workshop volume.'}, status=400)
        if destination.current_volume_liters + volume > destination.capacity_liters:
            _audit_operation(
                'movement_rejected',
                'material_movement',
                '',
                user,
                {'reason': 'raw_product_tank_overflow', 'destination_id': destination_id, 'volume_liters': str(volume)},
                OperationAuditLog.RESULT_REJECTED,
            )
            return JsonResponse({'detail': 'Destination tank capacity would be exceeded.'}, status=400)

        source_before = source.current_volume_liters
        destination_before = destination.current_volume_liters
        source_after = source_before - volume
        destination_after = destination_before + volume
        try:
            with transaction.atomic():
                movement = MaterialMovement.objects.create(
                    movement_number=_movement_number(),
                    movement_type=movement_type,
                    source_container=source,
                    destination_container=destination,
                    product_name=product_name,
                    volume_liters=volume,
                    created_by=user,
                    idempotency_key=idempotency_key,
                    source_snapshot=source.display_name,
                    destination_snapshot=destination.display_name,
                    source_volume_before=source_before,
                    source_volume_after=source_after,
                    destination_volume_before=destination_before,
                    destination_volume_after=destination_after,
                    system_description=f'Ручная загрузка из цеха переработки: {product_name}.',
                )
        except IntegrityError:
            existing = MaterialMovement.objects.filter(idempotency_key=idempotency_key).first()
            if existing and existing.created_by_id == user.pk:
                return JsonResponse(_serialize_movement(existing))
            return JsonResponse({'detail': 'Movement could not be created.'}, status=409)

        source.current_volume_liters = source_after
        destination.current_volume_liters = destination_after
        source.save(update_fields=['current_volume_liters', 'updated_at'])
        destination.save(update_fields=['current_volume_liters', 'updated_at'])
        _audit_operation(
            'movement_created',
            'material_movement',
            movement.pk,
            user,
            {
                'movement_number': movement.movement_number,
                'product_name': product_name,
                'volume_liters': str(volume),
            },
        )
        return JsonResponse(_serialize_movement(movement), status=201)


@csrf_exempt
def workshop_to_raw_diesel_tank_movements_view(request):
    return _workshop_to_raw_tank_movement_view(
        request,
        MODULE_RAW_DIESEL_TANK_LOADING,
        ProductionContainer.KIND_RAW_DIESEL_TANK,
        MaterialMovement.TYPE_WORKSHOP_TO_RAW_DIESEL_TANK,
        'Сырая солярка',
    )


@csrf_exempt
def workshop_to_raw_spindle_tank_movements_view(request):
    return _workshop_to_raw_tank_movement_view(
        request,
        MODULE_RAW_SPINDLE_TANK_LOADING,
        ProductionContainer.KIND_RAW_SPINDLE_TANK,
        MaterialMovement.TYPE_WORKSHOP_TO_RAW_SPINDLE_TANK,
        'Сырая веретенка',
    )


@csrf_exempt
def compensate_movement_view(request, movement_id):
    user, error = _require_admin(request)
    if error:
        return error
    if request.method != 'POST':
        return _method_not_allowed()
    body = _json_body(request)
    if body is None:
        return _invalid_json_body()
    try:
        compensation, compensation_error = _compensate_movement(movement_id, user, str(body.get('reason') or ''))
    except MaterialMovement.DoesNotExist:
        return JsonResponse({'detail': 'Movement not found.'}, status=404)
    if compensation_error:
        return JsonResponse({'detail': compensation_error}, status=400)
    return JsonResponse(_serialize_movement(compensation), status=201)


@require_GET
def processing_journal_view(request):
    user, error = _require_admin(request)
    if error:
        return error

    movements = MaterialMovement.objects.select_related('created_by').all()
    audits = OperationAuditLog.objects.select_related('user').all()
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    movement_type = request.GET.get('movement_type')
    status = request.GET.get('status')
    source = request.GET.get('source')
    destination = request.GET.get('destination')
    username = request.GET.get('user')
    movement_number = request.GET.get('number')
    volume = _volume_value(request.GET.get('volume')) if request.GET.get('volume') else None
    query = request.GET.get('query', '').strip()

    if date_from:
        movements = movements.filter(moved_at__date__gte=date_from)
        audits = audits.filter(created_at__date__gte=date_from)
    if date_to:
        movements = movements.filter(moved_at__date__lte=date_to)
        audits = audits.filter(created_at__date__lte=date_to)
    if movement_type:
        movements = movements.filter(movement_type=movement_type)
        audits = audits.none()
    if status:
        movements = movements.filter(status=status)
        audits = audits.filter(result=status)
    if source:
        movements = movements.filter(source_snapshot__icontains=source)
        audits = audits.none()
    if destination:
        movements = movements.filter(destination_snapshot__icontains=destination)
        audits = audits.none()
    if username:
        movements = movements.filter(created_by__username__icontains=username)
        audits = audits.filter(user__username__icontains=username)
    if movement_number:
        movements = movements.filter(movement_number__icontains=movement_number)
        audits = audits.none()
    if volume is not None:
        movements = movements.filter(volume_liters=volume)
        audits = audits.none()
    if query:
        movements = movements.filter(
            Q(movement_number__icontains=query)
            | Q(source_snapshot__icontains=query)
            | Q(destination_snapshot__icontains=query)
            | Q(created_by__username__icontains=query)
        )
        audits = audits.filter(
            Q(action__icontains=query)
            | Q(object_type__icontains=query)
            | Q(object_id__icontains=query)
            | Q(user__username__icontains=query)
        )

    items = [_serialize_movement(item) for item in movements] + [_serialize_audit_log(item) for item in audits]
    items.sort(key=lambda item: item.get('moved_at') or item.get('created_at'), reverse=True)
    try:
        page = max(int(request.GET.get('page', 1)), 1)
        page_size = min(max(int(request.GET.get('page_size', 10)), 1), 100)
    except (TypeError, ValueError):
        return JsonResponse({'detail': 'Invalid pagination parameters.'}, status=400)
    total = len(items)
    page_count = max((total + page_size - 1) // page_size, 1)
    if page > page_count:
        page = page_count
    start = (page - 1) * page_size
    return JsonResponse({
        'items': items[start:start + page_size],
        'total': total,
        'page': page,
        'page_size': page_size,
        'page_count': page_count,
    })


@require_GET
def production_overview_view(request):
    from .oil_processing import oil_overview
    from .oil_manufacturing import manufacturing_overview
    from .sorbent import sorbent_overview
    _, error = _require_processing_permission(request, MODULE_DASHBOARD, PERMISSION_VIEW)
    if error:
        return error

    today = timezone.localdate()
    completed_today = RawMaterialReceipt.objects.filter(
        is_completed=True,
        completed_at__date=today,
    )
    accepted_today = completed_today.aggregate(total=Sum('quantity_liters'))['total'] or Decimal('0.000')
    completed_count = completed_today.count()
    receiving_tanks = _overview_container_totals(ProductionContainer.KIND_RECEIVING_TANK)
    preheating_boilers = _overview_container_totals(ProductionContainer.KIND_PREHEATING_BOILER)
    separators = _overview_container_totals(ProductionContainer.KIND_SEPARATOR)
    chemical_mixers = _overview_container_totals(ProductionContainer.KIND_CHEMICAL_MIXER)
    chemical_mixer_items = _overview_container_items(
        ProductionContainer.KIND_CHEMICAL_MIXER,
        MaterialMovement.TYPE_SEPARATOR_TO_CHEMICAL_MIXER,
    )
    processing_workshops = _overview_container_totals(ProductionContainer.KIND_PROCESSING_WORKSHOP)
    processing_workshop_items = _overview_container_items(
        ProductionContainer.KIND_PROCESSING_WORKSHOP,
        MaterialMovement.TYPE_CHEMICAL_MIXER_TO_WORKSHOP,
    )
    raw_diesel_tanks = _overview_container_totals(ProductionContainer.KIND_RAW_DIESEL_TANK)
    raw_spindle_tanks = _overview_container_totals(ProductionContainer.KIND_RAW_SPINDLE_TANK)
    last_tank_movement = MaterialMovement.objects.filter(
        destination_container__kind=ProductionContainer.KIND_RECEIVING_TANK,
    ).order_by('-moved_at', '-id').first()
    last_boiler_loading = MaterialMovement.objects.filter(
        movement_type=MaterialMovement.TYPE_TANK_TO_BOILER,
    ).order_by('-moved_at', '-id').first()
    last_separator_loading = MaterialMovement.objects.filter(
        movement_type=MaterialMovement.TYPE_BOILER_TO_SEPARATOR,
    ).order_by('-moved_at', '-id').first()
    last_raw_diesel_loading = MaterialMovement.objects.filter(
        movement_type=MaterialMovement.TYPE_WORKSHOP_TO_RAW_DIESEL_TANK,
    ).order_by('-moved_at', '-id').first()
    last_raw_spindle_loading = MaterialMovement.objects.filter(
        movement_type=MaterialMovement.TYPE_WORKSHOP_TO_RAW_SPINDLE_TANK,
    ).order_by('-moved_at', '-id').first()

    return JsonResponse({
        'reception': {
            'accepted_today_liters': str(accepted_today),
            'completed_today_count': completed_count,
            'open_receipt_count': RawMaterialReceipt.objects.filter(is_completed=False).count(),
            'average_receipt_liters': str(
                (accepted_today / completed_count).quantize(VOLUME_QUANTUM)
                if completed_count
                else Decimal('0.000')
            ),
        },
        'receiving_tanks': {
            **receiving_tanks,
            'last_movement_at': last_tank_movement.moved_at.isoformat() if last_tank_movement else '',
        },
        'preheating_boilers': {
            **preheating_boilers,
            'last_loading_at': last_boiler_loading.moved_at.isoformat() if last_boiler_loading else '',
        },
        'separators': {
            **separators,
            'last_loading_at': last_separator_loading.moved_at.isoformat() if last_separator_loading else '',
        },
        'chemical_mixers': {
            **chemical_mixers,
            'items': chemical_mixer_items,
        },
        'processing_workshops': {
            **processing_workshops,
            'items': processing_workshop_items,
        },
        'raw_diesel_tanks': {
            **raw_diesel_tanks,
            'last_loading_at': last_raw_diesel_loading.moved_at.isoformat() if last_raw_diesel_loading else '',
        },
        'raw_spindle_tanks': {
            **raw_spindle_tanks,
            'last_loading_at': last_raw_spindle_loading.moved_at.isoformat() if last_raw_spindle_loading else '',
        },
        'packaging_production': _packaging_production_overview(),
        'oil_finishing': oil_overview(),
        'oil_manufacturing': manufacturing_overview(),
        'sorbent_cycle': sorbent_overview(),
        'updated_at': timezone.now().isoformat(),
    })


WAREHOUSE_DOCUMENT_PERMISSIONS = {
    WarehouseDocument.TYPE_RECEIPT: PERMISSION_RECEIPT,
    WarehouseDocument.TYPE_ISSUE: PERMISSION_ISSUE,
    WarehouseDocument.TYPE_TRANSFER: PERMISSION_TRANSFER,
    WarehouseDocument.TYPE_INVENTORY: PERMISSION_INVENTORY,
}

WAREHOUSE_DOCUMENT_PREFIXES = {
    'production-output': 'ВЫП',
    WarehouseDocument.TYPE_RECEIPT: 'ПРХ',
    WarehouseDocument.TYPE_ISSUE: 'РСХ',
    WarehouseDocument.TYPE_TRANSFER: 'ПРМ',
    WarehouseDocument.TYPE_INVENTORY: 'ИНВ',
}


def _serialize_inventory_category(category):
    return {'id': category.pk, 'name': category.name, 'is_active': category.is_active}


def _serialize_unit(unit):
    return {
        'id': unit.pk,
        'name': unit.name,
        'symbol': unit.symbol,
        'decimal_places': unit.decimal_places,
        'is_active': unit.is_active,
    }


def _serialize_inventory_item(item):
    return {
        'id': item.pk,
        'name': item.name,
        'category_id': item.category_id,
        'category': _serialize_inventory_category(item.category),
        'unit_id': item.unit_id,
        'unit': _serialize_unit(item.unit),
        'last_purchase_price': str(item.last_purchase_price),
        'production_material': item.production_material,
        'production_material_label': item.get_production_material_display(),
        'production_product': item.production_product,
        'production_product_label': item.get_production_product_display(),
        'is_active': item.is_active,
    }


def _serialize_warehouse(warehouse):
    return {
        'id': warehouse.pk,
        'name': warehouse.name,
        'description': warehouse.description,
        'is_active': warehouse.is_active,
    }


def _serialize_production_item(item):
    return {
        'id': item.pk, 'name': item.name, 'unit_id': item.unit_id, 'unit': _serialize_unit(item.unit),
        'category_id': item.category_id, 'category': _serialize_inventory_category(item.category),
        'production_material': item.production_material, 'production_product': item.production_product,
        'is_active': item.is_active,
    }


def _serialize_warehouse_balance(balance):
    return {
        'id': balance.pk,
        'warehouse': _serialize_warehouse(balance.warehouse),
        'item': _serialize_inventory_item(balance.item),
        'quantity': str(balance.quantity),
        'average_unit_cost': str(balance.average_unit_cost),
        'total_value': str((balance.quantity * balance.average_unit_cost).quantize(Decimal('0.01'))),
        'updated_at': balance.updated_at.isoformat(),
    }


def _serialize_warehouse_document_line(line):
    return {
        'id': line.pk,
        'item_id': line.item_id,
        'item': _serialize_inventory_item(line.item),
        'quantity': str(line.quantity),
        'unit_price': str(line.unit_price) if line.unit_price is not None else '',
        'line_total': str((line.quantity * line.unit_price).quantize(Decimal('0.01'))) if line.unit_price is not None else '',
    }


def _serialize_warehouse_document(document):
    lines = list(document.lines.all())
    return {
        'id': document.pk,
        'number': document.number,
        'document_type': document.document_type,
        'document_type_label': document.get_document_type_display(),
        'status': document.status,
        'status_label': document.get_status_display(),
        'document_date': document.document_date.isoformat(),
        'source_warehouse_id': document.source_warehouse_id,
        'source_warehouse': _serialize_warehouse(document.source_warehouse) if document.source_warehouse else None,
        'destination_warehouse_id': document.destination_warehouse_id,
        'destination_warehouse': _serialize_warehouse(document.destination_warehouse) if document.destination_warehouse else None,
        'supplier_id': document.supplier_id,
        'supplier': _serialize_supplier(document.supplier) if document.supplier else None,
        'purpose': document.purpose,
        'production_target': document.production_target,
        'production_target_label': document.get_production_target_display(),
        'created_by': document.created_by.get_username() if document.created_by else '',
        'posted_by': document.posted_by.get_username() if document.posted_by else '',
        'confirmed_by': document.confirmed_by.get_username() if document.confirmed_by else '',
        'created_at': document.created_at.isoformat(),
        'posted_at': document.posted_at.isoformat() if document.posted_at else '',
        'confirmed_at': document.confirmed_at.isoformat() if document.confirmed_at else '',
        'cancelled_at': document.cancelled_at.isoformat() if document.cancelled_at else '',
        'lines': [_serialize_warehouse_document_line(line) for line in lines],
        'total_value': str(sum(
            (line.quantity * line.unit_price for line in lines if line.unit_price is not None),
            Decimal('0.00'),
        ).quantize(Decimal('0.01'))),
    }


def _warehouse_document_date(value):
    if not value:
        return timezone.now()
    parsed = parse_datetime(str(value))
    if parsed is None:
        return None
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed


def _warehouse_quantity(value, unit, allow_zero=False):
    quantity = _decimal_value(value)
    if quantity is None or quantity < 0 or (quantity == 0 and not allow_zero):
        return None
    quantum = Decimal('1').scaleb(-unit.decimal_places)
    if quantity != quantity.quantize(quantum):
        return None
    return quantity.quantize(Decimal('0.01'))


def _warehouse_price(value):
    price = _decimal_value(value)
    if price is None or price < 0:
        return None
    return price.quantize(Decimal('0.01'))


def _next_warehouse_document_number(document_type, document_date):
    year = timezone.localtime(document_date).year
    WarehouseDocumentSequence.objects.get_or_create(document_type=document_type, year=year)
    sequence = WarehouseDocumentSequence.objects.select_for_update().get(
        document_type=document_type,
        year=year,
    )
    sequence.last_number += 1
    sequence.save(update_fields=['last_number'])
    return f'{WAREHOUSE_DOCUMENT_PREFIXES[document_type]}-{year}-{sequence.last_number:06d}'


def _warehouse_header_error(document_type, source_warehouse, destination_warehouse, supplier):
    if document_type == WarehouseDocument.TYPE_RECEIPT:
        if destination_warehouse is None or supplier is None:
            return 'Для поступления необходимо выбрать склад и поставщика.'
    elif document_type in (WarehouseDocument.TYPE_ISSUE, WarehouseDocument.TYPE_INVENTORY):
        if source_warehouse is None:
            return 'Необходимо выбрать склад.'
    elif document_type == WarehouseDocument.TYPE_TRANSFER:
        if source_warehouse is None or destination_warehouse is None:
            return 'Для перемещения необходимо выбрать оба склада.'
        if source_warehouse.pk == destination_warehouse.pk:
            return 'Склад-источник и склад-получатель должны отличаться.'
    else:
        return 'Неизвестный тип складского документа.'
    return None


def _parse_warehouse_document_lines(raw_lines, document_type):
    if not isinstance(raw_lines, list) or not raw_lines:
        return None, 'Добавьте хотя бы одну строку документа.'
    item_ids = []
    for raw_line in raw_lines:
        try:
            item_ids.append(int(raw_line.get('item_id')))
        except (AttributeError, TypeError, ValueError):
            return None, 'В каждой строке должна быть выбрана номенклатура.'
    if len(item_ids) != len(set(item_ids)):
        return None, 'Номенклатура не должна повторяться в одном документе.'

    items = {
        item.pk: item
        for item in InventoryItem.objects.select_related('category', 'unit').filter(pk__in=item_ids, is_active=True)
    }
    if len(items) != len(item_ids):
        return None, 'Одна или несколько позиций номенклатуры не найдены или неактивны.'

    lines = []
    for raw_line, item_id in zip(raw_lines, item_ids):
        item = items[item_id]
        quantity = _warehouse_quantity(
            raw_line.get('quantity'),
            item.unit,
            allow_zero=document_type == WarehouseDocument.TYPE_INVENTORY,
        )
        if quantity is None:
            return None, f'Количество для «{item.name}» не соответствует точности единицы измерения.'
        unit_price = None
        if document_type == WarehouseDocument.TYPE_RECEIPT:
            unit_price = _warehouse_price(raw_line.get('unit_price'))
            if unit_price is None:
                return None, f'Укажите корректную цену для «{item.name}».'
        lines.append({'item': item, 'quantity': quantity, 'unit_price': unit_price})
    return lines, None


def _locked_warehouse_balance(warehouse, item):
    WarehouseBalance.objects.get_or_create(warehouse=warehouse, item=item)
    return WarehouseBalance.objects.select_for_update().get(warehouse=warehouse, item=item)


def _add_to_warehouse_balance(balance, quantity, unit_cost):
    current_value = balance.quantity * balance.average_unit_cost
    incoming_value = quantity * unit_cost
    new_quantity = balance.quantity + quantity
    balance.quantity = new_quantity
    balance.average_unit_cost = (
        ((current_value + incoming_value) / new_quantity).quantize(Decimal('0.01'))
        if new_quantity > 0
        else Decimal('0.00')
    )
    balance.save(update_fields=['quantity', 'average_unit_cost', 'updated_at'])


def _remove_from_warehouse_balance(balance, quantity):
    if balance.quantity < quantity:
        raise ValueError(f'Недостаточный остаток позиции «{balance.item.name}» на складе «{balance.warehouse.name}».')
    unit_cost = balance.average_unit_cost
    balance.quantity -= quantity
    if balance.quantity == 0:
        balance.average_unit_cost = Decimal('0.00')
    balance.save(update_fields=['quantity', 'average_unit_cost', 'updated_at'])
    return unit_cost


def _create_warehouse_movement(document, warehouse, item, movement_type, quantity_delta, unit_cost, user):
    WarehouseMovement.objects.create(
        document=document,
        warehouse=warehouse,
        item=item,
        movement_type=movement_type,
        quantity_delta=quantity_delta,
        unit_cost=unit_cost,
        total_value_delta=(quantity_delta * unit_cost).quantize(Decimal('0.01')),
        created_by=user,
    )


def _warehouse_settings_view(request, model, serializer, fields):
    user, error = _require_auth(request)
    if error:
        return error
    permission_code = _method_permission(request)
    if permission_code is None:
        return _method_not_allowed()
    if not (_is_admin(user) or _has_permission(user, MODULE_WAREHOUSE_SETTINGS, permission_code)):
        return _permission_denied()
    if request.method == 'GET':
        queryset = model.objects.all()
        if model is InventoryItem:
            queryset = queryset.select_related('category', 'unit')
        return JsonResponse({'items': [serializer(item) for item in queryset]})
    if request.method != 'POST':
        return _method_not_allowed()
    body = _json_body(request)
    if body is None:
        return _invalid_json_body()
    try:
        values = fields(body, None)
        instance = model.objects.create(**values)
        if model is InventoryItem:
            instance = InventoryItem.objects.select_related('category', 'unit').get(pk=instance.pk)
    except (IntegrityError, ValueError, TypeError) as exc:
        return JsonResponse({'detail': str(exc) or 'Не удалось создать запись.'}, status=400)
    return JsonResponse(serializer(instance), status=201)


def _warehouse_settings_detail_view(request, item_id, model, serializer, fields):
    user, error = _require_auth(request)
    if error:
        return error
    permission_code = _method_permission(request)
    if permission_code is None:
        return _method_not_allowed()
    if not (_is_admin(user) or _has_permission(user, MODULE_WAREHOUSE_SETTINGS, permission_code)):
        return _permission_denied()
    queryset = model.objects.all()
    if model is InventoryItem:
        queryset = queryset.select_related('category', 'unit')
    instance = queryset.filter(pk=item_id).first()
    if instance is None:
        return JsonResponse({'detail': 'Запись не найдена.'}, status=404)
    if request.method == 'GET':
        return JsonResponse(serializer(instance))
    if request.method in ('PUT', 'PATCH'):
        body = _json_body(request)
        if body is None:
            return _invalid_json_body()
        try:
            for field, value in fields(body, instance).items():
                setattr(instance, field, value)
            instance.save()
            if model is InventoryItem:
                instance = InventoryItem.objects.select_related('category', 'unit').get(pk=instance.pk)
        except (IntegrityError, ValueError, TypeError) as exc:
            return JsonResponse({'detail': str(exc) or 'Не удалось сохранить запись.'}, status=400)
        return JsonResponse(serializer(instance))
    if request.method == 'DELETE':
        try:
            if model is Warehouse and instance.permanent_items.exists():
                return JsonResponse({'detail': 'Склад используется для постоянного хранения производственных материалов.'}, status=400)
            instance.delete()
        except ProtectedError:
            return JsonResponse({'detail': 'Запись используется и не может быть удалена.'}, status=400)
        return JsonResponse({'deleted': True})
    return _method_not_allowed()


def _category_fields(body, instance):
    name = str(body.get('name', instance.name if instance else '')).strip()
    if not name:
        raise ValueError('Название категории обязательно.')
    return {'name': name, 'is_active': _boolean_value(body.get('is_active', instance.is_active if instance else True))}


def _unit_fields(body, instance):
    name = str(body.get('name', instance.name if instance else '')).strip()
    symbol = str(body.get('symbol', instance.symbol if instance else '')).strip()
    try:
        decimal_places = int(body.get('decimal_places', instance.decimal_places if instance else 0))
    except (TypeError, ValueError):
        decimal_places = -1
    if not name or not symbol or decimal_places not in (0, 1, 2):
        raise ValueError('Укажите название, обозначение и точность единицы измерения.')
    if instance and instance.items.exclude(production_material='').exists():
        if symbol.lower() not in ('кг', 'kg') or not _boolean_value(body.get('is_active', instance.is_active)):
            raise ValueError('Для производственных материалов необходимо сохранить активную единицу кг.')
        if decimal_places != instance.decimal_places and instance.items.filter(warehouse_movements__document__production_target__gt='').exists():
            raise ValueError('Нельзя изменить точность единицы после производственных загрузок.')
    if instance and instance.items.exclude(production_product='').exists():
        if decimal_places != 0 or symbol.lower() not in ('шт', 'шт.', 'pcs', 'dona') or not _boolean_value(body.get('is_active', instance.is_active)):
            raise ValueError('Для выпуска упаковки выберите целую единицу измерения в штуках.')
    return {
        'name': name,
        'symbol': symbol,
        'decimal_places': decimal_places,
        'is_active': _boolean_value(body.get('is_active', instance.is_active if instance else True)),
    }


def _inventory_item_fields(body, instance):
    name = str(body.get('name', instance.name if instance else '')).strip()
    category_id = body.get('category_id', instance.category_id if instance else None)
    unit_id = body.get('unit_id', instance.unit_id if instance else None)
    category = InventoryCategory.objects.filter(pk=category_id, is_active=True).first()
    unit = UnitOfMeasure.objects.filter(pk=unit_id, is_active=True).first()
    if not name or category is None or unit is None:
        raise ValueError('Укажите название, категорию и единицу измерения.')
    return {
        'name': name,
        'category': category,
        'unit': unit,
        'is_active': _boolean_value(body.get('is_active', instance.is_active if instance else True)),
    }


def _warehouse_fields(body, instance):
    name = str(body.get('name', instance.name if instance else '')).strip()
    if not name:
        raise ValueError('Название склада обязательно.')
    if instance and instance.permanent_items.exists() and not _boolean_value(body.get('is_active', instance.is_active)):
        raise ValueError('Склад используется для постоянного хранения производственных материалов.')
    return {
        'name': name,
        'description': str(body.get('description', instance.description if instance else '')).strip(),
        'is_active': _boolean_value(body.get('is_active', instance.is_active if instance else True)),
    }


@csrf_exempt
def inventory_categories_view(request):
    return _warehouse_settings_view(request, InventoryCategory, _serialize_inventory_category, _category_fields)


@csrf_exempt
def inventory_category_detail_view(request, category_id):
    return _warehouse_settings_detail_view(
        request, category_id, InventoryCategory, _serialize_inventory_category, _category_fields,
    )


@csrf_exempt
def units_of_measure_view(request):
    return _warehouse_settings_view(request, UnitOfMeasure, _serialize_unit, _unit_fields)


@csrf_exempt
def unit_of_measure_detail_view(request, unit_id):
    return _warehouse_settings_detail_view(request, unit_id, UnitOfMeasure, _serialize_unit, _unit_fields)


@csrf_exempt
def inventory_items_view(request):
    return _inventory_items_endpoint(request)


@csrf_exempt
def inventory_item_detail_view(request, item_id):
    return _inventory_items_endpoint(request, item_id)


def _serialize_inventory_settings_item(item):
    return {
        **_serialize_inventory_item(item),
        'permanent_warehouse_ids': [warehouse.pk for warehouse in item.permanent_warehouses.all()],
    }


def _inventory_items_endpoint(request, item_id=None):
    user, error = _require_auth(request)
    if error:
        return error
    permission_code = _method_permission(request)
    if permission_code is None:
        return _method_not_allowed()
    if not (_is_admin(user) or _has_permission(user, MODULE_WAREHOUSE_SETTINGS, permission_code)):
        return _permission_denied()
    queryset = InventoryItem.objects.select_related('category', 'unit').prefetch_related('permanent_warehouses')
    if request.method == 'GET':
        if item_id is None:
            return JsonResponse({'items': [_serialize_inventory_settings_item(item) for item in queryset]})
        item = queryset.filter(pk=item_id).first()
        return JsonResponse(_serialize_inventory_settings_item(item)) if item else JsonResponse(
            {'detail': 'Запись не найдена.'}, status=404,
        )
    if (item_id is None and request.method != 'POST') or (item_id is not None and request.method == 'POST'):
        return _method_not_allowed()
    body = _json_body(request) if request.method != 'DELETE' else {}
    if not isinstance(body, dict):
        return _invalid_json_body()
    try:
        with transaction.atomic():
            item = InventoryItem.objects.select_for_update().filter(pk=item_id).first() if item_id else None
            if item_id and item is None:
                return JsonResponse({'detail': 'Запись не найдена.'}, status=404)
            if request.method == 'DELETE':
                if item.production_material:
                    raise ValueError('Постоянную производственную позицию нельзя удалить. Сначала измените её назначение.')
                item.delete()
                return JsonResponse({'deleted': True})
            values = _inventory_item_fields(body, item)
            material = body.get('production_material', item.production_material if item else '')
            product = body.get('production_product', item.production_product if item else '')
            if material not in dict(InventoryItem.MATERIAL_CHOICES):
                raise ValueError('Выберите корректное назначение материала.')
            if product not in dict(InventoryItem.PRODUCT_CHOICES) or (product and material):
                raise ValueError('Выберите только одно назначение: сырьё или выпускаемая упаковка.')
            if product and (values['unit'].decimal_places != 0 or values['unit'].symbol.lower() not in ('шт', 'шт.', 'pcs', 'dona')):
                raise ValueError('Для выпуска упаковки выберите целую единицу измерения в штуках.')
            warehouse_ids = body.get('permanent_warehouse_ids', list(item.permanent_warehouses.values_list('pk', flat=True)) if item else [])
            if not isinstance(warehouse_ids, list) or any(type(value) is not int or value <= 0 for value in warehouse_ids):
                raise ValueError('Выберите склады постоянного хранения.')
            warehouse_ids = set(warehouse_ids)
            if Warehouse.objects.filter(pk__in=warehouse_ids, is_active=True).count() != len(warehouse_ids):
                raise ValueError('Один из выбранных складов не найден или неактивен.')
            if material:
                if not warehouse_ids:
                    raise ValueError('Для производственного материала выберите хотя бы один постоянный склад.')
                if values['unit'].symbol.lower() not in ('кг', 'kg'):
                    raise ValueError('Для производственных материалов выберите единицу кг.')
                if not values['is_active']:
                    raise ValueError('Постоянная производственная позиция должна оставаться активной.')
            elif warehouse_ids:
                raise ValueError('Постоянные склады задаются только для производственных материалов.')
            if len(values['name']) > 180:
                raise ValueError('Название номенклатуры не должно превышать 180 символов.')
            if item and (item.document_lines.exists() or item.production_output_lines.exists()) and values['unit'].pk != item.unit_id:
                raise ValueError('Нельзя изменить единицу измерения позиции с историей движений.')
            if item and material != item.production_material and item.warehouse_movements.exclude(document__production_target='').exists():
                raise ValueError('Нельзя изменить назначение сырья с историей производственных загрузок.')
            if item and product != item.production_product and item.production_output_lines.exists():
                raise ValueError('Нельзя изменить вид упаковки с историей выпуска.')
            values['production_material'] = material
            values['production_product'] = product
            if item:
                for field, value in values.items():
                    setattr(item, field, value)
                item.save()
            else:
                item = InventoryItem.objects.create(**values)
            item.permanent_warehouses.set(warehouse_ids)
        saved = queryset.get(pk=item.pk)
        return JsonResponse(_serialize_inventory_settings_item(saved), status=200 if item_id else 201)
    except ProtectedError:
        return JsonResponse({'detail': 'Запись используется и не может быть удалена.'}, status=400)
    except (ValueError, TypeError) as exc:
        return JsonResponse({'detail': str(exc)}, status=400)
    except IntegrityError:
        return JsonResponse({'detail': 'Номенклатура с таким названием уже существует.'}, status=400)


@csrf_exempt
def warehouses_view(request):
    return _warehouse_settings_view(request, Warehouse, _serialize_warehouse, _warehouse_fields)


@csrf_exempt
def warehouse_detail_view(request, warehouse_id):
    return _warehouse_settings_detail_view(request, warehouse_id, Warehouse, _serialize_warehouse, _warehouse_fields)


@require_GET
def warehouse_reference_data_view(request):
    user, error = _require_auth(request)
    if error:
        return error
    if not (_is_admin(user) or _has_permission(user, MODULE_WAREHOUSE_ACCOUNTING, PERMISSION_VIEW)):
        return _permission_denied()
    return JsonResponse({
        'warehouses': [_serialize_warehouse(item) for item in Warehouse.objects.filter(is_active=True)],
        'items': [
            _serialize_inventory_item(item)
            for item in InventoryItem.objects.select_related('category', 'unit').filter(is_active=True)
        ],
        'suppliers': [_serialize_supplier(item) for item in Supplier.objects.select_related('city').all()],
    })


@require_GET
def warehouse_overview_view(request):
    user, error = _require_auth(request)
    if error:
        return error
    if not (_is_admin(user) or _has_permission(user, MODULE_WAREHOUSE_ACCOUNTING, PERMISSION_VIEW)):
        return _permission_denied()
    balances = list(WarehouseBalance.objects.select_related('warehouse', 'item__category', 'item__unit').filter(quantity__gt=0))
    total_value = sum(
        (balance.quantity * balance.average_unit_cost for balance in balances),
        Decimal('0.00'),
    ).quantize(Decimal('0.01'))
    rows = {(balance.warehouse_id, balance.item_id): _serialize_warehouse_balance(balance) for balance in balances}
    permanent_items = InventoryItem.objects.exclude(production_material='').filter(is_active=True).select_related(
        'category', 'unit',
    ).prefetch_related('permanent_warehouses')
    for item in permanent_items:
        for warehouse in item.permanent_warehouses.all():
            if not warehouse.is_active:
                continue
            key = (warehouse.pk, item.pk)
            if key not in rows:
                rows[key] = {
                    'id': f'permanent-{warehouse.pk}-{item.pk}',
                    'warehouse': _serialize_warehouse(warehouse), 'item': _serialize_inventory_item(item),
                    'quantity': '0.00', 'average_unit_cost': '0.00', 'total_value': '0.00', 'updated_at': None,
                }
            rows[key]['is_permanent'] = True
    return JsonResponse({
        'balances': sorted(rows.values(), key=lambda row: (row['warehouse']['name'], row['item']['name'])),
        'total_value': str(total_value),
        'warehouse_count': Warehouse.objects.filter(is_active=True).count(),
        'item_count': InventoryItem.objects.filter(is_active=True).count(),
        'in_transit_count': WarehouseDocument.objects.filter(
            document_type=WarehouseDocument.TYPE_TRANSFER,
            status=WarehouseDocument.STATUS_IN_TRANSIT,
        ).count(),
    })


@csrf_exempt
def warehouse_documents_view(request):
    user, error = _require_auth(request)
    if error:
        return error
    if request.method == 'GET':
        if not (_is_admin(user) or _has_permission(user, MODULE_WAREHOUSE_ACCOUNTING, PERMISSION_VIEW)):
            return _permission_denied()
        documents = (
            WarehouseDocument.objects
            .select_related('source_warehouse', 'destination_warehouse', 'supplier__city', 'created_by', 'posted_by', 'confirmed_by')
            .prefetch_related('lines__item__category', 'lines__item__unit')
        )
        document_type = request.GET.get('type')
        if document_type:
            documents = documents.filter(document_type=document_type)
        return JsonResponse({'items': [_serialize_warehouse_document(document) for document in documents]})
    if request.method != 'POST':
        return _method_not_allowed()
    body = _json_body(request)
    if body is None:
        return _invalid_json_body()
    document_type = str(body.get('document_type') or '')
    permission_code = WAREHOUSE_DOCUMENT_PERMISSIONS.get(document_type)
    if permission_code is None or not (_is_admin(user) or _has_permission(user, MODULE_WAREHOUSE_ACCOUNTING, permission_code)):
        return _permission_denied()
    document_date = _warehouse_document_date(body.get('document_date'))
    if document_date is None:
        return JsonResponse({'detail': 'Некорректная дата документа.'}, status=400)
    source_warehouse = Warehouse.objects.filter(pk=body.get('source_warehouse_id'), is_active=True).first()
    destination_warehouse = Warehouse.objects.filter(pk=body.get('destination_warehouse_id'), is_active=True).first()
    supplier = Supplier.objects.filter(pk=body.get('supplier_id')).first()
    header_error = _warehouse_header_error(document_type, source_warehouse, destination_warehouse, supplier)
    if header_error:
        return JsonResponse({'detail': header_error}, status=400)
    purpose = str(body.get('purpose') or '').strip()
    if document_type == WarehouseDocument.TYPE_ISSUE and not purpose:
        return JsonResponse({'detail': 'Укажите назначение внутреннего расхода.'}, status=400)
    parsed_lines, lines_error = _parse_warehouse_document_lines(body.get('lines'), document_type)
    if lines_error:
        return JsonResponse({'detail': lines_error}, status=400)
    with transaction.atomic():
        document = WarehouseDocument.objects.create(
            number=_next_warehouse_document_number(document_type, document_date),
            document_type=document_type,
            document_date=document_date,
            source_warehouse=source_warehouse,
            destination_warehouse=destination_warehouse,
            supplier=supplier,
            purpose=purpose,
            created_by=user,
        )
        WarehouseDocumentLine.objects.bulk_create([
            WarehouseDocumentLine(document=document, **line) for line in parsed_lines
        ])
    document = (
        WarehouseDocument.objects
        .select_related('source_warehouse', 'destination_warehouse', 'supplier__city', 'created_by', 'posted_by', 'confirmed_by')
        .prefetch_related('lines__item__category', 'lines__item__unit')
        .get(pk=document.pk)
    )
    return JsonResponse(_serialize_warehouse_document(document), status=201)


@csrf_exempt
def warehouse_document_detail_view(request, document_id):
    user, error = _require_auth(request)
    if error:
        return error
    if not (_is_admin(user) or _has_permission(user, MODULE_WAREHOUSE_ACCOUNTING, PERMISSION_VIEW)):
        return _permission_denied()
    document = (
        WarehouseDocument.objects
        .select_related('source_warehouse', 'destination_warehouse', 'supplier__city', 'created_by', 'posted_by', 'confirmed_by')
        .prefetch_related('lines__item__category', 'lines__item__unit')
        .filter(pk=document_id)
        .first()
    )
    if document is None:
        return JsonResponse({'detail': 'Складской документ не найден.'}, status=404)
    if request.method == 'GET':
        return JsonResponse(_serialize_warehouse_document(document))
    if request.method == 'DELETE':
        if document.status != WarehouseDocument.STATUS_DRAFT:
            return JsonResponse({'detail': 'Проведённый документ нельзя удалить.'}, status=423)
        permission_code = WAREHOUSE_DOCUMENT_PERMISSIONS[document.document_type]
        if not (_is_admin(user) or _has_permission(user, MODULE_WAREHOUSE_ACCOUNTING, permission_code)):
            return _permission_denied()
        document.delete()
        return JsonResponse({'deleted': True})
    return _method_not_allowed()


@csrf_exempt
@require_POST
def warehouse_document_post_view(request, document_id):
    user, error = _require_auth(request)
    if error:
        return error
    with transaction.atomic():
        document = (
            WarehouseDocument.objects
            .select_for_update(of=('self',))
            .select_related('source_warehouse', 'destination_warehouse')
            .prefetch_related('lines__item__unit')
            .filter(pk=document_id)
            .first()
        )
        if document is None:
            return JsonResponse({'detail': 'Складской документ не найден.'}, status=404)
        permission_code = WAREHOUSE_DOCUMENT_PERMISSIONS[document.document_type]
        if not (_is_admin(user) or _has_permission(user, MODULE_WAREHOUSE_ACCOUNTING, permission_code)):
            return _permission_denied()
        if document.status != WarehouseDocument.STATUS_DRAFT:
            return JsonResponse({'detail': 'Можно провести только черновик.'}, status=423)
        if not _is_admin(user) and timezone.localtime(document.document_date).date() != timezone.localdate():
            return JsonResponse({'detail': 'Проводить документы другой датой может только администратор.'}, status=403)
        try:
            for line in document.lines.all():
                if document.document_type == WarehouseDocument.TYPE_RECEIPT:
                    balance = _locked_warehouse_balance(document.destination_warehouse, line.item)
                    _add_to_warehouse_balance(balance, line.quantity, line.unit_price)
                    line.item.last_purchase_price = line.unit_price
                    line.item.save(update_fields=['last_purchase_price', 'updated_at'])
                    _create_warehouse_movement(
                        document, document.destination_warehouse, line.item,
                        WarehouseMovement.TYPE_RECEIPT, line.quantity, line.unit_price, user,
                    )
                elif document.document_type == WarehouseDocument.TYPE_ISSUE:
                    balance = _locked_warehouse_balance(document.source_warehouse, line.item)
                    unit_cost = _remove_from_warehouse_balance(balance, line.quantity)
                    _create_warehouse_movement(
                        document, document.source_warehouse, line.item,
                        WarehouseMovement.TYPE_ISSUE, -line.quantity, unit_cost, user,
                    )
                elif document.document_type == WarehouseDocument.TYPE_TRANSFER:
                    balance = _locked_warehouse_balance(document.source_warehouse, line.item)
                    unit_cost = _remove_from_warehouse_balance(balance, line.quantity)
                    _create_warehouse_movement(
                        document, document.source_warehouse, line.item,
                        WarehouseMovement.TYPE_TRANSFER_OUT, -line.quantity, unit_cost, user,
                    )
                else:
                    balance = _locked_warehouse_balance(document.source_warehouse, line.item)
                    delta = line.quantity - balance.quantity
                    if delta > 0:
                        unit_cost = balance.average_unit_cost or line.item.last_purchase_price
                        _add_to_warehouse_balance(balance, delta, unit_cost)
                    elif delta < 0:
                        unit_cost = _remove_from_warehouse_balance(balance, -delta)
                    else:
                        continue
                    _create_warehouse_movement(
                        document, document.source_warehouse, line.item,
                        WarehouseMovement.TYPE_INVENTORY, delta, unit_cost, user,
                    )
        except ValueError as exc:
            transaction.set_rollback(True)
            return JsonResponse({'detail': str(exc)}, status=400)
        document.status = (
            WarehouseDocument.STATUS_IN_TRANSIT
            if document.document_type == WarehouseDocument.TYPE_TRANSFER
            else WarehouseDocument.STATUS_POSTED
        )
        document.posted_by = user
        document.posted_at = timezone.now()
        document.save(update_fields=['status', 'posted_by', 'posted_at'])
    return JsonResponse({'posted': True, 'status': document.status})


@csrf_exempt
@require_POST
def warehouse_transfer_decision_view(request, document_id):
    user, error = _require_auth(request)
    if error:
        return error
    if not (_is_admin(user) or _has_permission(user, MODULE_WAREHOUSE_ACCOUNTING, PERMISSION_TRANSFER_CONFIRM)):
        return _permission_denied()
    body = _json_body(request)
    if body is None:
        return _invalid_json_body()
    decision = str(body.get('decision') or '')
    if decision not in ('confirm', 'reject'):
        return JsonResponse({'detail': 'Укажите подтверждение или отказ.'}, status=400)
    with transaction.atomic():
        document = (
            WarehouseDocument.objects
            .select_for_update(of=('self',))
            .select_related('source_warehouse', 'destination_warehouse')
            .prefetch_related('lines__item')
            .filter(pk=document_id, document_type=WarehouseDocument.TYPE_TRANSFER)
            .first()
        )
        if document is None:
            return JsonResponse({'detail': 'Перемещение не найдено.'}, status=404)
        if document.status != WarehouseDocument.STATUS_IN_TRANSIT:
            return JsonResponse({'detail': 'Решение уже принято или документ не отправлен.'}, status=423)
        outgoing_costs = {
            movement.item_id: movement.unit_cost
            for movement in document.movements.filter(movement_type=WarehouseMovement.TYPE_TRANSFER_OUT)
        }
        destination = document.destination_warehouse if decision == 'confirm' else document.source_warehouse
        movement_type = (
            WarehouseMovement.TYPE_TRANSFER_IN
            if decision == 'confirm'
            else WarehouseMovement.TYPE_TRANSFER_RETURN
        )
        for line in document.lines.all():
            unit_cost = outgoing_costs[line.item_id]
            balance = _locked_warehouse_balance(destination, line.item)
            _add_to_warehouse_balance(balance, line.quantity, unit_cost)
            _create_warehouse_movement(document, destination, line.item, movement_type, line.quantity, unit_cost, user)
        document.status = (
            WarehouseDocument.STATUS_COMPLETED
            if decision == 'confirm'
            else WarehouseDocument.STATUS_REJECTED
        )
        document.confirmed_by = user
        document.confirmed_at = timezone.now()
        document.save(update_fields=['status', 'confirmed_by', 'confirmed_at'])
    return JsonResponse({'status': document.status})


@csrf_exempt
@require_POST
def warehouse_document_cancel_view(request, document_id):
    user, error = _require_admin(request)
    if error:
        return error
    with transaction.atomic():
        lock_oil_line()
        document = WarehouseDocument.objects.select_for_update().filter(pk=document_id).first()
        if document is None:
            return JsonResponse({'detail': 'Складской документ не найден.'}, status=404)
        if document.status not in (
            WarehouseDocument.STATUS_POSTED,
            WarehouseDocument.STATUS_IN_TRANSIT,
            WarehouseDocument.STATUS_COMPLETED,
        ):
            return JsonResponse({'detail': 'Этот документ нельзя отменить.'}, status=423)
        if document.production_target == WarehouseDocument.TARGET_SORPTION:
            from .sorbent import loading_is_in_use
            if loading_is_in_use(document.pk):
                return JsonResponse({'detail': 'Нельзя отменить пополнение бака: сначала компенсируйте связанные движения сорбента.'}, status=423)
        if document.production_target and ProductionMaterialUsage.objects.filter(
            source_movement__document=document, output__is_cancelled=False,
        ).exists():
            return JsonResponse({'detail': 'Нельзя отменить загрузку: сырьё уже использовано в выпуске. Сначала отмените связанный выпуск.'}, status=423)
        if OilManufacturingBatch.objects.filter(material_document=document).exclude(status=OilManufacturingBatch.STATUS_CANCELLED).exists():
            return JsonResponse({'detail': 'Отменяйте расход полипропилена через связанную производственную партию.'}, status=423)
        original_movements = list(
            document.movements.exclude(movement_type=WarehouseMovement.TYPE_REVERSAL).select_related('warehouse', 'item')
        )
        try:
            for movement in original_movements:
                reverse_quantity = -movement.quantity_delta
                balance = _locked_warehouse_balance(movement.warehouse, movement.item)
                if reverse_quantity > 0:
                    _add_to_warehouse_balance(balance, reverse_quantity, movement.unit_cost)
                else:
                    _remove_from_warehouse_balance(balance, -reverse_quantity)
                _create_warehouse_movement(
                    document, movement.warehouse, movement.item,
                    WarehouseMovement.TYPE_REVERSAL, reverse_quantity, movement.unit_cost, user,
                )
        except ValueError as exc:
            transaction.set_rollback(True)
            return JsonResponse({'detail': f'Документ нельзя отменить: {exc}'}, status=400)
        document.status = WarehouseDocument.STATUS_CANCELLED
        document.cancelled_at = timezone.now()
        document.save(update_fields=['status', 'cancelled_at'])
    return JsonResponse({'status': document.status})


PRODUCTION_LOADING_CONFIG = {
    WarehouseDocument.TARGET_CANISTERS: (MODULE_CANISTER_LOADING, (InventoryItem.MATERIAL_GRANULES, InventoryItem.MATERIAL_DYE)),
    WarehouseDocument.TARGET_CAPS: (MODULE_CAP_LOADING, (InventoryItem.MATERIAL_GRANULES, InventoryItem.MATERIAL_DYE)),
    WarehouseDocument.TARGET_SORPTION: (MODULE_SORBENT_LOADING, (InventoryItem.MATERIAL_SORBENT,)),
}


def _production_loading_user(request, target):
    user, error = _require_auth(request)
    if error:
        return None, error
    config = PRODUCTION_LOADING_CONFIG.get(target)
    if config is None:
        return None, JsonResponse({'detail': 'Неизвестное направление производственной загрузки.'}, status=404)
    permission = _method_permission(request)
    if request.method not in ('GET', 'POST'):
        return None, _method_not_allowed()
    if not (_is_admin(user) or _has_permission(user, config[0], permission)):
        return None, _permission_denied()
    return user, None


def _production_loading_queryset():
    return WarehouseDocument.objects.exclude(production_target='').select_related(
        'source_warehouse', 'destination_warehouse', 'supplier__city', 'created_by', 'posted_by', 'confirmed_by',
    ).prefetch_related('lines__item__category', 'lines__item__unit', 'movements')


def _serialize_production_loading(document):
    result = _serialize_warehouse_document(document)
    items = {line.item_id: line.item for line in document.lines.all()}
    movements = {movement.item_id: movement for movement in document.movements.all() if movement.movement_type == WarehouseMovement.TYPE_ISSUE}
    for line in result['lines']:
        line['item'] = _serialize_production_item(items[line['item_id']])
        movement = movements.get(line['item_id'])
        line['unit_cost'] = str(movement.unit_cost) if movement else '0.00'
        line['material_cost'] = str(-movement.total_value_delta) if movement else '0.00'
    result['material_cost'] = str(sum((Decimal(line['material_cost']) for line in result['lines']), Decimal('0.00')))
    return result


@require_GET
def production_loading_reference_view(request, target):
    user, error = _production_loading_user(request, target)
    if error:
        return error
    items = InventoryItem.objects.filter(
        production_material__in=PRODUCTION_LOADING_CONFIG[target][1],
        is_active=True, category__is_active=True, unit__is_active=True,
    ).select_related('category', 'unit').prefetch_related('permanent_warehouses')
    balances = {
        (balance.warehouse_id, balance.item_id): balance.quantity
        for balance in WarehouseBalance.objects.filter(item__in=items)
    }
    rows = []
    warehouses = {}
    for item in items:
        for warehouse in item.permanent_warehouses.all():
            if warehouse.is_active:
                warehouses[warehouse.pk] = _serialize_warehouse(warehouse)
                rows.append({
                    'warehouse_id': warehouse.pk, 'item': _serialize_production_item(item),
                    'quantity': str(balances.get((warehouse.pk, item.pk), Decimal('0.00'))),
                })
    return JsonResponse({'warehouses': list(warehouses.values()), 'materials': rows, **_production_material_state(target)})


def _production_loading_replay(document, target, warehouse_id, lines, purpose, user):
    original = {line.item_id: line.quantity for line in document.lines.all()}
    requested = {line['item_id']: line['quantity'] for line in lines}
    if document.created_by_id != user.pk or document.production_target != target or document.source_warehouse_id != warehouse_id or original != requested or document.purpose != purpose:
        return JsonResponse({'detail': 'Этот ключ запроса уже использован для другой загрузки.'}, status=409)
    return JsonResponse(_serialize_production_loading(document))


@csrf_exempt
def production_loadings_view(request, target):
    user, error = _production_loading_user(request, target)
    if error:
        return error
    queryset = _production_loading_queryset()
    if request.method == 'GET':
        return JsonResponse({'items': [_serialize_production_loading(document) for document in queryset.filter(production_target=target)]})
    body = _json_body(request)
    if not isinstance(body, dict):
        return _invalid_json_body()
    key = body.get('idempotency_key')
    warehouse_id = body.get('source_warehouse_id')
    purpose = body.get('purpose', '')
    if not isinstance(key, str) or not key.strip() or len(key) > 80:
        return JsonResponse({'detail': 'Необходим корректный ключ запроса загрузки.'}, status=400)
    if type(warehouse_id) is not int or warehouse_id <= 0:
        return JsonResponse({'detail': 'Необходимо выбрать склад.'}, status=400)
    if not isinstance(purpose, str) or len(purpose) > 1000:
        return JsonResponse({'detail': 'Комментарий должен содержать не более 1000 символов.'}, status=400)
    purpose = purpose.strip() or dict(WarehouseDocument.PRODUCTION_TARGET_CHOICES)[target]
    raw_lines = body.get('lines')
    if not isinstance(raw_lines, list) or not 1 <= len(raw_lines) <= 100:
        return JsonResponse({'detail': 'Добавьте от 1 до 100 строк загрузки.'}, status=400)
    lines = []
    for raw_line in raw_lines:
        if not isinstance(raw_line, dict) or type(raw_line.get('item_id')) is not int:
            return JsonResponse({'detail': 'В каждой строке должна быть выбрана номенклатура.'}, status=400)
        quantity = _decimal_value(raw_line.get('quantity'))
        if quantity is None or not quantity.is_finite() or not Decimal('0') < quantity < Decimal('10000000000000000'):
            return JsonResponse({'detail': 'Укажите корректное положительное количество материала.'}, status=400)
        lines.append({'item_id': raw_line['item_id'], 'quantity': quantity})
    if len({line['item_id'] for line in lines}) != len(lines):
        return JsonResponse({'detail': 'Номенклатура не должна повторяться в одном документе.'}, status=400)
    key = key.strip()
    existing = queryset.filter(idempotency_key=key).first()
    if existing:
        return _production_loading_replay(existing, target, warehouse_id, lines, purpose, user)
    try:
        with transaction.atomic():
            warehouse = Warehouse.objects.filter(pk=warehouse_id, is_active=True).first()
            if warehouse is None:
                raise ValueError('Выбранный склад не найден или неактивен.')
            items = {
                item.pk: item for item in InventoryItem.objects.select_for_update(of=('self',)).select_related('unit', 'category').filter(
                    pk__in=[line['item_id'] for line in lines], is_active=True,
                ).order_by('pk')
            }
            for line in lines:
                item = items.get(line['item_id'])
                if item is None or not item.unit.is_active or not item.category.is_active or item.unit.symbol.lower() not in ('кг', 'kg'):
                    raise ValueError('Материал не найден, неактивен или имеет неподходящую единицу измерения.')
                if item.production_material not in PRODUCTION_LOADING_CONFIG[target][1] or not item.permanent_warehouses.filter(pk=warehouse.pk).exists():
                    raise ValueError('Материал не разрешён для этого направления или не закреплён за выбранным складом.')
                quantity = _warehouse_quantity(line['quantity'], item.unit)
                if quantity is None:
                    raise ValueError(f'Количество для «{item.name}» не соответствует точности единицы измерения.')
                line['quantity'] = quantity
            now = timezone.now()
            document = WarehouseDocument.objects.create(
                number=_next_warehouse_document_number(WarehouseDocument.TYPE_ISSUE, now),
                document_type=WarehouseDocument.TYPE_ISSUE, status=WarehouseDocument.STATUS_POSTED,
                document_date=now, source_warehouse=warehouse, purpose=purpose,
                production_target=target, idempotency_key=key,
                created_by=user, posted_by=user, posted_at=now,
            )
            for line in sorted(lines, key=lambda value: value['item_id']):
                item = items[line['item_id']]
                balance = _locked_warehouse_balance(warehouse, item)
                unit_cost = _remove_from_warehouse_balance(balance, line['quantity'])
                if line['quantity'] * unit_cost >= Decimal('1000000000000000000'):
                    raise ValueError('Стоимость загрузки превышает допустимый размер складского движения.')
                WarehouseDocumentLine.objects.create(document=document, item=item, quantity=line['quantity'])
                _create_warehouse_movement(document, warehouse, item, WarehouseMovement.TYPE_ISSUE, -line['quantity'], unit_cost, user)
        return JsonResponse(_serialize_production_loading(queryset.get(pk=document.pk)), status=201)
    except ValueError as exc:
        return JsonResponse({'detail': str(exc)}, status=400)
    except IntegrityError:
        existing = queryset.filter(idempotency_key=key).first()
        if existing:
            return _production_loading_replay(existing, target, warehouse_id, lines, purpose, user)
        return JsonResponse({'detail': 'Не удалось провести загрузку. Обновите данные и повторите попытку.'}, status=409)


PRODUCTION_OUTPUT_MODULES = {'canisters': MODULE_CANISTER_OUTPUT, 'caps': MODULE_CAP_OUTPUT}


def _packaging_production_overview():
    targets = tuple(PRODUCTION_OUTPUT_MODULES)
    result = {target: {
        'materials': {role: {'loaded_quantity': Decimal('0.00'), 'used_quantity': Decimal('0.00')} for role in ('granules', 'dye')},
        'output_totals': {'good': 0, 'deviation': 0, 'reject': 0},
    } for target in targets}
    loaded = WarehouseMovement.objects.filter(
        movement_type=WarehouseMovement.TYPE_ISSUE, document__status=WarehouseDocument.STATUS_POSTED,
        document__production_target__in=targets,
    ).values('document__production_target', 'item__production_material').annotate(total=Sum('quantity_delta'))
    used = ProductionMaterialUsage.objects.filter(output__is_cancelled=False).values(
        'output__target', 'source_movement__item__production_material',
    ).annotate(total=Sum('quantity'))
    for row in loaded:
        role = row['item__production_material']
        if role in result[row['document__production_target']]['materials']:
            result[row['document__production_target']]['materials'][role]['loaded_quantity'] = -row['total']
    for row in used:
        role = row['source_movement__item__production_material']
        if row['output__target'] in result and role in result[row['output__target']]['materials']:
            result[row['output__target']]['materials'][role]['used_quantity'] = row['total']
    counts = ProductionOutputLine.objects.filter(output__is_cancelled=False).values('output__target', 'disposition').annotate(total=Sum('quantity'))
    for row in counts:
        result[row['output__target']]['output_totals'][row['disposition']] = row['total']
    for target in result.values():
        for material in target['materials'].values():
            material['available_quantity'] = material['loaded_quantity'] - material['used_quantity']
            for key, quantity in material.items():
                material[key] = str(quantity)
    return result


def _production_sources(target):
    return WarehouseMovement.objects.filter(
        movement_type=WarehouseMovement.TYPE_ISSUE, document__production_target=target,
        document__status=WarehouseDocument.STATUS_POSTED,
    ).select_related('item__unit', 'item__category', 'warehouse', 'document').annotate(
        used_quantity=Sum('production_usages__quantity', filter=Q(production_usages__output__is_cancelled=False)),
        used_cost=Sum('production_usages__material_cost', filter=Q(production_usages__output__is_cancelled=False)),
    ).order_by('created_at', 'pk')


def _production_source_remainder(source):
    return (
        -source.quantity_delta - (source.used_quantity or Decimal('0.00')),
        -source.total_value_delta - (source.used_cost or Decimal('0.00')),
    )


def _production_material_state(target):
    balances = {}
    sources = []
    for source in _production_sources(target):
        quantity, cost = _production_source_remainder(source)
        balance = balances.setdefault(source.item_id, {
            'item': _serialize_production_item(source.item), 'loaded_quantity': Decimal('0.00'),
            'used_quantity': Decimal('0.00'), 'available_quantity': Decimal('0.00'), 'available_cost': Decimal('0.00'),
        })
        balance['loaded_quantity'] -= source.quantity_delta
        balance['used_quantity'] += source.used_quantity or Decimal('0.00')
        balance['available_quantity'] += quantity
        balance['available_cost'] += cost
        if quantity > 0:
            sources.append({
                'id': source.pk, 'item': _serialize_production_item(source.item),
                'loading_id': source.document_id, 'loading_number': source.document.number,
                'warehouse': _serialize_warehouse(source.warehouse), 'loaded_at': source.created_at.isoformat(),
                'available_quantity': str(quantity), 'unit_cost': str(source.unit_cost), 'available_cost': str(cost),
            })
    return {
        'production_balances': [{key: value if key == 'item' else str(value) for key, value in balance.items()} for balance in balances.values()],
        'production_sources': sources,
    }


def _production_output_user(request, target):
    user, error = _require_auth(request)
    if error:
        return None, error
    if target not in PRODUCTION_OUTPUT_MODULES:
        return None, JsonResponse({'detail': 'Неизвестное направление выпуска.'}, status=404)
    if request.method not in ('GET', 'POST'):
        return None, _method_not_allowed()
    if not (_is_admin(user) or _has_permission(user, PRODUCTION_OUTPUT_MODULES[target], _method_permission(request))):
        return None, _permission_denied()
    return user, None


def _production_output_queryset():
    return ProductionOutput.objects.select_related('created_by', 'cancelled_by').prefetch_related(
        'lines__item__category', 'lines__item__unit', 'material_usages__source_movement__item__category',
        'material_usages__source_movement__item__unit', 'material_usages__source_movement__document',
    )


def _serialize_production_output(output):
    usages = list(output.material_usages.all())
    return {
        'id': output.pk, 'number': output.number, 'target': output.target, 'note': output.note,
        'created_at': output.created_at.isoformat(), 'created_by': output.created_by.get_username() if output.created_by else '',
        'is_cancelled': output.is_cancelled, 'cancelled_at': output.cancelled_at.isoformat() if output.cancelled_at else None,
        'cancelled_by': output.cancelled_by.get_username() if output.cancelled_by else '',
        'material_cost': str(sum((usage.material_cost for usage in usages), Decimal('0.00'))),
        'lines': [{
            'id': line.pk, 'item': _serialize_production_item(line.item), 'item_id': line.item_id,
            'disposition': line.disposition, 'disposition_label': line.get_disposition_display(), 'quantity': line.quantity,
        } for line in output.lines.all()],
        'material_usages': [{
            'id': usage.pk, 'source_movement_id': usage.source_movement_id,
            'loading_number': usage.source_movement.document.number,
            'item': _serialize_production_item(usage.source_movement.item), 'quantity': str(usage.quantity),
            'unit_cost': str(usage.unit_cost), 'material_cost': str(usage.material_cost),
        } for usage in usages],
    }


@require_GET
def production_output_reference_view(request, target):
    _, error = _production_output_user(request, target)
    if error:
        return error
    products = InventoryItem.objects.filter(
        production_product=target, is_active=True, category__is_active=True, unit__is_active=True,
    ).select_related('category', 'unit')
    return JsonResponse({'products': [_serialize_production_item(item) for item in products], **_production_material_state(target)})


def _production_output_payload(body, target):
    if not isinstance(body, dict):
        raise ValueError('Ожидается объект с данными выпуска.')
    key = body.get('idempotency_key')
    note = body.get('note', '')
    if not isinstance(key, str) or not key.strip() or len(key) > 80:
        raise ValueError('Необходим корректный ключ запроса выпуска.')
    if not isinstance(note, str) or len(note) > 1000:
        raise ValueError('Комментарий должен содержать не более 1000 символов.')
    raw_lines, raw_usages = body.get('lines'), body.get('material_usages')
    if not isinstance(raw_lines, list) or not 1 <= len(raw_lines) <= 100 or not isinstance(raw_usages, list) or not 1 <= len(raw_usages) <= 100:
        raise ValueError('Укажите от 1 до 100 строк выпуска и фактического расхода сырья.')
    lines, usages = [], []
    dispositions = {'good', 'reject'} | ({'deviation'} if target == 'canisters' else set())
    for line in raw_lines:
        if not isinstance(line, dict) or type(line.get('item_id')) is not int or type(line.get('quantity')) is not int or not 0 < line['quantity'] <= 2147483647:
            raise ValueError('Выпуск указывается положительным целым количеством штук с выбранной номенклатурой.')
        if line.get('disposition') not in dispositions:
            raise ValueError('Для крышек допустимы только годные и брак; отклонения доступны только для канистр.')
        lines.append({'item_id': line['item_id'], 'disposition': line['disposition'], 'quantity': line['quantity']})
    for usage in raw_usages:
        if not isinstance(usage, dict) or type(usage.get('source_movement_id')) is not int:
            raise ValueError('Выберите загрузку для каждой строки расхода сырья.')
        quantity = _decimal_value(usage.get('quantity'))
        if quantity is None or not quantity.is_finite() or not Decimal('0') < quantity < Decimal('10000000000000000') or quantity != quantity.quantize(Decimal('0.01')):
            raise ValueError('Укажите корректный фактический расход сырья в килограммах.')
        usages.append({'source_movement_id': usage['source_movement_id'], 'quantity': quantity})
    if len({(line['item_id'], line['disposition']) for line in lines}) != len(lines) or len({usage['source_movement_id'] for usage in usages}) != len(usages):
        raise ValueError('Строки выпуска или источники расхода не должны повторяться.')
    return key.strip(), note.strip(), lines, usages


def _production_output_replay(output, target, user, note, lines, usages):
    original_lines = {(line.item_id, line.disposition): line.quantity for line in output.lines.all()}
    original_usages = {usage.source_movement_id: usage.quantity for usage in output.material_usages.all()}
    if output.target != target or output.created_by_id != user.pk or output.note != note or original_lines != {(line['item_id'], line['disposition']): line['quantity'] for line in lines} or original_usages != {usage['source_movement_id']: usage['quantity'] for usage in usages}:
        return JsonResponse({'detail': 'Этот ключ запроса уже использован для другого выпуска.'}, status=409)
    return JsonResponse(_serialize_production_output(output))


@csrf_exempt
def production_outputs_view(request, target):
    user, error = _production_output_user(request, target)
    if error:
        return error
    queryset = _production_output_queryset()
    if request.method == 'GET':
        return JsonResponse({'items': [_serialize_production_output(output) for output in queryset.filter(target=target)]})
    try:
        key, note, lines, usages = _production_output_payload(_json_body(request), target)
    except (ValueError, TypeError, InvalidOperation) as exc:
        return JsonResponse({'detail': str(exc)}, status=400)
    existing = queryset.filter(idempotency_key=key).first()
    if existing:
        return _production_output_replay(existing, target, user, note, lines, usages)
    try:
        with transaction.atomic():
            source_ids = [usage['source_movement_id'] for usage in usages]
            document_ids = list(WarehouseMovement.objects.filter(
                pk__in=source_ids, movement_type=WarehouseMovement.TYPE_ISSUE,
                document__production_target=target, document__status=WarehouseDocument.STATUS_POSTED,
            ).values_list('document_id', flat=True))
            documents = list(WarehouseDocument.objects.select_for_update().filter(pk__in=document_ids).order_by('pk'))
            existing = queryset.filter(idempotency_key=key).first()
            if existing:
                return _production_output_replay(existing, target, user, note, lines, usages)
            if any(document.status != WarehouseDocument.STATUS_POSTED for document in documents):
                raise ValueError('Одна из загрузок отменена или недоступна.')
            sources = {source.pk: source for source in _production_sources(target).filter(pk__in=source_ids)}
            if len(sources) != len(source_ids):
                raise ValueError('Источник сырья не найден, отменён или относится к другой линии.')
            items = {item.pk: item for item in InventoryItem.objects.select_for_update(of=('self',)).select_related('unit', 'category').filter(
                pk__in=[line['item_id'] for line in lines], production_product=target, is_active=True,
            ).order_by('pk')}
            for line in lines:
                item = items.get(line['item_id'])
                if item is None or not item.unit.is_active or not item.category.is_active or item.unit.decimal_places != 0 or item.unit.symbol.lower() not in ('шт', 'шт.', 'pcs', 'dona'):
                    raise ValueError('Выберите активную номенклатуру упаковки соответствующей линии в штуках.')
            for usage in usages:
                source = sources[usage['source_movement_id']]
                quantity, cost = _production_source_remainder(source)
                if _warehouse_quantity(usage['quantity'], source.item.unit) is None or usage['quantity'] > quantity:
                    raise ValueError('Расход превышает доступное сырьё в производстве или точность единицы измерения.')
                usage['unit_cost'] = source.unit_cost
                usage['material_cost'] = cost if usage['quantity'] == quantity else (cost * usage['quantity'] / quantity).quantize(Decimal('0.01'))
            now = timezone.now()
            output = ProductionOutput.objects.create(
                number=_next_warehouse_document_number('production-output', now), target=target,
                idempotency_key=key, note=note, created_by=user, created_at=now,
            )
            ProductionOutputLine.objects.bulk_create([ProductionOutputLine(output=output, **line) for line in lines])
            ProductionMaterialUsage.objects.bulk_create([ProductionMaterialUsage(output=output, **usage) for usage in usages])
        return JsonResponse(_serialize_production_output(queryset.get(pk=output.pk)), status=201)
    except (ValueError, InvalidOperation) as exc:
        return JsonResponse({'detail': str(exc)}, status=400)
    except IntegrityError:
        existing = queryset.filter(idempotency_key=key).first()
        if existing:
            return _production_output_replay(existing, target, user, note, lines, usages)
        return JsonResponse({'detail': 'Не удалось зарегистрировать выпуск. Обновите данные и повторите попытку.'}, status=409)


@csrf_exempt
@require_POST
def production_output_cancel_view(request, target, output_id):
    user, error = _require_admin(request)
    if error:
        return error
    with transaction.atomic():
        output = ProductionOutput.objects.select_for_update().filter(pk=output_id, target=target).first()
        if output is None:
            return JsonResponse({'detail': 'Выпуск не найден.'}, status=404)
        if output.is_cancelled:
            return JsonResponse({'detail': 'Выпуск уже отменён.'}, status=423)
        document_ids = output.material_usages.values_list('source_movement__document_id', flat=True)
        list(WarehouseDocument.objects.select_for_update().filter(pk__in=document_ids).order_by('pk'))
        output.is_cancelled = True
        output.cancelled_at = timezone.now()
        output.cancelled_by = user
        output.save(update_fields=['is_cancelled', 'cancelled_at', 'cancelled_by'])
    return JsonResponse({'cancelled': True})


def _require_knowledge_permission(request):
    user, error = _require_auth(request)
    if error:
        return None, error
    permission_code = _method_permission(request)
    if permission_code is None:
        return None, _method_not_allowed()
    if not (_is_admin(user) or _has_permission(user, MODULE_KNOWLEDGE_BASE, permission_code)):
        return None, _permission_denied()
    return user, None


def _serialize_knowledge_category(category):
    return {'id': category.pk, 'name': category.name, 'description': category.description}


def _serialize_knowledge_article(article):
    return {
        'id': article.pk,
        'category_id': article.category_id,
        'category': _serialize_knowledge_category(article.category),
        'title': article.title,
        'summary': article.summary,
        'content': article.content,
        'created_at': article.created_at.isoformat(),
        'updated_at': article.updated_at.isoformat(),
        'created_by': article.created_by.get_username() if article.created_by else '',
        'updated_by': article.updated_by.get_username() if article.updated_by else '',
    }


def _knowledge_text(body, field, label, max_length, default='', required=False):
    value = body.get(field, default)
    if not isinstance(value, str):
        raise ValueError(f'Поле «{label}» должно содержать текст.')
    value = value.strip()
    if required and not value:
        raise ValueError(f'Заполните поле «{label}».')
    if len(value) > max_length:
        raise ValueError(f'Поле «{label}» не должно превышать {max_length} символов.')
    return value


def _knowledge_category_values(body, instance=None):
    return {
        'name': _knowledge_text(body, 'name', 'Название раздела', 120, instance.name if instance else '', True),
        'description': _knowledge_text(body, 'description', 'Описание раздела', 300, instance.description if instance else ''),
    }


def _knowledge_article_values(body, instance=None):
    category_id = body.get('category_id', instance.category_id if instance else None)
    if isinstance(category_id, bool) or len(str(category_id)) > 18 or not str(category_id).isdecimal():
        raise ValueError('Выберите раздел базы знаний.')
    category = KnowledgeCategory.objects.filter(pk=int(category_id)).first()
    if category is None:
        raise ValueError('Раздел базы знаний не найден.')
    return {
        'category': category,
        'title': _knowledge_text(body, 'title', 'Заголовок', 200, instance.title if instance else '', True),
        'summary': _knowledge_text(body, 'summary', 'Краткое описание', 500, instance.summary if instance else ''),
        'content': _knowledge_text(body, 'content', 'Текст статьи', 100000, instance.content if instance else '', True),
    }


@csrf_exempt
def knowledge_categories_view(request):
    _, error = _require_knowledge_permission(request)
    if error:
        return error
    if request.method == 'GET':
        return JsonResponse({'items': [_serialize_knowledge_category(item) for item in KnowledgeCategory.objects.all()]})
    if request.method != 'POST':
        return _method_not_allowed()
    body = _json_body(request)
    if not isinstance(body, dict):
        return _invalid_json_body()
    try:
        values = _knowledge_category_values(body)
        with transaction.atomic():
            category = KnowledgeCategory.objects.create(**values)
    except ValueError as exc:
        return _json_error(str(exc), status=400)
    except IntegrityError:
        return _json_error('Раздел с таким названием уже существует.', status=400)
    return JsonResponse(_serialize_knowledge_category(category), status=201)


@csrf_exempt
def knowledge_category_detail_view(request, category_id):
    _, error = _require_knowledge_permission(request)
    if error:
        return error
    category = KnowledgeCategory.objects.filter(pk=category_id).first()
    if category is None:
        return _json_error('Раздел базы знаний не найден.', status=404)
    if request.method == 'GET':
        return JsonResponse(_serialize_knowledge_category(category))
    if request.method in ('PUT', 'PATCH'):
        body = _json_body(request)
        if not isinstance(body, dict):
            return _invalid_json_body()
        try:
            values = _knowledge_category_values(body, category)
            with transaction.atomic():
                for field, value in values.items():
                    setattr(category, field, value)
                category.save()
        except ValueError as exc:
            return _json_error(str(exc), status=400)
        except IntegrityError:
            return _json_error('Раздел с таким названием уже существует.', status=400)
        return JsonResponse(_serialize_knowledge_category(category))
    if request.method == 'DELETE':
        try:
            category.delete()
        except ProtectedError:
            return _json_error('Перенесите или удалите статьи раздела перед его удалением.', status=400)
        return JsonResponse({'deleted': True})
    return _method_not_allowed()


def _knowledge_article_queryset():
    return KnowledgeArticle.objects.select_related('category', 'created_by', 'updated_by')


@csrf_exempt
def knowledge_articles_view(request):
    user, error = _require_knowledge_permission(request)
    if error:
        return error
    if request.method == 'GET':
        articles = _knowledge_article_queryset()
        return JsonResponse({'items': [_serialize_knowledge_article(item) for item in articles]})
    if request.method != 'POST':
        return _method_not_allowed()
    body = _json_body(request)
    if not isinstance(body, dict):
        return _invalid_json_body()
    try:
        values = _knowledge_article_values(body)
    except ValueError as exc:
        return _json_error(str(exc), status=400)
    with transaction.atomic():
        article = KnowledgeArticle.objects.create(**values, created_by=user, updated_by=user)
    return JsonResponse(_serialize_knowledge_article(article), status=201)


@csrf_exempt
def knowledge_article_detail_view(request, article_id):
    user, error = _require_knowledge_permission(request)
    if error:
        return error
    article = _knowledge_article_queryset().filter(pk=article_id).first()
    if article is None:
        return _json_error('Статья базы знаний не найдена.', status=404)
    if request.method == 'GET':
        return JsonResponse(_serialize_knowledge_article(article))
    if request.method in ('PUT', 'PATCH'):
        body = _json_body(request)
        if not isinstance(body, dict):
            return _invalid_json_body()
        try:
            values = _knowledge_article_values(body, article)
        except ValueError as exc:
            return _json_error(str(exc), status=400)
        with transaction.atomic():
            for field, value in values.items():
                setattr(article, field, value)
            article.updated_by = user
            article.save()
        return JsonResponse(_serialize_knowledge_article(article))
    if request.method == 'DELETE':
        article.delete()
        return JsonResponse({'deleted': True})
    return _method_not_allowed()
