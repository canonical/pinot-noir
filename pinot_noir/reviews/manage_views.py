from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods

from pinot_noir.site_admin.forms import LPUserRoleForm
from pinot_noir.site_admin.lp_roles import REVIEW_MARKER, Role, handle_role_post, role_tables
from pinot_noir.site_admin.page_tasks import (
    Command,
    ScheduleForm,
    handle_task_post,
    task_sections,
)

from .apps import PAGE_SLUG
from .tasks import refresh_reviews

COMMANDS = [
    Command(
        refresh_reviews,
        "Refresh reviews",
        "Replace the reviews with the team members' open Launchpad merge proposals that "
        "have a review marker as a reviewer.",
    ),
]


@staff_member_required
@require_http_methods(["GET", "POST"])
def index(request: HttpRequest) -> HttpResponse:
    """Reviews settings (review markers), its schedule, and commands to run now."""
    bound: tuple[Role, LPUserRoleForm] | None = None
    schedule_form: ScheduleForm | None = None
    if request.method == "POST":
        role_result = handle_role_post(request, [REVIEW_MARKER])
        if isinstance(role_result, HttpResponse):
            return role_result
        if role_result is not None:
            bound = role_result
        else:
            task_result = handle_task_post(request, COMMANDS)
            if isinstance(task_result, HttpResponse):
                return task_result
            schedule_form = task_result
    return render(
        request,
        "reviews/manage.html",
        {
            "title": "Reviews",
            "tables": role_tables([REVIEW_MARKER], bound),
            **task_sections(request, COMMANDS, PAGE_SLUG, schedule_form),
        },
    )
