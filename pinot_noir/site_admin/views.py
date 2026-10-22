from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.http import Http404, HttpRequest, JsonResponse
from django.shortcuts import redirect, render
from django.urls import NoReverseMatch, reverse
from django.views.decorators.http import require_http_methods

from pinot_noir.data_manager.models import UserTokens
from pinot_noir.launchpad.models import LPUser
from pinot_noir.pages.models import PageMetadata
from pinot_noir.pages.registry import get_page, get_pages

from .forms import LPUserRoleForm, ReviewMarkerForm, TokensForm
from .sections import SECTIONS, section_entries


@staff_member_required
def index(request):
    return redirect(SECTIONS[0].url_name)


@staff_member_required
def tokens(request):
    """Let the signed-in user set their own tokens. Stored values are never shown."""
    instance = UserTokens.objects.filter(user=request.user).first() or UserTokens(
        user=request.user
    )
    form = TokensForm(request.POST or None, instance=instance)
    if request.method == "POST" and form.is_valid():
        changed = form.save()
        if changed:
            messages.success(request, f"Updated: {', '.join(changed)}.")
        else:
            messages.info(request, "No tokens changed.")
        return redirect("site_admin:tokens")
    return render(
        request,
        "site_admin/tokens.html",
        {
            "title": "My tokens",
            "form": form,
            "sections": section_entries(request.path),
        },
    )


@staff_member_required
@require_http_methods(["GET", "POST"])
def pages(request):
    """Turn registered pages on and off. A disabled page is hidden from the sidebar."""
    registered = get_pages()
    if request.method == "POST":
        enabled = set(request.POST.getlist("enabled"))
        changed = []
        for page in registered:
            meta, _ = PageMetadata.objects.get_or_create(slug=page.slug)
            want = page.slug in enabled
            if meta.enabled != want:
                meta.enabled = want
                meta.save(update_fields=["enabled"])
                changed.append(f"{page.label} {'enabled' if want else 'disabled'}")
        if changed:
            messages.success(request, f"{', '.join(changed)}.")
        else:
            messages.info(request, "No pages changed.")
        return redirect("site_admin:pages")

    metadata = {m.slug: m for m in PageMetadata.objects.all()}
    rows = []
    for page in registered:
        meta = metadata.get(page.slug)
        try:
            url = reverse(page.url_name)
        except NoReverseMatch:
            url = ""
        rows.append(
            {
                "page": page,
                "url": url,
                "enabled": meta.enabled if meta else True,
                "last_refreshed_at": meta.last_refreshed_at if meta else None,
            }
        )
    return render(
        request,
        "site_admin/pages.html",
        {"title": "Pages", "rows": rows, "sections": section_entries(request.path)},
    )


@staff_member_required
@require_http_methods(["POST"])
def toggle_page(request: HttpRequest, slug: str) -> JsonResponse:
    """Enable or disable one page right away (the Pages switches); answers with JSON."""
    page = get_page(slug)
    if page is None:
        raise Http404(f"No page {slug!r}")
    enabled = request.POST.get("enabled") == "true"
    meta, _ = PageMetadata.objects.get_or_create(slug=slug)
    if meta.enabled != enabled:
        meta.enabled = enabled
        meta.save(update_fields=["enabled"])
    return JsonResponse({"slug": slug, "enabled": meta.enabled})


# role field -> (form prefix, what the table is called in messages, add form)
LP_ROLES = {
    "is_team_member": ("team", "team members", LPUserRoleForm),
    "is_review_marker": ("marker", "review markers", ReviewMarkerForm),
}


@staff_member_required
@require_http_methods(["GET", "POST"])
def team(request):
    """Team settings page."""
    forms = {role: form(prefix=prefix) for role, (prefix, _, form) in LP_ROLES.items()}
    if request.method == "POST":
        role = request.POST.get("role", "")
        if role not in LP_ROLES:
            return redirect("site_admin:team")
        prefix, table, form_class = LP_ROLES[role]
        if request.POST.get("action") == "remove":
            username = request.POST.get("username", "")
            if LPUser.objects.filter(username=username).update(**{role: False}):
                messages.success(request, f"Removed {username} from {table}.")
            return redirect("site_admin:team")
        form = form_class(request.POST, prefix=prefix)
        if form.is_valid():
            user, already = form.save(role)
            if already:
                messages.info(request, f"{user.username} is already in {table}.")
            else:
                messages.success(request, f"Added {user.username} to {table}.")
            return redirect("site_admin:team")
        forms[role] = form

    tables = [
        {
            "role": role,
            "title": table.capitalize(),
            "form": forms[role],
            "users": LPUser.objects.filter(**{role: True}).order_by("username"),
        }
        for role, (_prefix, table, _form) in LP_ROLES.items()
    ]
    tables[0]["description"] = "Launchpad users on the team."
    tables[1]["description"] = (
        "Launchpad usernames for users or teams that, when assigned to a Launchpad merge "
        "proposal, mark it to be added on the Reviews page."
    )
    return render(
        request,
        "site_admin/team.html",
        {"title": "My team", "tables": tables, "sections": section_entries(request.path)},
    )
