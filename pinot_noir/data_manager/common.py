"""Shared helpers used by the feature apps' sync tasks."""

from django.contrib.auth.models import User
from django.core.exceptions import ObjectDoesNotExist
from ubq import QueryService
from ubq.models import ProviderCredentials

from pinot_noir.data_manager.models import UserTokens
from pinot_noir.launchpad.models import UbuntuRelease


def get_devel_or_requested_release(release_adjective: str | None = None) -> UbuntuRelease:
    """Return the UbuntuRelease for the given adjective, or the current devel release."""
    if release_adjective:
        try:
            return UbuntuRelease.objects.get(adjective=release_adjective)
        except UbuntuRelease.DoesNotExist:
            raise ObjectDoesNotExist(
                f"No Ubuntu release found with adjective '{release_adjective}'."
            )

    release = UbuntuRelease.objects.filter(status=UbuntuRelease.STATUS_DEVEL).first()
    if release is None:
        raise ObjectDoesNotExist("No Ubuntu development release found.")
    return release


def get_launchpad_service_for_user(username: str) -> QueryService:
    """Return a QueryService logged in to Launchpad with *username*'s stored token."""
    user = User.objects.get(username=username)
    tokens = UserTokens.objects.filter(user=user).first()
    if tokens is None or not tokens.lp_token:
        raise ObjectDoesNotExist(f"No Launchpad token configured for user '{username}'.")

    service = QueryService()
    service.login(
        provider_name="launchpad",
        credentials=ProviderCredentials(token=tokens.lp_token),
    )
    return service


def milestones_for_release(version: str) -> set[str]:
    """Return the set of valid LP milestone names for a Ubuntu release cycle.

    Given a version like ``'26.04'``, returns the six monthly milestones
    spanning the cycle: ``{'25.11', '25.12', '26.01', '26.02', '26.03', '26.04'}``.
    """
    year_str, month_str = version.split(".")
    year = int(year_str)
    month = int(month_str)

    milestones: set[str] = set()
    for i in range(6):
        m = month - i
        y = year
        while m <= 0:
            m += 12
            y -= 1
        milestones.add(f"{y:02d}.{m:02d}")
    return milestones
