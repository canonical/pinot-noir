"""Background task that keeps the bug triage page in sync via startriage."""

import asyncio
import logging
import threading
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date
from unittest import mock

import aiohttp
import startriage.report as startriage_report
import startriage.sources.launchpad.triage as startriage_launchpad
from django.contrib.auth.models import User
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.utils import timezone
from django_tasks import task
from django_tasks_db.models import DBTaskResult
from launchpadlib.credentials import Credentials
from launchpadlib.launchpad import Launchpad
from startriage.ai import (
    BugOutcome,
    Pipeline,
    Provider,
    build_provider,
    payloads_from_tasks,
    render_report,
    triage_bugs,
)
from startriage.ai.checks import URLChecker
from startriage.ai.render import AI_APPEND_NOTICE
from startriage.ai.run import scratch_dir, team_members
from startriage.ai.tools import ReadOnlyHTTP, ToolContext, build_tools, debian, enabled_tool_names
from startriage.config import StarTriageConfig
from startriage.output import ReportItem
from startriage.source import FetchMode, TaskFilterOptions
from startriage.sources.launchpad.models import Task
from startriage.sources.launchpad.triage import LaunchpadTriage
from startriage.triage import build_filter, fetch

from pinot_noir.bug_triage.apps import PAGE_SLUG
from pinot_noir.bug_triage.models import (
    StartriageAISettings,
    StartriageTeam,
    TriageItem,
    TriageReport,
)
from pinot_noir.bug_triage.sync import (
    BugDetails,
    TriageItemData,
    bug_details,
    build_config,
    markdown_filename,
    report_heading,
    triage_items,
)
from pinot_noir.data_manager.models import UserTokens
from pinot_noir.pages.models import PageMetadata

logger = logging.getLogger(__name__)

# startriage connects to Launchpad through a module-level function; it is
# swapped for the duration of a fetch, so only one fetch may run at a time.
_launchpad_patch_lock = threading.Lock()


@contextmanager
def _launchpad_credentials(lp_token: str):
    """Make startriage log into Launchpad with *lp_token* instead of its own credential file.

    startriage only reads ``lp_credentials_file`` for its own OAuth consumer and
    discards credentials of any other consumer, so the stored Pinot Noir token
    is handed over as a ready Launchpad object instead.
    """

    def connect_launchpad(*_args, **_kwargs) -> Launchpad:
        return Launchpad(
            Credentials.from_string(lp_token),
            None,
            None,
            service_root="production",
            version="devel",
        )

    with (
        _launchpad_patch_lock,
        mock.patch.object(startriage_launchpad, "connect_launchpad", connect_launchpad),
    ):
        yield


def _launchpad_tasks(result: LaunchpadTriage) -> list[Task]:
    """Return every Launchpad task shown in the report (triage, freezer and expiry tables)."""
    tasks = result.tasks
    return [*tasks.tasks, *tasks.freezer_tasks, *tasks.expire_level1, *tasks.expire_level2]


def _descriptions(tasks: list[Task]) -> dict[str, str]:
    """Return {bug number: description} (blocking Launchpad access)."""
    descriptions: dict[str, str] = {}
    for lp_task in tasks:
        if lp_task.number in descriptions:
            continue
        try:
            descriptions[lp_task.number] = lp_task.lp_task.bug.description or ""
        except Exception:
            logger.warning("Could not fetch description of LP #%s", lp_task.number, exc_info=True)
    return descriptions


async def _run_ai(
    config: StarTriageConfig, result: LaunchpadTriage, provider: Provider
) -> list[BugOutcome]:
    """Run startriage's AI pipeline over the triage table, like ``triage --ai``.

    This mirrors startriage's ``run_ai_over_triage_results``, which only returns
    the rendered markdown, to keep each bug's outcome. Skill feedback is kept
    in the outcomes instead of startriage's feedback log file.
    """
    payloads = await asyncio.to_thread(payloads_from_tasks, list(result.tasks.tasks))
    if not payloads:
        return []
    lp = result.tasks.lp
    team = await asyncio.to_thread(team_members, lp, result.team_config.lp_team)
    window = (result.filter.start, result.filter.end)
    tool_names = enabled_tool_names(config.ai)
    github_token = config.general.github_token
    async with aiohttp.ClientSession() as http_session:
        http = ReadOnlyHTTP(
            http_session,
            allowed_posts=debian.ALLOWED_POSTS,
            # Sent to api.github.com only, for higher search limits.
            credentials=(
                {"api.github.com": {"Authorization": f"Bearer {github_token}"}}
                if github_token and "github_search" in tool_names
                else None
            ),
        )
        with scratch_dir() as workdir:
            tools = build_tools(ToolContext(lp=lp, http=http, workdir=workdir), tool_names)
            pipeline = Pipeline(
                provider=provider,
                tools={tool.name: tool for tool in tools},
                lp=lp,
                http=http,
                team=team,
                window=window,
                urls=URLChecker(http if "verify_url" in tool_names else None),
                feedback=config.ai.suggest_improvements,
                model=config.ai.model or "",
                working_directory=workdir,
            )
            return await triage_bugs(pipeline, payloads)


@dataclass
class FetchedTriage:
    items: list[ReportItem] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    # Launchpad bug details by bug number.
    details: dict[str, BugDetails] = field(default_factory=dict)
    # startriage's triage markdown report.
    markdown: str = ""


async def _fetch_report_items(
    config: StarTriageConfig,
    opts: TaskFilterOptions,
    ai_provider: Provider | None = None,
    markdown_range: str = "",
) -> FetchedTriage:
    """Fetch all sources like ``startriage triage --html --markdown FILE [--ai]``.

    As with ``startriage triage --ai``, only the Launchpad bugs of the triage
    table are analysed, and only when *ai_provider* is given. *markdown_range*
    is the date range of the markdown report's title, e.g. " 2026-10-19".
    """
    results = await fetch(config, opts, FetchMode.triage)
    items: list[ReportItem] = []
    failed: list[str] = []
    details: dict[str, BugDetails] = {}
    ai_report = ""
    for source, result in results.items():
        if result.error is not None:
            logger.warning("startriage source %s failed: %s", source, result.error)
            failed.append(source)
            continue
        items.extend(await result.report_items(None))
        if not isinstance(result, LaunchpadTriage):
            continue
        descriptions = await asyncio.to_thread(_descriptions, _launchpad_tasks(result))
        outcomes = None
        if ai_provider is not None:
            outcomes = await _run_ai(config, result, ai_provider)
            if outcomes:
                ai_report = render_report(outcomes, tools=enabled_tool_names(config.ai))
        details = bug_details(descriptions, outcomes)
    markdown = await startriage_report._triage_markdown(results, markdown_range)
    if ai_report:
        # As ``triage --markdown FILE --ai``, which appends the AI report to FILE.
        markdown += "\n\n" + AI_APPEND_NOTICE + ai_report
    return FetchedTriage(items, sorted(failed), details, markdown)


def _details_fields(row: TriageItemData, details: dict[str, BugDetails]) -> dict:
    """Return the TriageItem description/AI fields for *row*."""
    if row.source != "launchpad" or row.key not in details:
        return {}
    detail = details[row.key]
    return {
        "description": detail.description,
        "ai_result": detail.ai_result,
        "ai_error": detail.ai_error,
        "ai_route": detail.ai_route,
        "ai_note": detail.ai_note,
        "ai_phases": detail.ai_phases,
    }


def _default_triage_day(today: date) -> str | None:
    """Triage the current day, or the previous Friday on weekends (startriage has none)."""
    return "friday" if today.weekday() in (5, 6) else None


@task()
def refresh_bug_triage(
    username: str,
    team: str | None = None,
    triage_day: str | None = None,
    ai: bool | None = None,
) -> None:
    """Replace the bug triage table with startriage's daily triage results.

    *team* is a StartriageTeam name; by default the default (or only) team is
    used. *triage_day* is a day name as for ``startriage triage <day>``.
    Launchpad is queried with *username*'s Launchpad token, GitHub with their
    GitHub token if set.

    *ai* runs startriage's AI analysis (``triage --ai``) over the Launchpad
    bugs; by default it runs when enabled in StartriageAISettings.
    """

    DBTaskResult.objects.filter(
        task_path=refresh_bug_triage.module_path,
        status="READY",
        run_after__lte=timezone.now(),
    ).delete()

    user = User.objects.get(username=username)
    tokens = UserTokens.objects.filter(user=user).first()
    if tokens is None or not tokens.lp_token:
        raise ObjectDoesNotExist(f"No Launchpad token configured for user '{username}'.")

    teams = list(StartriageTeam.objects.all())
    default_team = next((t.name for t in teams if t.is_default), None)
    ai_settings = StartriageAISettings.objects.first()
    if ai is None:
        ai = ai_settings is not None and ai_settings.enabled
    if ai and ai_settings is None:
        raise ObjectDoesNotExist("AI analysis requested, but no Startriage AI Settings exist.")
    ai_config = (
        ai_settings.to_ai_config(tokens.copilot_token, tokens.openrouter_api_key)
        if ai_settings is not None
        else None
    )
    config = build_config(
        {t.name: t.to_team_config() for t in teams},
        default_team=default_team,
        github_token=tokens.github_token,
        ai=ai_config,
    )
    # Validates the AI provider and credentials before fetching anything.
    ai_provider = build_provider(config.ai) if ai and ai_settings is not None else None

    if triage_day is None:
        triage_day = _default_triage_day(timezone.localdate())
    opts = build_filter(config, team=team, triage_day=triage_day)
    title, subtitle = report_heading(opts)

    with _launchpad_credentials(tokens.lp_token):
        fetched = asyncio.run(
            _fetch_report_items(
                config, opts, ai_provider, markdown_range=title.removeprefix("Triage")
            )
        )
    items, failed, details = fetched.items, fetched.failed, fetched.details

    if len(failed) == len(opts.sources):
        raise RuntimeError(f"All startriage sources failed: {', '.join(failed)}")

    rows = triage_items(items)

    # Each run is a snapshot of the triage day, so replace the whole table.
    with transaction.atomic():
        TriageItem.objects.all().delete()
        TriageItem.objects.bulk_create(
            TriageItem(
                source=row.source,
                key=row.key,
                section=row.section,
                section_order=row.section_order,
                position=row.position,
                label=row.label,
                url=row.url,
                title=row.title,
                context=row.context,
                refs=row.refs,
                assignees=row.assignees,
                status=row.status,
                importance=row.importance,
                updated=row.updated,
                releases=row.releases,
                further=row.further,
                chips=row.chips,
                **_details_fields(row, details),
            )
            for row in rows
        )
        TriageReport.objects.all().delete()
        TriageReport.objects.create(
            team=opts.team,
            title=title,
            subtitle=subtitle,
            start=opts.start,
            end=opts.end,
            failed_sources=failed,
            markdown=fetched.markdown,
            markdown_filename=markdown_filename(opts),
        )

    PageMetadata.touch(PAGE_SLUG)
