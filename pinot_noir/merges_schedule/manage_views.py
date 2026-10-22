from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from pinot_noir.data_manager.models import MergeBugFilterSettings
from pinot_noir.data_manager.tasks import submit_backport_bugs, submit_merge_bugs
from pinot_noir.site_admin.page_tasks import Command, handle_task_post, task_sections

from .apps import PAGE_SLUG
from .forms import FIELDS, FilterEntryForm, get_filter_settings, remove_filter_entry
from .tasks import refresh_merge_schedule

COMMANDS = [
    Command(
        refresh_merge_schedule,
        "Refresh merge schedule",
        "Replace the schedule with the bugs that have the merge or backport tags and a "
        "milestone in the development release cycle, then refresh each bug's details.",
    ),
    Command(
        submit_merge_bugs,
        "Submit merge bugs",
        "File a merge bug in the development release for each merge package that needs "
        "one and hasn't had one filed this cycle.",
    ),
    Command(
        submit_backport_bugs,
        "Submit backport bugs",
        "File a backport bug in the development release for each backport package that "
        "hasn't had one filed this cycle.",
    ),
]

# (settings type, heading, what the bugs are called in help text)
FILTERS = (
    (MergeBugFilterSettings.TYPE_MERGE, "Merge bugs", "merge"),
    (MergeBugFilterSettings.TYPE_BACKPORT, "Backport bugs", "backport"),
)


@staff_member_required
@require_http_methods(["GET", "POST"])
def index(request: HttpRequest) -> HttpResponse:
    """Merge Schedule settings, its schedule, and commands to run now."""
    forms = {
        (kind, field): FilterEntryForm(settings_type=kind, field=field)
        for kind, _, _ in FILTERS
        for field in FIELDS
    }
    schedule_form = None
    action = request.POST.get("action", "")
    kind, field = request.POST.get("settings_type", ""), request.POST.get("field", "")
    if request.method == "POST" and action.startswith("filter-"):
        if (kind, field) not in forms:
            messages.error(request, "Unknown setting.")
            return redirect(request.path)
        if action == "filter-add":
            form = FilterEntryForm(request.POST, settings_type=kind, field=field)
            if form.is_valid():
                messages.success(request, f"Added {form.save()}.")
                return redirect(request.path)
            forms[(kind, field)] = form
        else:
            value = request.POST.get("value", "")
            error = remove_filter_entry(kind, field, value)
            if error:
                messages.error(request, error)
            else:
                messages.success(request, f"Removed {value}.")
            return redirect(request.path)
    elif request.method == "POST":
        result = handle_task_post(request, COMMANDS)
        if isinstance(result, HttpResponse):
            return result
        schedule_form = result

    filters = []
    for kind, heading, noun in FILTERS:
        settings = get_filter_settings(kind)
        lists = [
            {
                "field": field,
                "label": label,
                "values": getattr(settings, field) if settings else [],
                "form": forms[(kind, field)],
            }
            for field, (label, _) in FIELDS.items()
        ]
        filters.append({"kind": kind, "heading": heading, "noun": noun, "lists": lists})
    return render(
        request,
        "merges_schedule/manage.html",
        {
            "title": "Merge Schedule",
            "filters": filters,
            **task_sections(request, COMMANDS, PAGE_SLUG, schedule_form),
        },
    )
