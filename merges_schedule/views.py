from django.shortcuts import render

from .models import Merge


def index(request):
	"""Render the merges schedule page using stored Merge objects."""
	merges = Merge.objects.all()
	context = {
		"title": "Merge Schedule",
		"merges": merges,
	}

	return render(request, "merges_schedule/index.html", context)
