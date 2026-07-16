"""Management command to enqueue the first run of the weekly task scheduler."""

from django.core.management.base import BaseCommand

from pinot_noir.data_manager.tasks import schedule_weekly_tasks


class Command(BaseCommand):
    help = "Enqueue the first run of the self-scheduling weekly task scheduler."

    def handle(self, *args, **options) -> None:
        schedule_weekly_tasks.enqueue()
        self.stdout.write(self.style.SUCCESS("Weekly task scheduler enqueued."))
