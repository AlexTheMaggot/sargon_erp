from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.core.exceptions import ObjectDoesNotExist
from jwt import PyJWTError

from .auth import get_user_from_token
from .models import UserProfile


OPERATIONS_GROUP = 'operations'


@database_sync_to_async
def _get_user_access(token):
    user = get_user_from_token(token)
    profile, _ = UserProfile.objects.select_related('group').get_or_create(user=user)
    if profile.group is None:
        return user.pk, {}

    access_rows = profile.group.module_access.select_related('module').prefetch_related('permissions')
    access_map = {}
    for access in access_rows:
        if not access.module.is_active:
            continue
        permission_codes = set(access.permissions.values_list('code', flat=True))
        if not permission_codes:
            permission_codes.add('view')
        access_map[access.module.code] = sorted(permission_codes)
    return user.pk, access_map


class OperationsConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        query_params = parse_qs(self.scope.get('query_string', b'').decode())
        token = query_params.get('token', [''])[0]

        try:
            self.user_id, self.access = await _get_user_access(token)
        except (ObjectDoesNotExist, PyJWTError, ValueError):
            await self.close(code=4401)
            return

        if not self._can_view_operations():
            await self.close(code=4403)
            return

        await self.channel_layer.group_add(OPERATIONS_GROUP, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(OPERATIONS_GROUP, self.channel_name)

    async def operations_event(self, event):
        payload = event.get('payload', {})
        target_module = payload.get('target_module')
        if target_module and not self._can_view_module(target_module):
            return

        await self.send_json(payload)

    def _can_view_operations(self):
        return (
            self._can_view_module('raw-material-receiving')
            or self._can_view_module('laboratory-analysis')
        )

    def _can_view_module(self, module_code):
        return 'view' in self.access.get(module_code, [])
