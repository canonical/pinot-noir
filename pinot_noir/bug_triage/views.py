from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods

from pinot_noir.pages.models import PageMetadata

from .apps import PAGE_SLUG
from .models import TriageReport

REPORT_CSP = (
    "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
    "img-src data:; connect-src 'none'; base-uri 'none'; form-action 'none'; "
    "frame-ancestors 'self'"
)


def index(request: HttpRequest) -> HttpResponse:
    report = TriageReport.objects.first()
    if report is not None and not report.html:
        # Reports from before startriage generated the HTML need one refresh.
        report = None
    return render(
        request,
        "bug_triage/index.html",
        {
            "title": "Bug Triage",
            "report": report,
            "page_meta": PageMetadata.objects.filter(slug=PAGE_SLUG).first(),
        },
    )


def _report_response(report: TriageReport | None) -> HttpResponse:
    if report is None or not report.html:
        raise Http404("No Bug Triage HTML report has been generated.")
    response = HttpResponse(report.html, content_type="text/html; charset=utf-8")
    response["Content-Security-Policy"] = REPORT_CSP
    response["X-Content-Type-Options"] = "nosniff"
    return response


@require_http_methods(["GET"])
def report(request: HttpRequest) -> HttpResponse:
    """Serve startriage's self-contained report, including its interactive JavaScript."""
    return _report_response(TriageReport.objects.first())


@require_http_methods(["GET"])
def download(request: HttpRequest) -> HttpResponse:
    report = TriageReport.objects.first()
    response = _report_response(report)
    assert report is not None  # _report_response raises when there is no HTML report.
    response["Content-Disposition"] = f'attachment; filename="{report.html_filename}"'
    return response
