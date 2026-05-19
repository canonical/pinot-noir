"""Management command to sync MergeBugPackageInfo from a YAML or plain-text file."""

import yaml
from django.core.management.base import BaseCommand, CommandError

from pinot_noir.data_manager.tasks import sync_merge_packages_from_yaml


class Command(BaseCommand):
    help = (
        "Sync the MergeBugPackageInfo table to match the package list in a YAML file or a "
        "plain-text file. "
        "Packages not in the file are removed; new packages are added with milestone_offset=0."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "package_file",
            help=(
                "Path to the package list file. "
                "Use a .yaml/.yml file for YAML subscriptions format, "
                "or any other extension for a plain-text file."
            ),
        )
        parser.add_argument(
            "--key",
            default="ubuntu-server",
            help=(
                "Top-level key in the YAML file whose value is the package set "
                "(default: ubuntu-server). Ignored for plain-text files."
            ),
        )

    def handle(self, *args, **options) -> None:
        file_path = options["package_file"]
        key = options["key"]

        if file_path.endswith((".yaml", ".yml")):
            packages = self._load_yaml(file_path, key)
        else:
            packages = self._load_text(file_path)

        added, removed = sync_merge_packages_from_yaml(packages)

        self.stdout.write(
            self.style.SUCCESS(
                f"Sync complete: {added} package(s) added, {removed} package(s) removed."
            )
        )

    def _load_yaml(self, yaml_path: str, key: str) -> set[str]:
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
            return {str(p) for p in raw}
        elif isinstance(raw, dict):
            return {str(k) for k in raw.keys()}
        else:
            raise CommandError(
                f"Expected a set or mapping under key {key!r}, got {type(raw).__name__}."
            )

    def _load_text(self, text_path: str) -> set[str]:
        try:
            with open(text_path) as f:
                lines = f.readlines()
        except OSError as exc:
            raise CommandError(f"Could not open {text_path!r}: {exc}") from exc

        packages = {line.strip() for line in lines if line.strip()}
        if not packages:
            raise CommandError(f"No package names found in {text_path!r}.")
        return packages
