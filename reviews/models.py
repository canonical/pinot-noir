from django.db import models


class Review(models.Model):
    STATUS_NEEDS_REVIEW = "Needs Review"
    STATUS_WORK_IN_PROGRESS = "Work in Progress"
    STATUS_UNDER_REVIEW = "Under Review"
    STATUS_APPROVED = "Approved"
    STATUS_NEEDS_FIXING = "Needs Fixing"
    STATUS_NEEDS_INFORMATION = "Needs Information"

    STATUS_CHOICES = [
        (STATUS_NEEDS_REVIEW, STATUS_NEEDS_REVIEW),
        (STATUS_WORK_IN_PROGRESS, STATUS_WORK_IN_PROGRESS),
        (STATUS_UNDER_REVIEW, STATUS_UNDER_REVIEW),
        (STATUS_APPROVED, STATUS_APPROVED),
        (STATUS_NEEDS_FIXING, STATUS_NEEDS_FIXING),
        (STATUS_NEEDS_INFORMATION, STATUS_NEEDS_INFORMATION),
    ]

    package = models.CharField(max_length=200)
    release_version = models.CharField(max_length=50, blank=True)
    mp_url = models.URLField(max_length=500)

    reviewer = models.CharField(max_length=100, blank=True)
    reviewer_user = models.ForeignKey(
        "launchpad.LPUser",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_reviews",
    )

    submitter = models.CharField(max_length=100, blank=True)
    submitter_user = models.ForeignKey(
        "launchpad.LPUser",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="submitted_reviews",
    )

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_NEEDS_REVIEW)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        if self.release_version:
            return f"{self.package} ({self.release_version}) - {self.status}"
        return f"{self.package} - {self.status}"
