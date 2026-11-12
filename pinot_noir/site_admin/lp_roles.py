"""Team-member and review-marker tables shared by staff management pages."""

from dataclasses import dataclass

from django.contrib import messages
from django.contrib.auth.models import User
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect

from pinot_noir.launchpad.models import ReviewMarker

from .forms import ReviewMarkerForm, RoleForm, TeamMemberForm


@dataclass(frozen=True)
class Role:
    key: str
    prefix: str
    table: str
    form: type[RoleForm]
    description: str


TEAM_MEMBER = Role(
    "team",
    "team",
    "team members",
    TeamMemberForm,
    "Active Django users on the team. Their usernames are used as Launchpad usernames.",
)
REVIEW_MARKER = Role(
    "review-marker",
    "marker",
    "review markers",
    ReviewMarkerForm,
    "Launchpad usernames for users or teams that, when assigned to a Launchpad merge "
    "proposal, mark it to be added on the Reviews page.",
)


def handle_role_post(
    request: HttpRequest, roles: list[Role]
) -> HttpResponse | tuple[Role, RoleForm] | None:
    """Handle an add, deactivate, or remove POST for one of ``roles``."""
    role = next((r for r in roles if r.key == request.POST.get("role")), None)
    if role is None:
        return None
    if request.POST.get("action") == "remove":
        username = request.POST.get("username", "")
        if role == TEAM_MEMBER:
            if username == request.user.get_username():
                messages.error(request, "You cannot deactivate your own account.")
            elif User.objects.filter(username=username, is_active=True).update(is_active=False):
                messages.success(request, f"Deactivated {username}.")
        else:
            deleted, _ = ReviewMarker.objects.filter(username=username).delete()
            if deleted:
                messages.success(request, f"Removed {username} from {role.table}.")
        return redirect(request.path)
    form = role.form(request.POST, prefix=role.prefix)
    if not form.is_valid():
        return role, form
    user, already = form.save()
    if already:
        messages.info(request, f"{user.username} is already in {role.table}.")
    else:
        messages.success(request, f"Added {user.username} to {role.table}.")
    return redirect(request.path)


def role_tables(roles: list[Role], bound: tuple[Role, RoleForm] | None = None) -> list:
    """Context for ``_lp_role_table.html``, one entry per role."""
    tables = []
    for role in roles:
        users = (
            User.objects.filter(is_active=True)
            if role == TEAM_MEMBER
            else ReviewMarker.objects.all()
        )
        tables.append(
            {
                "role": role.key,
                "title": role.table.capitalize(),
                "description": role.description,
                "form": bound[1] if bound and bound[0] == role else role.form(prefix=role.prefix),
                "users": users.order_by("username"),
            }
        )
    return tables
