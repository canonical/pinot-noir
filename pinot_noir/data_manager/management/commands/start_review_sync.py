"""Management command to enqueue the initial review-sync task."""

from django.core.management.base import BaseCommand

from pinot_noir.data_manager.tasks import refresh_reviews


class Command(BaseCommand):
    help = "Enqueue the first run of the periodic review sync task."

    def handle(self, *args, **options) -> None:
        refresh_reviews.enqueue()
        self.stdout.write(self.style.SUCCESS("Review sync task enqueued."))
