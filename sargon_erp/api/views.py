import json
from decimal import Decimal
from decimal import InvalidOperation
from decimal import ROUND_HALF_UP

import jwt
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.contrib.auth import authenticate
from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.db.models import Max
from django.db.models import Sum
from django.db.models import ProtectedError
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
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
from .models import Permission
from .models import RawMaterialReceipt
from .models import ReceiptBatch
from .models import Supplier
from .models import UserProfile


MODULE_ACCESS = 'access'
MODULE_DASHBOARD = 'dashboard'
MODULE_LABORATORY = 'laboratory-analysis'
MODULE_RAW_MATERIAL = 'raw-material-receiving'
MODULE_SUPPLIERS = 'suppliers'

PERMISSION_APPROVE = 'approve'
PERMISSION_VIEW = 'view'


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
        return '/welcome'

    access_map = _user_access_map(user)
    start_module = profile.group.start_module
    if (
        start_module
        and start_module.is_active
        and start_module.default_path
        and PERMISSION_VIEW in access_map.get(start_module.code, [])
    ):
        return start_module.default_path

    if PERMISSION_VIEW in access_map.get(MODULE_DASHBOARD, []):
        return '/welcome'

    module = (
        Module.objects
        .filter(group_access__group=profile.group, group_access__permissions__code=PERMISSION_VIEW, is_active=True)
        .exclude(default_path='')
        .order_by('name')
        .first()
    )
    return module.default_path if module else '/welcome'


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
        'can_set_quantity': is_analysis_approved and not is_analysis_rejected,
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

    has_approved_batch = False
    for batch in batches:
        analysis = _get_batch_laboratory_analysis(batch)
        if analysis is None or not (analysis.is_approved or analysis.is_rejected):
            return False
        if analysis.is_approved:
            has_approved_batch = True
            if batch.input_quantity is None or batch.input_quantity <= 0:
                return False
            if _calculate_quantity_liters(batch, analysis.density) is None:
                return False
    return has_approved_batch


def _is_admin(user):
    if user.is_superuser or user.is_staff:
        return True

    profile, _ = UserProfile.objects.select_related('group').get_or_create(user=user)
    return profile.group is not None and profile.group.name == 'Администраторы'



def _boolean_value(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ('1', 'true', 'yes', 'on')
    return bool(value)


def _validate_laboratory_values(values, require_all=False):
    if require_all and any(value is None for value in values.values()):
        return 'All laboratory values must be valid numbers.'
    if values.get('density') is not None and values['density'] <= 0:
        return 'Density must be a positive number.'
    if values.get('water_percentage') is not None and not Decimal('0') <= values['water_percentage'] <= Decimal('100'):
        return 'Water percentage must be between 0 and 100.'
    return None


def _sync_group_modules(group, module_ids):
    if module_ids is None:
        return

    modules = list(Module.objects.filter(pk__in=module_ids))
    if len(modules) != len(set(module_ids)):
        raise ValueError('One or more modules do not exist.')

    GroupModuleAccess.objects.filter(group=group).exclude(module_id__in=module_ids).delete()
    for module in modules:
        GroupModuleAccess.objects.get_or_create(group=group, module=module)


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
            _sync_group_modules(group, body.get('module_ids', []))
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
            _sync_group_modules(group, body.get('module_ids'))
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
            if not _can_complete_receipt(receipt):
                return JsonResponse({'detail': 'Receipt can be completed only after all batches have final laboratory decisions and approved batches have quantity.'}, status=400)
            for batch in receipt.batches.all():
                analysis = _get_batch_laboratory_analysis(batch)
                if analysis and analysis.is_approved:
                    _sync_batch_liters(batch, analysis.density)
            _sync_receipt_liters(receipt)
            receipt.is_completed = True
            receipt.completed_at = timezone.now()
            receipt.save(update_fields=['is_completed', 'completed_at'])
            _broadcast_operations_event(
                'receipt_completed',
                {'receipt_id': receipt.pk},
            )
            return JsonResponse(_serialize_receipt(receipt))

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
        if receipt.is_completed and not _is_admin(user):
            return JsonResponse({'detail': 'Receipt is completed.'}, status=423)

        next_sequence_number = (receipt.batches.aggregate(max_number=Max('sequence_number'))['max_number'] or 0) + 1
        batch = ReceiptBatch.objects.create(receipt=receipt, sequence_number=next_sequence_number)
        LaboratoryAnalysis.objects.create(batch=batch)
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
        receipt_id = batch.receipt_id
        deleted_batch_id = batch.pk
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
