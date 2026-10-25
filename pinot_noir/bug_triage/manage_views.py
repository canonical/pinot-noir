from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from pinot_noir.site_admin.page_tasks import (
    Command,
    ScheduleForm,
    handle_task_post,
    task_sections,
)

from .apps import PAGE_SLUG
from .forms import (
    TEAM_LISTS,
    DefaultTeamForm,
    StartriageAISettingsForm,
    TeamEntryForm,
    default_team,
    entry_name,
    remove_team_entry,
)
from .models import StartriageAISettings, StartriageTeam
from .tasks import refresh_bug_triage

COMMANDS = [
    Command(
        refresh_bug_triage,
        "Refresh bug triage",
        "Replace the triage report with startriage's triage of the default team for the "
        "current day (the previous Friday on weekends), with AI analysis if it is turned on.",
    ),
]


def _team_list_post(
    request: HttpRequest, team: StartriageTeam | None
) -> HttpResponse | TeamEntryForm:
    """Add or remove one entry of a default team list; the bound form if adding failed."""
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


def _save_form(request: HttpRequest, form, message: str) -> HttpResponse | None:
    if not form.is_valid():
        return None
    form.save()
    messages.success(request, message)
    return redirect(request.path)


@staff_member_required
@require_http_methods(["GET", "POST"])
def index(request: HttpRequest) -> HttpResponse:
    """Bug Triage settings (default team, AI), its schedule, and commands to run now."""
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
    schedule_form: ScheduleForm | None = None

    response: HttpResponse | None = None
    if action == "ai-settings":
        response = _save_form(request, ai_form, "Saved the AI settings.")
    elif action == "team-settings":
        response = _save_form(request, team_form, "Saved the default team.")
    elif action in ("team-add", "team-remove"):
        result = _team_list_post(request, team)
        if isinstance(result, TeamEntryForm):
            entry_forms[result.spec.field] = result
        else:
            response = result
    elif request.method == "POST":
        task_result = handle_task_post(request, COMMANDS)
        if isinstance(task_result, HttpResponse):
            response = task_result
        else:
            schedule_form = task_result
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
        "bug_triage/manage.html",
        {
            "title": "Bug Triage",
            "team": team,
            "team_form": team_form,
            "team_lists": team_lists,
            "ai_form": ai_form,
            "ai_saved": ai_instance.pk is not None,
            "other_teams": StartriageTeam.objects.filter(is_default=False).count(),
            **task_sections(request, COMMANDS, PAGE_SLUG, schedule_form),
        },
    )
