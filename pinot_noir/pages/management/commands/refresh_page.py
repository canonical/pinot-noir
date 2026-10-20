"""Management command to enqueue a page's refresh task."""

from django.core.management.base import BaseCommand, CommandError

from pinot_noir.pages.registry import get_page, get_pages


class Command(BaseCommand):
    help = "Enqueue the refresh task for a page (see its AppConfig.page)."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "slug",
            choices=[p.slug for p in get_pages() if p.refresh_task],
            help="Page slug.",
        )
        parser.add_argument(
            "--username",
            required=True,
            help="Django username whose stored Launchpad token should be used.",
        )
        parser.add_argument(
            "--release",
            dest="release_adjective",
            default=None,
            help="Ubuntu release adjective, for pages whose task accepts one "
            "(e.g. merges-schedule). Defaults to the development release.",
        )
        parser.add_argument(
            "--team",
            default=None,
            help="startriage team name, for pages whose task accepts one (e.g. bug-triage). "
            "Defaults to the default or only configured team.",
        )
        parser.add_argument(
            "--ai",
            action="store_true",
            help="Run AI analysis, for pages whose task supports it (e.g. bug-triage, "
            "as 'startriage triage --ai'). Defaults to the page's own setting.",
        )
        parser.add_argument(
            "--triage-day",
            dest="triage_day",
            default=None,
            help="Triage day name as for 'startriage triage <day>', for pages whose task "
            "accepts one (e.g. bug-triage). Defaults to today.",
        )

    def handle(self, *args, **options) -> None:
        page = get_page(options["slug"])
        if page is None:
            raise CommandError(f"Unknown page {options['slug']!r}.")
        task = page.get_refresh_task()
        if task is None:
            raise CommandError(f"Page {options['slug']!r} has no refresh task.")
        kwargs = {"username": options["username"]}
        if options["release_adjective"]:
            kwargs["release_adjective"] = options["release_adjective"]
        for option in ("team", "triage_day"):
            if options[option]:
                kwargs[option] = options[option]
        if options["ai"]:
            kwargs["ai"] = True
        try:
            task.enqueue(**kwargs)
        except TypeError as exc:
            raise CommandError(f"{page.refresh_task} rejected the arguments: {exc}") from exc
        self.stdout.write(self.style.SUCCESS(f"Refresh enqueued for {page.label}."))
