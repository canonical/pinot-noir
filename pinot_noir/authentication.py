from django.conf import settings
from django.core.exceptions import SuspiciousOperation
from mozilla_django_oidc.auth import OIDCAuthenticationBackend


class GoogleOIDCAuthenticationBackend(OIDCAuthenticationBackend):
    """Authenticate an existing Django user with a verified Google email."""

    GOOGLE_ISSUERS = {"https://accounts.google.com", "accounts.google.com"}

    def verify_token(self, token: str, **kwargs):
        payload = super().verify_token(token, **kwargs)
        if payload.get("aud") != self.OIDC_RP_CLIENT_ID:
            raise SuspiciousOperation("Google ID token has the wrong audience.")
        if payload.get("iss") not in self.GOOGLE_ISSUERS:
            raise SuspiciousOperation("Google ID token has the wrong issuer.")
        return payload

    def verify_claims(self, claims):
        return super().verify_claims(claims) and claims.get("email_verified") is True

    def filter_users_by_claims(self, claims):
        email = claims.get("email", "").strip()
        if not email or claims.get("email_verified") is not True:
            return self.UserModel.objects.none()
        users = self.UserModel.objects.filter(email__iexact=email, is_active=True)
        # Django email addresses are not unique; never choose an ambiguous account.
        if users.count() != 1:
            return self.UserModel.objects.none()
        return users


def google_oauth(request):
    """Expose only non-secret Google OAuth state to the login template."""
    return {
        "google_oauth_enabled": bool(
            settings.OIDC_RP_CLIENT_ID and settings.OIDC_RP_CLIENT_SECRET
        ),
        "google_oauth_failed": request.GET.get("oauth") == "failed",
    }
