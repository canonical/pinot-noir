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
    STATUS_UPLOADED = "uploaded"
    STATUS_DONE = "done"

    STATUS_CHOICES = [
        (STATUS_NEW, "new"),
        (STATUS_PROJECTED, "projected"),
        (STATUS_STARTED, "started"),
        (STATUS_UPLOADED, "uploaded"),
        (STATUS_DONE, "done"),
    ]

    # Launchpad bug number - primary key
    lp_bug = models.PositiveIntegerField(primary_key=True)

    # Name of package or package group to update
    package = models.CharField(max_length=200)

    # Type of merge - merge, sync, backport, etc.
    merge_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default=TYPE_MERGE)

    # Launchpad username of assignee
    assignee = models.CharField(max_length=100, blank=True)

    # Optional foreign key to a Launchpad user; will be populated from `assignee` via migration
    assignee_user = models.ForeignKey(
        "launchpad.LPUser",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="merges",
    )

    # Ubuntu release milestone the merge should be completed for
    milestone = models.CharField(max_length=100, blank=True)

    # Current status of the merge
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_NEW)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.package} ({self.merge_type}) - {self.status}"
