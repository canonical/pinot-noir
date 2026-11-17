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
from .forms import HousekeepingSettingsForm
from .models import HousekeepingSettings
from .tasks import refresh_bug_housekeeping

COMMANDS = [
    Command(
        refresh_bug_housekeeping,
        "Refresh bug housekeeping",
        "Generate startriage's interactive housekeeping report for the default team, "
        "commit the saved-bug list, and push it when the running user has an SSH key.",
    ),
]


@staff_member_required(login_url="login")
@require_http_methods(["GET", "POST"])
def index(request: HttpRequest) -> HttpResponse:
    """Saved-bugs Git settings, the housekeeping schedule, and commands to run now."""
    instance = HousekeepingSettings.objects.first() or HousekeepingSettings()
    action = request.POST.get("action", "")
    form = HousekeepingSettingsForm(
        request.POST if action == "git-settings" else None,
        instance=instance,
        prefix="git",
    )
    schedule_form: ScheduleForm | None = None

    if action == "git-settings":
        if form.is_valid():
            form.save()
            messages.success(request, "Saved the Git repository settings.")
            return redirect(request.path)
    elif request.method == "POST":
        task_result = handle_task_post(request, COMMANDS)
        if isinstance(task_result, HttpResponse):
            return task_result
        schedule_form = task_result

    return render(
        request,
        "bug_housekeeping/manage.html",
        {
            "title": "Bug Housekeeping",
            "form": form,
            "settings_saved": instance.pk is not None,
            **task_sections(request, COMMANDS, PAGE_SLUG, schedule_form),
        },
    )
