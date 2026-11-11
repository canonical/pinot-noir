from django.urls import reverse


def user_settings(request):
    """Expose the Account settings link and the settings area's own navigation."""
    user = getattr(request, "user", None)
    if user is None or not (user.is_authenticated and user.is_active):
        return {}
    index_url = reverse("user_settings:index")
    path = getattr(request, "path", "") or ""
    context: dict[str, object] = {
        "user_settings_nav": {
            "url": index_url,
            "is_active": path.startswith(index_url),
        }
    }
    if path.startswith(index_url):
        tokens_url = reverse("user_settings:tokens")
        context["user_settings_sections"] = [
            {
                "label": "My tokens",
                "url": tokens_url,
                "is_active": path == tokens_url,
            }
        ]
    return context
