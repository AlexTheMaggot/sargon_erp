from datetime import datetime, timedelta, timezone

import jwt
from django.conf import settings
from django.contrib.auth import get_user_model


JWT_ALGORITHM = 'HS256'


def create_access_token(user):
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=settings.JWT_ACCESS_TOKEN_LIFETIME_MINUTES)
    payload = {
        'sub': str(user.pk),
        'username': user.get_username(),
        'iat': int(now.timestamp()),
        'exp': int(expires_at.timestamp()),
        'type': 'access',
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=JWT_ALGORITHM)


def get_user_from_token(token):
    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[JWT_ALGORITHM])
    if payload.get('type') != 'access':
        raise jwt.InvalidTokenError('Invalid token type')

    user_id = payload.get('sub')
    if not user_id:
        raise jwt.InvalidTokenError('Missing subject')

    return get_user_model().objects.get(pk=user_id)
