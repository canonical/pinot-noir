from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from pinot_noir.data_manager.models import MergeBugFilterSettings
from pinot_noir.data_manager.tasks import submit_backport_bugs, submit_merge_bugs
from pinot_noir.site_admin.page_tasks import (
    Command,
    handle_task_post,
    has_lp_token,
    task_sections,
)

from .apps import PAGE_SLUG
from .forms import FIELDS, FilterEntryForm, get_filter_settings, remove_filter_entry
from .models import Merge
from .tasks import refresh_merge_schedule, update_schedule_bug_filter

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


def _filter_values(kind: str, field: str) -> list[str]:
    settings = get_filter_settings(kind)
    return list(getattr(settings, field)) if settings else []


def _queue_filter_update(
    request: HttpRequest, kind: str, field: str, previous_values: list[str]
) -> str:
    """Queue a requested Launchpad update and return text for the success message."""
    bug_ids = list(
        Merge.objects.filter(merge_type=kind).order_by("lp_bug").values_list("lp_bug", flat=True)
    )
    if not bug_ids:
        return f" There are no existing {kind} bugs on the schedule."

    update_schedule_bug_filter.enqueue(
        username=request.user.get_username(),
        field=field,
        previous_values=previous_values,
        values=_filter_values(kind, field),
        bug_ids=bug_ids,
    )
    suffix = "" if len(bug_ids) == 1 else "s"
    return f" Queued updates for {len(bug_ids)} existing {kind} bug{suffix}."


def _filter_post(
    request: HttpRequest, forms: dict[tuple[str, str], FilterEntryForm]
) -> HttpResponse | FilterEntryForm | None:
    """Handle a settings POST, returning a redirect or a bound invalid add form."""
    action = request.POST.get("action", "")
    if action == "filter-edit":
        action = "filter-add" if "add_entry" in request.POST else "filter-remove"
    kind, field = request.POST.get("settings_type", ""), request.POST.get("field", "")
    if (kind, field) not in forms:
        messages.error(request, "Unknown setting.")
        return redirect(request.path)

    update_bugs = "update_bugs" in request.POST or f"{kind}-{field}-update_bugs" in request.POST
    if update_bugs and not has_lp_token(request.user):
        messages.error(
            request,
            "Add your Launchpad token in My tokens before updating existing bugs.",
        )
        return redirect(request.path)

    previous_values = _filter_values(kind, field)
    if action == "filter-add":
        form = FilterEntryForm(request.POST, settings_type=kind, field=field)
        if not form.is_valid():
            if not has_lp_token(request.user):
                form.fields["update_bugs"].widget.attrs["disabled"] = True
            return form
        message = f"Added {form.save()}."
    else:
        value = request.POST.get("value", "")
        error = remove_filter_entry(kind, field, value)
        if error:
            messages.error(request, error)
            return redirect(request.path)
        message = f"Removed {value}."

    if update_bugs:
        message += _queue_filter_update(request, kind, field, previous_values)
    messages.success(request, message)
    return redirect(request.path)


@staff_member_required(login_url="login")
@require_http_methods(["GET", "POST"])
def index(request: HttpRequest) -> HttpResponse:
    """Merge Schedule settings, its schedule, and commands to run now."""
    forms = {
        (kind, field): FilterEntryForm(settings_type=kind, field=field)
        for kind, _, _ in FILTERS
        for field in FIELDS
    }
    if not has_lp_token(request.user):
        for filter_form in forms.values():
            filter_form.fields["update_bugs"].widget.attrs["disabled"] = True
    schedule_form = None
    action = request.POST.get("action", "")
    if request.method == "POST" and action.startswith("filter-"):
        filter_result = _filter_post(request, forms)
        if isinstance(filter_result, HttpResponse):
            return filter_result
        if filter_result is not None:
            forms[(filter_result.settings_type, filter_result.field)] = filter_result
    elif request.method == "POST":
        task_result = handle_task_post(request, COMMANDS)
        if isinstance(task_result, HttpResponse):
            return task_result
        schedule_form = task_result

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
