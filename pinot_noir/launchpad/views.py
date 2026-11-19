import logging
from typing import cast

from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.exceptions import ObjectDoesNotExist
from django.http import HttpRequest, HttpResponse
from django.views.decorators.http import require_http_methods

from pinot_noir.data_manager.common import (
    get_launchpad_service_for_user,
    user_has_launchpad_token,
)

from .bug_submission import BugSubmission

logger = logging.getLogger(__name__)


@login_required
@require_http_methods(["POST"])
def new_bug(request: HttpRequest, bug_type: str) -> HttpResponse:
    """Submit a merge or backport bug with the signed-in user's Launchpad token."""
    user = cast(User, request.user)
    bug_submission = BugSubmission(request.POST, bug_type)
    validation_error = ""
    validation_status = 400
    if bug_type not in {"merge", "backport"}:
        validation_error = "Unknown bug type."
    elif not user_has_launchpad_token(user):
        validation_error = "Add a Launchpad token in Settings before creating bugs."
        validation_status = 403
    elif not bug_submission.get_package_name():
        validation_error = "Package name is required."
    if validation_error:
        return HttpResponse(validation_error, content_type="text/plain", status=validation_status)

    try:
        service = get_launchpad_service_for_user(user.username)
        submission = bug_submission.prepare(service)
        if submission is None:
            return HttpResponse(
                f"No {bug_type} bug submission is currently needed for "
                f"{bug_submission.get_package_name()}.",
                content_type="text/plain",
                status=409,
            )

        bug = service.submit_bug(submission=submission, provider_name="launchpad")
        if bug is None:
            return HttpResponse(
                "Launchpad did not create the bug.", content_type="text/plain", status=502
            )
    except (ObjectDoesNotExist, ValueError) as exc:
        return HttpResponse(str(exc), content_type="text/plain", status=400)
    except Exception:
        logger.exception("Failed to create %s bug for %s", bug_type, user.username)
        return HttpResponse(
            "Failed to create the Launchpad bug.", content_type="text/plain", status=502
        )

    bug_submission.mark_filed()
    return HttpResponse(f"https://bugs.launchpad.net/bugs/{bug.id}", content_type="text/plain")
