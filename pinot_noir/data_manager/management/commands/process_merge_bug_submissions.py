"""Prepare, export/import, and submit merge and/or backport bug submissions."""

import json
from collections.abc import Callable

from django.core.management.base import BaseCommand, CommandError

from pinot_noir.data_manager.tasks import (
    bug_submission_from_json_dict,
    bug_submission_to_json_dict,
    prepare_backport_bug_submissions,
    prepare_merge_bug_submissions,
    submit_prepared_backport_bug_submissions,
    submit_prepared_merge_bug_submissions,
)


class Command(BaseCommand):
    help = (
        "Prepare merge and backport bug submissions using a user's Launchpad token. "
        "Both types are processed by default; use --merges or --backports to restrict to one. "
        "Submissions can be submitted immediately or exported/imported as JSON."
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
            "--output-json",
            help=(
                "Path to write prepared submissions as JSON "
                "(requires --merges or --backports)."
            ),
        )
        parser.add_argument(
            "--input-json",
            help=(
                "Path to read prepared submissions JSON from disk "
                "(requires --merges or --backports)."
            ),
        )
        parser.add_argument(
            "--submit",
            action="store_true",
            help="Submit all prepared/imported submissions to Launchpad.",
        )

    def _load_submissions(self, input_json: str) -> list[tuple[str, object]]:
        try:
            with open(input_json, encoding="utf-8") as f:
                raw = json.load(f)
        except OSError as exc:
            raise CommandError(f"Could not open {input_json!r}: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise CommandError(f"Invalid JSON in {input_json!r}: {exc}") from exc

        if not isinstance(raw, list):
            raise CommandError("Input JSON must contain a list of prepared submissions.")

        loaded: list[tuple[str, object]] = []
        for i, row in enumerate(raw):
            if not isinstance(row, dict) or "package" not in row or "submission" not in row:
                raise CommandError(f"Invalid entry at index {i} in {input_json!r}.")
            if not isinstance(row["package"], str):
                raise CommandError(f"Invalid package value at index {i} in {input_json!r}.")
            if not isinstance(row["submission"], dict):
                raise CommandError(f"Invalid submission value at index {i} in {input_json!r}.")
            loaded.append((row["package"], bug_submission_from_json_dict(row["submission"])))

        return loaded

    def _save_submissions(self, output_json: str, submissions: list[tuple[str, object]]) -> None:
        payload = [
            {
                "package": package,
                "submission": bug_submission_to_json_dict(submission),
            }
            for package, submission in submissions
        ]

        try:
            with open(output_json, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, sort_keys=True)
                f.write("\n")
        except OSError as exc:
            raise CommandError(f"Could not write {output_json!r}: {exc}") from exc

    def _process_type(
        self,
        label: str,
        prepare_fn: Callable,
        submit_fn: Callable,
        username: str,
        release_adjective: str | None,
        input_json: str | None,
        output_json: str | None,
        submit: bool,
    ) -> None:
        self.stdout.write(f"\n-- {label} --")

        if input_json:
            submissions = self._load_submissions(input_json)
            self.stdout.write(f"Loaded {len(submissions)} prepared submission(s) from JSON.")
        else:
            submissions = prepare_fn(username=username, release_adjective=release_adjective)
            self.stdout.write(f"Prepared {len(submissions)} submission(s).")

        if output_json:
            self._save_submissions(output_json, submissions)
            self.stdout.write(self.style.SUCCESS(f"Saved prepared submissions to {output_json}"))

        if submit:
            submitted, failed = submit_fn(username, submissions)
            self.stdout.write(
                self.style.SUCCESS(f"Submitted {submitted} bug(s); {failed} submission(s) failed.")
            )

    def handle(self, *args, **options) -> None:
        if options["input_json"] and options["output_json"]:
            raise CommandError("Use either --input-json or --output-json, not both.")

        run_merges = options["merges"]
        run_backports = options["backports"]
        run_both = not run_merges and not run_backports

        if (options["input_json"] or options["output_json"]) and run_both:
            raise CommandError(
                "--input-json and --output-json require --merges or --backports to be specified."
            )

        username = options["username"]
        release_adjective = options.get("release")
        input_json = options["input_json"]
        output_json = options["output_json"]
        submit = options["submit"]

        if run_merges or run_both:
            self._process_type(
                label="Merge bugs",
                prepare_fn=prepare_merge_bug_submissions,
                submit_fn=submit_prepared_merge_bug_submissions,
                username=username,
                release_adjective=release_adjective,
                input_json=input_json if run_merges else None,
                output_json=output_json if run_merges else None,
                submit=submit,
            )

        if run_backports or run_both:
            self._process_type(
                label="Backport bugs",
                prepare_fn=prepare_backport_bug_submissions,
                submit_fn=submit_prepared_backport_bug_submissions,
                username=username,
                release_adjective=release_adjective,
                input_json=input_json if run_backports else None,
                output_json=output_json if run_backports else None,
                submit=submit,
            )

        if not submit and not output_json:
            self.stdout.write("No submission action requested. Use --submit and/or --output-json.")
