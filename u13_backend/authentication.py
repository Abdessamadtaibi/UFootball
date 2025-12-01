from django.core.exceptions import ValidationError
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.settings import api_settings


class UUIDSafeJWTAuthentication(JWTAuthentication):
    """
    JWT authentication that avoids 500 errors when the token carries a
    non-UUID user identifier (e.g., tokens minted before switching to UUID PKs).

    Instead of letting Django raise ValidationError/ValueError during user lookup,
    we convert these into AuthenticationFailed (401) so the API responds cleanly
    and clients can re-authenticate.
    """

    def get_user(self, validated_token):
        try:
            user_id = validated_token[api_settings.USER_ID_CLAIM]
        except KeyError:
            raise AuthenticationFailed(
                'Token missing user identifier.', code='token_no_user_id'
            )

        try:
            return self.user_model.objects.get(
                **{api_settings.USER_ID_FIELD: user_id}
            )
        except (ValueError, ValidationError, self.user_model.DoesNotExist):
            # Likely an old token with an integer user_id after UUID migration
            raise AuthenticationFailed(
                'Invalid or expired token. Please log in again.',
                code='token_invalid_user_id'
            )