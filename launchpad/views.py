from urllib.parse import quote

from django.http import HttpRequest, HttpResponseRedirect

def get_ubuntu_devel_release_name() -> str:
    """Return the name of the current Ubuntu devel release, or an empty string if not found."""
    from launchpad.models import UbuntuRelease

    devel_release = UbuntuRelease.objects.filter(status=UbuntuRelease.STATUS_DEVEL).first()
    return devel_release.adjective if devel_release else "next"

def file_bug_redirect(request: HttpRequest, package_name: str, query_params: str = "") -> HttpResponseRedirect:
	"""Redirect to Launchpad's source-package bug filing page."""
	encoded_package = quote(package_name, safe="")
	launchpad_url = f"https://launchpad.net/ubuntu/+source/{encoded_package}/+filebug"

	if query_params:
		launchpad_url += f"?{query_params}"

	return HttpResponseRedirect(launchpad_url)


def file_merge_bug_redirect(request: HttpRequest, package_name: str) -> HttpResponseRedirect:
    """Redirect to Launchpad's source-package bug filing page with merge template."""
    query_params = f"field.title=Merge%20{package_name}%20for%20{get_ubuntu_devel_release_name()}%20cycle"

    return file_bug_redirect(request, package_name, query_params)


def file_backport_bug_redirect(request: HttpRequest, package_name: str) -> HttpResponseRedirect:
    """Redirect to Launchpad's source-package bug filing page with backport template."""
    query_params = f"field.title=Backport%20{package_name}%20for%20{get_ubuntu_devel_release_name()}%20cycle"

    return file_bug_redirect(request, package_name, query_params)
