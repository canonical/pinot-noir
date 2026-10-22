from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.http import Http404, HttpRequest, JsonResponse
from django.shortcuts import redirect, render
from django.urls import NoReverseMatch, reverse
from django.views.decorators.http import require_http_methods

from pinot_noir.data_manager.models import UserTokens
from pinot_noir.pages.models import PageMetadata
from pinot_noir.pages.registry import get_page, get_pages

from .forms import TokensForm
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
