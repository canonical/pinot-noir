from django.shortcuts import render

from launchpad.models import UbuntuRelease
from .models import Merge

# Custom status ordering used both for sorting and for constructing the statuses list
STATUS_ORDER = {
	Merge.STATUS_NEW: 0,
	Merge.STATUS_STARTED: 1,
	Merge.STATUS_PROJECTED: 2,
	Merge.STATUS_DONE: 3,
}

def sort_merges_default(merges):
	"""Sort merges by milestone, status, then assignee username."""
	return sorted(
		merges,
		key=lambda m: (
			m.milestone or "",
			STATUS_ORDER.get(m.status, -1),
			m.assignee_user.username if m.assignee_user else "",
		),
	)


def index(request):
	"""Render the merges schedule page using stored Merge objects."""
	merges = Merge.objects.select_related("assignee_user").all()
	sorted_merges = sort_merges_default(merges)

	# Lists for search and filter
	milestones = sorted({m.milestone for m in merges if m.milestone})
	assignees = sorted({(m.assignee_user.username if m.assignee_user else "UNASSIGNED") for m in merges})
	statuses = [s for s, _ in sorted(Merge.STATUS_CHOICES, key=lambda item: STATUS_ORDER.get(item[0], -1))]

    # Ubuntu releases for selection in backport bug creation
	ubuntu_releases = UbuntuRelease.objects.all().order_by("-version")

	context = {
		"title": "Merge Schedule",
		"merges": sorted_merges,
		"milestones": milestones,
		"assignees": assignees,
		"statuses": statuses,
		"ubuntu_releases": ubuntu_releases,
	}

	return render(request, "merges_schedule/index.html", context)
