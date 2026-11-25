from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from pinot_noir.site_admin.page_tasks import Command, handle_task_post, task_sections

from .apps import PAGE_SLUG
from .forms import TriageSettingsForm
from .models import TriageSettings
from .tasks import refresh_bug_triage

COMMANDS = [
    Command(
        refresh_bug_triage,
        "Refresh bug triage",
        "Generate startriage's triage of the default team for the current day "
        "(the previous Friday on weekends), with AI analysis if it is turned on.",
    ),
]


@staff_member_required(login_url="login")
@require_http_methods(["GET", "POST"])
def index(request: HttpRequest) -> HttpResponse:
    """Bug Triage report-history settings and refresh commands."""
    action = request.POST.get("action", "")
    history_instance = TriageSettings.current()
    history_form = TriageSettingsForm(
        request.POST if action == "history-settings" else None,
        instance=history_instance,
        prefix="history",
    )
    if action == "history-settings" and history_form.is_valid():
        history_form.save()
        history_instance.prune_reports()
        messages.success(request, "Saved the report history settings.")
        return redirect(request.path)

    if request.method == "POST":
        result = handle_task_post(request, COMMANDS)
        if isinstance(result, HttpResponse):
            return result
    return render(
        request,
        "bug_triage/manage.html",
        {
            "title": "Bug Triage",
            "history_form": history_form,
            **task_sections(request, COMMANDS, PAGE_SLUG),
        },
    )
