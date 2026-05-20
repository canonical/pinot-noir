"""Management command to enqueue the initial review-sync task."""

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError

from pinot_noir.data_manager.tasks import refresh_reviews


class Command(BaseCommand):
    help = "Enqueue the first run of the periodic review sync task."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--username",
            required=True,
            help="Django username whose stored Launchpad token should be used.",
        )

    def handle(self, *args, **options) -> None:
        try:
            user = User.objects.get(username=options["username"])
        except User.DoesNotExist as exc:
            raise CommandError(f"User {options['username']!r} does not exist.") from exc

        refresh_reviews.enqueue(user)
        self.stdout.write(self.style.SUCCESS("Review sync task enqueued."))
