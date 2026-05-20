"""Management command to enqueue staggered per-bug merge refresh tasks."""

from django.core.management.base import BaseCommand

from pinot_noir.data_manager.tasks import (
    SINGLE_MERGE_REFRESH_INTERVAL_HOURS,
    enqueue_all_merge_refreshes,
)


class Command(BaseCommand):
    help = (
        "Cancel any queued single-merge refresh tasks and enqueue a fresh staggered set "
        "for every bug currently in the Merge table."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--username",
            required=True,
            help="Django username whose stored Launchpad token should be used.",
        )
        parser.add_argument(
            "--interval-hours",
            type=int,
            default=SINGLE_MERGE_REFRESH_INTERVAL_HOURS,
            help=(
                "Hours between per-bug refreshes "
                f"(default: {SINGLE_MERGE_REFRESH_INTERVAL_HOURS})."
            ),
        )

    def handle(self, *args, **options) -> None:
        interval_hours = options["interval_hours"]
        enqueue_all_merge_refreshes.enqueue(options["username"], interval_hours)
        self.stdout.write(
            self.style.SUCCESS(
                f"Staggered merge bug refreshes enqueued (interval: {interval_hours}h)."
            )
        )
