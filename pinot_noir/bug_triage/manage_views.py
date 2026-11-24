from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods

from pinot_noir.site_admin.page_tasks import Command, handle_task_post, task_sections

from .apps import PAGE_SLUG
from .tasks import refresh_bug_triage

COMMANDS = [
    Command(
        refresh_bug_triage,
        "Refresh bug triage",
        "Replace the triage report with startriage's triage of the default team for the "
        "current day (the previous Friday on weekends), with AI analysis if it is turned on.",
    ),
]


@staff_member_required(login_url="login")
@require_http_methods(["GET", "POST"])
def index(request: HttpRequest) -> HttpResponse:
    """Commands to refresh Bug Triage using the shared Startriage settings."""
    if request.method == "POST":
        result = handle_task_post(request, COMMANDS)
        if isinstance(result, HttpResponse):
            return result
    return render(
        request,
        "bug_triage/manage.html",
        {"title": "Bug Triage", **task_sections(request, COMMANDS, PAGE_SLUG)},
    )
