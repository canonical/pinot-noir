from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.http import Http404, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.urls import NoReverseMatch, reverse
from django.views.decorators.http import require_http_methods

from pinot_noir.bug_triage.forms import (
    TEAM_LISTS,
    DefaultTeamForm,
    StartriageAISettingsForm,
    TeamEntryForm,
    default_team,
    entry_name,
    remove_team_entry,
)
from pinot_noir.bug_triage.models import StartriageAISettings, StartriageTeam
from pinot_noir.data_manager.models import TeamSettings
from pinot_noir.pages.models import PageMetadata
from pinot_noir.pages.registry import get_page, get_pages

from .forms import TeamNameForm
from .lp_roles import TEAM_MEMBER, handle_role_post, role_tables
from .page_tasks import handle_schedule_post, task_schedule_context
from .sections import SECTIONS


def _startriage_team_list_post(
    request: HttpRequest, team: StartriageTeam | None
) -> HttpResponse | TeamEntryForm:
    """Add or remove one default-team list entry; return a bound form on failure."""
    field = request.POST.get("field", "")
    if team is None or field not in TEAM_LISTS:
        messages.error(request, "Save the default team first.")
        return redirect(request.path)
    if request.POST.get("action") == "team-add":
        form = TeamEntryForm(request.POST, field=field, team=team)
        if not form.is_valid():
            return form
        messages.success(request, f"Added {form.save()}.")
        return redirect(request.path)
    value = request.POST.get("value", "")
    if remove_team_entry(team, field, value):
        messages.success(request, f"Removed {value}.")
    else:
        messages.error(request, f"{value} isn't in the list.")
    return redirect(request.path)


def _save_startriage_form(request: HttpRequest, form, message: str) -> HttpResponse | None:
    if not form.is_valid():
        return None
    form.save()
    messages.success(request, message)
    return redirect(request.path)


@staff_member_required(login_url="login")
@require_http_methods(["GET", "POST"])
def startriage(request: HttpRequest) -> HttpResponse:
    """Shared Startriage team and AI settings used by both startriage pages."""
    team = default_team()
    ai_instance = StartriageAISettings.objects.first() or StartriageAISettings()
    data = request.POST if request.method == "POST" else None
    action = request.POST.get("action", "")
    ai_form = StartriageAISettingsForm(
        data if action == "ai-settings" else None, instance=ai_instance, prefix="ai"
    )
    team_form = DefaultTeamForm(
        data if action == "team-settings" else None,
        instance=team or StartriageTeam(),
        prefix="team",
    )
    entry_forms = (
        {field: TeamEntryForm(field=field, team=team) for field in TEAM_LISTS} if team else {}
    )

    response: HttpResponse | None = None
    if action == "ai-settings":
        response = _save_startriage_form(request, ai_form, "Saved the AI settings.")
    elif action == "team-settings":
        response = _save_startriage_form(request, team_form, "Saved the default team.")
    elif action in ("team-add", "team-remove"):
        result = _startriage_team_list_post(request, team)
        if isinstance(result, TeamEntryForm):
            entry_forms[result.spec.field] = result
        else:
            response = result
    if response is not None:
        return response

    team_lists = []
    for field, spec in TEAM_LISTS.items():
        if team is None:
            break
        values = [
            {"name": entry_name(entry), "custom": isinstance(entry, dict)}
            for entry in getattr(team, field) or []
        ]
        team_lists.append(
            {
                "spec": spec,
                "form": entry_forms[field],
                "values": values,
                "has_custom": any(value["custom"] for value in values),
            }
        )
    return render(
        request,
        "site_admin/startriage.html",
        {
            "title": "Startriage",
            "team": team,
            "team_form": team_form,
            "team_lists": team_lists,
            "ai_form": ai_form,
            "ai_saved": ai_instance.pk is not None,
            "other_teams": StartriageTeam.objects.filter(is_default=False).count(),
        },
    )


@staff_member_required(login_url="login")
def index(request):
    return redirect(SECTIONS[0].url_name)


@staff_member_required(login_url="login")
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
        {"title": "Pages", "rows": rows},
    )


@staff_member_required(login_url="login")
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


@staff_member_required(login_url="login")
@require_http_methods(["GET", "POST"])
def task_schedule(request: HttpRequest) -> HttpResponse:
    """List and create weekly schedules for every registered task."""
    schedule_form = None
    if request.method == "POST":
        result = handle_schedule_post(request)
        if isinstance(result, HttpResponse):
            return result
        schedule_form = result
    return render(
        request,
        "site_admin/task_schedule.html",
        {"title": "Task Schedule", **task_schedule_context(request, schedule_form)},
    )


@staff_member_required(login_url="login")
@require_http_methods(["GET", "POST"])
def team(request):
    """Team settings page."""
    settings = TeamSettings.current()
    name_form = TeamNameForm(instance=settings, prefix="settings")
    bound = None
    if request.method == "POST" and request.POST.get("action") == "team-name":
        name_form = TeamNameForm(request.POST, instance=settings, prefix="settings")
        if name_form.is_valid():
            name_form.save()
            name = name_form.instance.name
            messages.success(
                request, f"Team name set to {name}." if name else "Team name cleared."
            )
            return redirect("site_admin:team")
    elif request.method == "POST":
        result = handle_role_post(request, [TEAM_MEMBER])
        if isinstance(result, HttpResponse):
            return result
        if result is None:
            return redirect("site_admin:team")
        bound = result

    tables = role_tables([TEAM_MEMBER], bound)
    return render(
        request,
        "site_admin/team.html",
        {
            "title": "My team",
            "name_form": name_form,
            "tables": tables,
        },
    )
