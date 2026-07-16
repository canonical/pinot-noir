"""Management command to enqueue a merge schedule refresh task."""

from django.core.management.base import BaseCommand

from pinot_noir.data_manager.tasks import refresh_merge_schedule


class Command(BaseCommand):
    help = (
        "Enqueue a merge schedule refresh for the given Ubuntu release. "
        "Once synced, staggered per-bug refreshes are enqueued automatically."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "release_adjective",
            type=str,
            nargs="?",
            default=None,
            help=(
                "Adjective of the Ubuntu release to sync (e.g. 'resolute'). "
                "Defaults to the current development release."
            ),
        )
        parser.add_argument(
            "--username",
            required=True,
            help="Django username whose stored Launchpad token should be used.",
        )

    def handle(self, *args, **options) -> None:
        release_adjective = options["release_adjective"]
        refresh_merge_schedule.enqueue(options["username"], release_adjective)
        target = release_adjective or "the development release"
        self.stdout.write(
            self.style.SUCCESS(f"Merge schedule sync enqueued for {target}.")
        )
