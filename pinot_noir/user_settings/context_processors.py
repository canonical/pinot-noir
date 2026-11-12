from django.urls import reverse

from .models import Preferences


def user_settings(request):
    """Expose the user's theme, Account settings link, and settings navigation."""
    context: dict[str, object] = {"user_theme": Preferences.Theme.LIGHT}
    user = getattr(request, "user", None)
    if user is None or not (user.is_authenticated and user.is_active):
        return context
    preferences = Preferences.objects.filter(user=user).only("theme").first()
    if preferences is not None:
        context["user_theme"] = preferences.theme
    index_url = reverse("user_settings:index")
    path = getattr(request, "path", "") or ""
    context["user_settings_nav"] = {
        "url": index_url,
        "is_active": path.startswith(index_url),
    }
    if path.startswith(index_url):
        context["user_settings_sections"] = [
            {
                "label": label,
                "url": reverse(url_name),
                "is_active": path == reverse(url_name),
            }
            for url_name, label in (
                ("user_settings:general", "General"),
                ("user_settings:tokens", "My tokens"),
            )
        ]
    return context
