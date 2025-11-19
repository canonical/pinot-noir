from django.shortcuts import render


def index(request):
	"""Render the merges schedule page."""
	# Simple placeholder context — extend later as needed
	context = {
		"title": "Merge Schedule",
		"description": "A schedule of upcoming merges."
	}
	return render(request, "merges_schedule/index.html", context)
