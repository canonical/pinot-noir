from django.http import HttpRequest, HttpResponse
from launchpad.bug_submission import BugSubmission

LAUNCHPAD_UBUNTU_BUG_URL_TEMPLATE = "https://launchpad.net/ubuntu/+source/#package/+filebug"

def new_bug(request: HttpRequest, bug_type: str) -> HttpResponse:
    """Redirect to Launchpad's Ubuntu package bug filing page with filled out info from body."""

    bug_submission = BugSubmission(request.POST, bug_type)

    launchpad_url_base = LAUNCHPAD_UBUNTU_BUG_URL_TEMPLATE.replace("#package", bug_submission.get_package_name())
    launchpad_url = f"{launchpad_url_base}?{bug_submission.get_full_launchpad_query()}"

    return HttpResponse(launchpad_url, content_type="text/plain")
