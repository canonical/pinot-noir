from django.urls import reverse

from .sections import section_entries


def site_admin(request):
    """Expose the sidebar link to the site admin, and its own side nav, for staff only."""
    user = getattr(request, "user", None)
    if user is None or not (user.is_active and user.is_staff):
        return {}
    url = reverse("site_admin:index")
    path = getattr(request, "path", "") or ""
    context: dict[str, object] = {
        "site_admin_nav": {"url": url, "is_active": path.startswith(url)}
    }
    if path.startswith(url):
        context["site_admin_sections"] = section_entries(path)
    return context
