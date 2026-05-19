"""Prepare, export/import, and submit merge bug submissions."""

import json

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError

from pinot_noir.data_manager.tasks import (
    bug_submission_from_json_dict,
    bug_submission_to_json_dict,
    prepare_merge_bug_submissions_for_user,
    submit_prepared_merge_bug_submissions_for_user,
)


class Command(BaseCommand):
    help = (
        "Prepare merge bug submissions for all MergeBugPackageInfo entries using a user's "
        "Launchpad token. Submissions can be submitted immediately or exported/imported as JSON."
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
        parser.add_argument(
            "--output-json",
            help="Path to write prepared submissions as JSON.",
        )
        parser.add_argument(
            "--input-json",
            help="Path to read prepared submissions JSON from disk.",
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

    def handle(self, *args, **options) -> None:
        if options["input_json"] and options["output_json"]:
            raise CommandError("Use either --input-json or --output-json, not both.")

        try:
            user = User.objects.get(username=options["username"])
        except User.DoesNotExist as exc:
            raise CommandError(f"User {options['username']!r} does not exist.") from exc

        if options["input_json"]:
            submissions = self._load_submissions(options["input_json"])
            self.stdout.write(f"Loaded {len(submissions)} prepared submission(s) from JSON.")
        else:
            submissions = prepare_merge_bug_submissions_for_user(
                user=user,
                release_adjective=options.get("release"),
            )
            self.stdout.write(f"Prepared {len(submissions)} submission(s).")

        if options["output_json"]:
            self._save_submissions(options["output_json"], submissions)
            self.stdout.write(
                self.style.SUCCESS(f"Saved prepared submissions to {options['output_json']}")
            )

        if options["submit"]:
            submitted, failed = submit_prepared_merge_bug_submissions_for_user(user, submissions)
            self.stdout.write(
                self.style.SUCCESS(f"Submitted {submitted} bug(s); {failed} submission(s) failed.")
            )
        elif not options["output_json"]:
            self.stdout.write("No submission action requested. Use --submit and/or --output-json.")
