"""Management command to enqueue task result pruning task."""

from django.core.management.base import BaseCommand

from pinot_noir.data_manager.tasks import prune_task_results


class Command(BaseCommand):
    help = "Enqueue the task result pruning task."

    def handle(self, *args, **options) -> None:
        prune_task_results.enqueue()
        self.stdout.write(self.style.SUCCESS("Task result pruning task enqueued."))
