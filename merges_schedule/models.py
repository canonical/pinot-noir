from django.db import models


class Merge(models.Model):
	TYPE_MERGE = "merge"
	TYPE_SYNC = "sync"
	TYPE_BACKPORT = "backport"

	TYPE_CHOICES = [
		(TYPE_MERGE, "merge"),
		(TYPE_SYNC, "sync"),
		(TYPE_BACKPORT, "backport"),
	]

	STATUS_NEW = "new"
	STATUS_PROJECTED = "projected"
	STATUS_STARTED = "started"
	STATUS_DONE = "done"

	STATUS_CHOICES = [
		(STATUS_NEW, "new"),
		(STATUS_PROJECTED, "projected"),
		(STATUS_STARTED, "started"),
		(STATUS_DONE, "done"),
	]

	package = models.CharField(max_length=200)
	type = models.CharField(max_length=20, choices=TYPE_CHOICES, default=TYPE_MERGE)
	assignee = models.CharField(max_length=100, blank=True)
	milestone = models.CharField(max_length=100, blank=True)
	status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_NEW)

	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ["-created_at"]

	def __str__(self) -> str:
		return f"{self.package} ({self.type}) - {self.status}"
