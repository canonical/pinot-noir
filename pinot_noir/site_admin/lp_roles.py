"""Tables of Launchpad users holding a role flag on LPUser (team member, review marker).

Shared by My team and the Reviews page's admin section: each view lists the roles
it shows, sends role POSTs to :func:`handle_role_post`, and renders
:func:`role_tables` with ``site_admin/_lp_role_table.html``.
"""

from dataclasses import dataclass

from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect

from pinot_noir.launchpad.models import LPUser

from .forms import LPUserRoleForm, ReviewMarkerForm


@dataclass(frozen=True)
class Role:
    field: str  # boolean field on LPUser
    prefix: str  # form prefix
    table: str  # what the table is called in messages, lowercase
    form: type[LPUserRoleForm]
    description: str


TEAM_MEMBER = Role(
    "is_team_member", "team", "team members", LPUserRoleForm, "Launchpad users on the team."
)
REVIEW_MARKER = Role(
    "is_review_marker",
    "marker",
    "review markers",
    ReviewMarkerForm,
    "Launchpad usernames for users or teams that, when assigned to a Launchpad merge "
    "proposal, mark it to be added on the Reviews page.",
)


def handle_role_post(
    request: HttpRequest, roles: list[Role]
) -> HttpResponse | tuple[Role, LPUserRoleForm] | None:
    """Handle an add or remove POST for one of ``roles``.

    Returns a redirect when handled, ``(role, bound form)`` when adding failed
    validation, or None when the POST isn't for one of these roles.
    """
    role = next((r for r in roles if r.field == request.POST.get("role")), None)
    if role is None:
        return None
    if request.POST.get("action") == "remove":
        username = request.POST.get("username", "")
        if LPUser.objects.filter(username=username).update(**{role.field: False}):
            messages.success(request, f"Removed {username} from {role.table}.")
        return redirect(request.path)
    form = role.form(request.POST, prefix=role.prefix)
    if not form.is_valid():
        return role, form
    user, already = form.save(role.field)
    if already:
        messages.info(request, f"{user.username} is already in {role.table}.")
    else:
        messages.success(request, f"Added {user.username} to {role.table}.")
    return redirect(request.path)


def role_tables(roles: list[Role], bound: tuple[Role, LPUserRoleForm] | None = None) -> list:
    """Context for ``_lp_role_table.html``, one entry per role."""
    return [
        {
            "role": role.field,
            "title": role.table.capitalize(),
            "description": role.description,
            "form": bound[1] if bound and bound[0] == role else role.form(prefix=role.prefix),
            "users": LPUser.objects.filter(**{role.field: True}).order_by("username"),
        }
        for role in roles
    ]
