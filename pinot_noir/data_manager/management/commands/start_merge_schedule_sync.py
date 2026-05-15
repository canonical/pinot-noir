"""Management command to enqueue a merge schedule refresh task."""

from django.core.management.base import BaseCommand

from pinot_noir.data_manager.tasks import refresh_merge_schedule


class Command(BaseCommand):
    help = "Enqueue a merge schedule refresh for the given Ubuntu release."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "release_adjective",
            type=str,
            help="Adjective of the Ubuntu release to sync (e.g. 'resolute').",
        )

    def handle(self, *args, **options) -> None:
        release_adjective = options["release_adjective"]
        refresh_merge_schedule.enqueue(release_adjective)
        self.stdout.write(
            self.style.SUCCESS(f"Merge schedule sync enqueued for release '{release_adjective}'.")
        )
