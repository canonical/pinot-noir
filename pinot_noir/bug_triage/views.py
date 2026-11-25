from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods

from pinot_noir.pages.models import PageMetadata

from .apps import PAGE_SLUG
from .models import TriageReport, TriageSettings

REPORT_CSP = (
    "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
    "img-src data:; connect-src 'none'; base-uri 'none'; form-action 'none'; "
    "frame-ancestors 'self'"
)


def _selected_report(request: HttpRequest, reports=None) -> TriageReport | None:
    """Return the requested report if it is in the current retention window."""
    if reports is None:
        reports = TriageSettings.current().report_history()
    selected = request.GET.get("report")
    if selected is None:
        return reports.first()
    try:
        pk = int(selected)
    except ValueError as exc:
        raise Http404("Invalid Bug Triage report.") from exc
    report = next((candidate for candidate in reports if candidate.pk == pk), None)
    if report is None:
        raise Http404("No such Bug Triage report in the current history.")
    return report


def index(request: HttpRequest) -> HttpResponse:
    reports = TriageSettings.current().report_history()
    report = _selected_report(request, reports)
    report_query = f"?report={report.pk}" if report is not None and "report" in request.GET else ""
    return render(
        request,
        "bug_triage/index.html",
        {
            "title": "Bug Triage",
            "report": report,
            "reports": reports,
            "report_query": report_query,
            "page_meta": PageMetadata.objects.filter(slug=PAGE_SLUG).first(),
        },
    )


def _report_response(report: TriageReport | None) -> HttpResponse:
    if report is None:
        raise Http404("No Bug Triage HTML report has been generated.")
    response = HttpResponse(report.html, content_type="text/html; charset=utf-8")
    response["Content-Security-Policy"] = REPORT_CSP
    response["X-Content-Type-Options"] = "nosniff"
    return response


@require_http_methods(["GET"])
def report(request: HttpRequest) -> HttpResponse:
    """Serve startriage's self-contained report, including its interactive JavaScript."""
    return _report_response(_selected_report(request))


@require_http_methods(["GET"])
def download(request: HttpRequest) -> HttpResponse:
    report = _selected_report(request)
    response = _report_response(report)
    assert report is not None  # _report_response raises when there is no HTML report.
    response["Content-Disposition"] = f'attachment; filename="{report.html_filename}"'
    return response
