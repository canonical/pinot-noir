from django.urls import reverse


def site_admin(request):
    """Expose the sidebar link to the site admin, for staff only."""
    user = getattr(request, "user", None)
    if user is None or not (user.is_active and user.is_staff):
        return {}
    url = reverse("site_admin:index")
    path = getattr(request, "path", "") or ""
    return {"site_admin_nav": {"url": url, "is_active": path.startswith(url)}}
