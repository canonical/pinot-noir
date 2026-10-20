from itertools import groupby

from django.shortcuts import render

from pinot_noir.pages.models import PageMetadata

from .apps import PAGE_SLUG
from .models import TriageItem, TriageReport
from .sync import context_label


def build_sections(items) -> list[dict]:
    """Group ordered TriageItems into the html report's sections."""
    sections = []
    for name, group in groupby(items, key=lambda i: (i.section_order, i.section)):
        rows = list(group)
        sections.append(
            {
                "name": name[1],
                "items": rows,
                "context_label": context_label([r.source for r in rows]),
            }
        )
    return sections


def index(request):
    """Render the bug triage page using the stored startriage results."""
    report = TriageReport.objects.first()
    items = TriageItem.objects.order_by("section_order", "position")

    context = {
        "title": report.title if report else "Bug Triage",
        "report": report,
        "sections": build_sections(items),
        "page_meta": PageMetadata.objects.filter(slug=PAGE_SLUG).first(),
    }

    return render(request, "bug_triage/index.html", context)
