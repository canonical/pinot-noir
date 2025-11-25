from django.shortcuts import render

from .models import Merge

def sort_merges_default(merges):
	"""Sort merges by milestone, status, then assignee username."""
	STATUS_ORDER = {
		Merge.STATUS_NEW: 0,
		Merge.STATUS_STARTED: 1,
		Merge.STATUS_PROJECTED: 2,
		Merge.STATUS_DONE: 3,
	}

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
	context = {
		"title": "Merge Schedule",
		"merges": sorted_merges,
	}

	return render(request, "merges_schedule/index.html", context)
