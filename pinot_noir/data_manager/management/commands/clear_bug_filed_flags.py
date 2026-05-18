"""Management command to reset all bug_filed_this_cycle flags to False."""

from django.core.management.base import BaseCommand

from pinot_noir.data_manager.models import BackportBugPackageInfo, MergeBugPackageInfo


class Command(BaseCommand):
    help = "Reset bug_filed_this_cycle to False for all merge and backport package entries."

    def handle(self, *args, **options) -> None:
        merge_count = MergeBugPackageInfo.objects.filter(bug_filed_this_cycle=True).update(
            bug_filed_this_cycle=False
        )
        backport_count = BackportBugPackageInfo.objects.filter(bug_filed_this_cycle=True).update(
            bug_filed_this_cycle=False
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Cleared {merge_count} merge and {backport_count} backport flag(s)."
            )
        )
