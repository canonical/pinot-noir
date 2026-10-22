"""Schedule and Commands sections shared by every page's admin section.

A page admin lists its tasks as :class:`Command` entries, passes POSTs through
:func:`handle_task_post`, and adds :func:`task_sections` to its template context.
The templates are ``site_admin/_schedule.html`` and ``site_admin/_commands.html``.
"""

from dataclasses import dataclass

from django import forms
from django.contrib import messages
from django.contrib.auth.models import User
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django_tasks.base import Task
from django_tasks_db.models import DBTaskResult

from pinot_noir.data_manager.models import UserTokens, WeeklyTask
from pinot_noir.data_manager.tasks import get_schedulable_tasks, schedule_weekly_tasks
from pinot_noir.pages.models import PageMetadata

DAY_CHOICES = [(day, day.capitalize()) for day in WeeklyTask.WEEKDAY_FIELDS]


@dataclass(frozen=True)
class Command:
    """A task an admin can run now or schedule. Its first parameter is ``username``."""

    task: Task
    label: str
    description: str

    @property
    def name(self) -> str:
        return self.task.name


class ScheduleForm(forms.ModelForm):
    days = forms.MultipleChoiceField(
        choices=DAY_CHOICES, widget=forms.CheckboxSelectMultiple, label="Days"
    )

    class Meta:
        model = WeeklyTask
        fields = ["task", "time_of_day", "user"]
        labels = {"time_of_day": "Time (UTC)", "user": "Run as"}
        widgets = {"time_of_day": forms.TimeInput(attrs={"type": "time"}, format="%H:%M")}

    def __init__(self, *args, commands: list[Command], **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["task"] = forms.ChoiceField(
            choices=[(command.name, command.label) for command in commands], label="Task"
        )
        user = self.fields["user"]
        assert isinstance(user, forms.ModelChoiceField)
        user.queryset = User.objects.filter(is_staff=True, is_active=True).order_by("username")
        user.required = True
        user.empty_label = None
        for name in ("task", "time_of_day", "user"):
            self.fields[name].widget.attrs["class"] = "p-form-validation__input"

    def save(self, commit: bool = True) -> WeeklyTask:
        weekly_task = super().save(commit=False)
        for day in WeeklyTask.WEEKDAY_FIELDS:
            setattr(weekly_task, day, day in self.cleaned_data["days"])
        if commit:
            weekly_task.save()
        return weekly_task


def has_lp_token(user) -> bool:
    # EncryptedTextField stores "" unencrypted, so this comparison is valid.
    return UserTokens.objects.filter(user=user).exclude(lp_token="").exists()


def _cancel_queued_run(weekly_task: WeeklyTask) -> None:
    """Drop the run the scheduler already queued, so pausing or removing takes effect now."""
    task = get_schedulable_tasks().get(weekly_task.task)
    if task is not None and weekly_task.next_run is not None:
        DBTaskResult.objects.filter(
            task_path=task.module_path, status="READY", run_after=weekly_task.next_run
        ).delete()
    weekly_task.next_run = None


def handle_task_post(
    request: HttpRequest, commands: list[Command]
) -> HttpResponse | ScheduleForm | None:
    """Handle a Schedule or Commands POST.

    Returns a redirect when the action was handled, the bound form when adding a
    schedule failed validation, or None when the POST was not for these sections.
    """
    by_name = {command.name: command for command in commands}
    action = request.POST.get("action", "")

    if action == "run":
        command = by_name.get(request.POST.get("task", ""))
        if command is None:
            messages.error(request, "Unknown command.")
        elif not has_lp_token(request.user):
            messages.error(request, "Add your Launchpad token in My tokens first.")
        else:
            command.task.enqueue(username=request.user.get_username())
            messages.success(request, f"Queued: {command.label}.")
        return redirect(request.path)

    if action == "schedule-add":
        form = ScheduleForm(request.POST, prefix="schedule", commands=commands)
        if not form.is_valid():
            return form
        weekly_task = form.save()
        messages.success(request, f"Scheduled {by_name[weekly_task.task].label}.")
        return redirect(request.path)

    if action in ("schedule-pause", "schedule-resume", "schedule-remove"):
        weekly_task = get_object_or_404(
            WeeklyTask, pk=request.POST.get("id"), task__in=list(by_name)
        )
        label = by_name[weekly_task.task].label
        _cancel_queued_run(weekly_task)
        if action == "schedule-remove":
            weekly_task.delete()
            messages.success(request, f"Removed a {label} schedule.")
        else:
            weekly_task.enabled = action == "schedule-resume"
            weekly_task.save(update_fields=["enabled", "next_run"])
            state = "Resumed" if weekly_task.enabled else "Paused"
            messages.success(request, f"{state} a {label} schedule.")
        return redirect(request.path)

    return None


def task_sections(
    request: HttpRequest,
    commands: list[Command],
    page_slug: str,
    schedule_form: ScheduleForm | None = None,
) -> dict:
    """Template context for ``_schedule.html`` and ``_commands.html``."""
    labels = {command.name: command.label for command in commands}
    rows = [
        {
            "task": weekly_task,
            "label": labels[weekly_task.task],
            "has_token": weekly_task.user is not None and has_lp_token(weekly_task.user),
        }
        for weekly_task in WeeklyTask.objects.filter(task__in=list(labels)).select_related("user")
    ]
    if schedule_form is None:
        schedule_form = ScheduleForm(
            prefix="schedule", commands=commands, initial={"user": request.user.pk}
        )
    scheduler_running = DBTaskResult.objects.filter(
        task_path=schedule_weekly_tasks.module_path, status__in=["READY", "RUNNING"]
    ).exists()
    meta = PageMetadata.objects.filter(slug=page_slug).first()
    return {
        "commands": commands,
        "schedule_rows": rows,
        "schedule_form": schedule_form,
        "scheduler_running": scheduler_running,
        "user_has_lp_token": has_lp_token(request.user),
        "last_refreshed_at": meta.last_refreshed_at if meta else None,
    }
