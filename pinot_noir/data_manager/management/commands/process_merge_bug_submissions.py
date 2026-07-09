"""Prepare and submit merge and/or backport bug submissions."""

from collections.abc import Callable

from django.core.management.base import BaseCommand

from pinot_noir.data_manager.tasks import (
    prepare_backport_bug_submissions,
    prepare_merge_bug_submissions,
    submit_prepared_backport_bug_submissions,
    submit_prepared_merge_bug_submissions,
)


class Command(BaseCommand):
    help = (
        "Prepare merge and backport bug submissions using a user's Launchpad token. "
        "Both types are processed by default; use --merges or --backports to restrict to one. "
        "Prepared submissions can be submitted to Launchpad with --submit."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--username",
            required=True,
            help="Django username whose stored Launchpad token should be used.",
        )
        parser.add_argument(
            "--release",
            help="Ubuntu release adjective to target (defaults to current devel release).",
        )

        type_group = parser.add_mutually_exclusive_group()
        type_group.add_argument(
            "--merges",
            action="store_true",
            help="Process merge bug submissions only.",
        )
        type_group.add_argument(
            "--backports",
            action="store_true",
            help="Process backport bug submissions only.",
        )

        parser.add_argument(
            "--submit",
            action="store_true",
            help="Submit all prepared submissions to Launchpad.",
        )

    def _process_type(
        self,
        label: str,
        prepare_fn: Callable,
        submit_fn: Callable,
        username: str,
        release_adjective: str | None,
        submit: bool,
    ) -> None:
        self.stdout.write(f"\n-- {label} --")

        submissions = prepare_fn(username=username, release_adjective=release_adjective)
        self.stdout.write(f"Prepared {len(submissions)} submission(s).")

        if submit:
            submitted, failed = submit_fn(username, submissions)
            self.stdout.write(
                self.style.SUCCESS(f"Submitted {submitted} bug(s); {failed} submission(s) failed.")
            )

    def handle(self, *args, **options) -> None:
        run_merges = options["merges"]
        run_backports = options["backports"]
        run_both = not run_merges and not run_backports

        username = options["username"]
        release_adjective = options.get("release")
        submit = options["submit"]

        if run_merges or run_both:
            self._process_type(
                label="Merge bugs",
                prepare_fn=prepare_merge_bug_submissions,
                submit_fn=submit_prepared_merge_bug_submissions,
                username=username,
                release_adjective=release_adjective,
                submit=submit,
            )

        if run_backports or run_both:
            self._process_type(
                label="Backport bugs",
                prepare_fn=prepare_backport_bug_submissions,
                submit_fn=submit_prepared_backport_bug_submissions,
                username=username,
                release_adjective=release_adjective,
                submit=submit,
            )

        if not submit:
            self.stdout.write("No submission action requested. Use --submit to file bugs.")
