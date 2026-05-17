"""Management command to sync MergeBugPackageInfo from a YAML subscriptions file."""

import yaml
from django.core.management.base import BaseCommand, CommandError

from pinot_noir.data_manager.tasks import sync_merge_packages_from_yaml


class Command(BaseCommand):
    help = (
        "Sync the MergeBugPackageInfo table to match the package list in a YAML file. "
        "Packages not in the file are removed; new packages are added with milestone_offset=0."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "yaml_file",
            help="Path to the YAML subscriptions file.",
        )
        parser.add_argument(
            "--key",
            default="ubuntu-server",
            help=(
                "Top-level key in the YAML file whose value is the package set "
                "(default: ubuntu-server)."
            ),
        )

    def handle(self, *args, **options) -> None:
        yaml_path = options["yaml_file"]
        key = options["key"]

        try:
            with open(yaml_path) as f:
                data = yaml.safe_load(f)
        except OSError as exc:
            raise CommandError(f"Could not open {yaml_path!r}: {exc}") from exc
        except yaml.YAMLError as exc:
            raise CommandError(f"Failed to parse {yaml_path!r}: {exc}") from exc

        if not isinstance(data, dict) or key not in data:
            raise CommandError(f"Key {key!r} not found in {yaml_path!r}.")

        raw = data[key]
        if isinstance(raw, set):
            packages: set[str] = {str(p) for p in raw}
        elif isinstance(raw, dict):
            packages = {str(k) for k in raw.keys()}
        else:
            raise CommandError(
                f"Expected a set or mapping under key {key!r}, got {type(raw).__name__}."
            )

        added, removed = sync_merge_packages_from_yaml(packages)

        self.stdout.write(
            self.style.SUCCESS(
                f"Sync complete: {added} package(s) added, {removed} package(s) removed."
            )
        )
