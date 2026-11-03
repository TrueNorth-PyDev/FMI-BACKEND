"""
JWT authentication that also honours session revocation.
"""
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken

from .models import UserSession

SESSION_CLAIM = 'sid'


class SessionJWTAuthentication(JWTAuthentication):
    """
    Rejects access tokens whose login session (the `sid` claim) has been revoked,
    so signing a session out takes effect immediately rather than when the
    15-minute access token expires. Tokens without the claim (issued before
    session tracking) are accepted until they expire.
    """

    def get_user(self, validated_token):
        user = super().get_user(validated_token)
        session_id = validated_token.get(SESSION_CLAIM)
        if session_id is not None and not UserSession.objects.filter(pk=session_id, user_id=user.pk).exists():
            raise InvalidToken({'detail': 'This session has been signed out.', 'code': 'session_revoked'})
        return user


def current_session_id(request):
    """The UserSession id of the token authenticating this request, if any."""
    token = getattr(request, 'auth', None)
    try:
        return token.get(SESSION_CLAIM) if token is not None else None
    except AttributeError:
        return None
