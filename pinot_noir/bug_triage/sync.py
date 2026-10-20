"""startriage -> TriageItem mapping for the bug triage page.

Everything here is free of database and network access, so the mapping can be
tested with plain startriage ``ReportItem`` objects.
"""

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, time

from startriage.ai import BugOutcome
from startriage.ai.phases import PhaseOutcome
from startriage.config import AIConfig, GeneralConfig, StarTriageConfig, TeamConfig
from startriage.dates import compact_date_range, last_day
from startriage.htmlreport import triage_sections
from startriage.output import Flag, Link, ReportItem
from startriage.source import TaskFilterOptions

# Context column header per source, as in startriage's html report.
CONTEXT_LABELS: dict[str, str] = {
    "launchpad": "Package",
    "github": "Repo",
    "discourse": "Category",
    "proposed": "Versions",
}

# Flags shown as chips next to the title, as in startriage's html report.
CHIP_LABELS: dict[Flag, str] = {
    Flag.NEW: "new",
    Flag.EXTERNAL: "reply pending",
    Flag.VERIFICATION_NEEDED: "verification needed",
    Flag.VERIFICATION_DONE: "verification done",
    Flag.EXPIRING: "expiring",
}


@dataclass(frozen=True)
class TriageItemData:
    """TriageItem row values derived from a startriage ReportItem."""

    source: str
    key: str
    section: str
    section_order: int
    position: int
    label: str
    url: str
    title: str
    context: list[list[str]]
    refs: list[list[str]]
    assignees: list[list[str]]
    status: str
    importance: str
    updated: datetime | None
    releases: list[list[str]]
    further: list[str]
    chips: list[str]


@dataclass(frozen=True)
class BugDetails:
    """Dropdown values for one Launchpad bug: description and AI analysis."""

    description: str = ""
    # startriage AgentResult as JSON, when the model answered.
    ai_result: dict | None = None
    # Why the analysis failed (startriage renders it as "triage failed").
    ai_error: str = ""
    # Precheck route, e.g. "triage" or "skip-recent".
    ai_route: str = ""
    # Why the bug was not sent to the model (denied/skip routes).
    ai_note: str = ""
    # What each phase did, from startriage's host log: see phase_data().
    ai_phases: list[dict] | None = None


def phase_data(phase: PhaseOutcome) -> dict:
    """JSON of one startriage pipeline phase, as its markdown "Thought Process" shows it."""
    return {
        "phase": phase.phase,
        "state": phase.state.value,
        "summary": " ".join(phase.summary.split()),
        "tool_calls": list(phase.tool_calls),
        # "name xN" per tool, in call order, as startriage's markdown.
        "tools": ", ".join(
            f"{name} x{count}" if count > 1 else name
            for name, count in Counter(phase.tool_calls).items()
        ),
        "sessions": phase.sessions,
        "input_tokens": phase.input_tokens,
        "output_tokens": phase.output_tokens,
        "feedback": " ".join(phase.feedback.split()),
    }


def build_config(
    teams: dict[str, TeamConfig],
    default_team: str | None = None,
    github_token: str | None = None,
    ai: AIConfig | None = None,
) -> StarTriageConfig:
    """Return a startriage config holding only the given values.

    Nothing is read from startriage's shipped defaults or a user config file.
    """
    return StarTriageConfig(
        general=GeneralConfig(default_team=default_team, github_token=github_token or None),
        ai=ai or AIConfig(),
        team=teams,
    )


def bug_details(
    descriptions: dict[str, str], outcomes: list[BugOutcome] | None = None
) -> dict[str, BugDetails]:
    """Combine bug descriptions and AI outcomes, keyed by Launchpad bug number."""
    by_bug = {outcome.bug: outcome for outcome in outcomes or []}
    details = {}
    for number, description in descriptions.items():
        outcome = by_bug.get(number)
        if outcome is None:
            details[number] = BugDetails(description=description)
            continue
        details[number] = BugDetails(
            description=description,
            ai_result=outcome.result.model_dump(mode="json") if outcome.result else None,
            ai_error=outcome.error or "",
            ai_route=outcome.route,
            ai_note=outcome.note,
            ai_phases=[phase_data(phase) for phase in outcome.phases],
        )
    return details


def report_heading(opts: TaskFilterOptions) -> tuple[str, str]:
    """Return the (title, subtitle) startriage's ``triage --html`` uses for *opts*.

    *opts* holds a half-open interval [start, end); whole days end at 00:00 of
    the day after the last one.
    """
    first, last = opts.start.date(), last_day(opts.end)
    if opts.start.time() == time.min and opts.end.time() == time.min:
        date_range = compact_date_range(first, last)
        first_str, last_str = (d.strftime("%Y-%m-%d (%A)") for d in (first, last))
        if first == last:
            range_verbose = f"on {first_str}"
        else:
            range_verbose = f"between {first_str} and {last_str} inclusive"
    else:
        date_range = f"{opts.start.isoformat()}->{opts.end.isoformat()}"
        range_verbose = f"from {opts.start.isoformat()} until {opts.end.isoformat()}"

    return f"Triage {date_range}", f"team {opts.team}, items updated {range_verbose}"


def markdown_filename(opts: TaskFilterOptions) -> str:
    """Return the file name startriage's ``triage --html`` saves the markdown as."""
    days = dict.fromkeys(d.isoformat() for d in (opts.start.date(), last_day(opts.end)))
    return "-".join(["triage", *days]) + ".md"


def _links(links: list[Link]) -> list[list[str]]:
    return [[link.text, link.url] for link in links]


def item_data(item: ReportItem, section: str, section_order: int, position: int) -> TriageItemData:
    """Map one startriage ReportItem to row values."""
    chips = []
    if Flag.GONE not in item.flags:
        chips = [label for flag, label in CHIP_LABELS.items() if flag in item.flags]

    return TriageItemData(
        source=item.source,
        key=str(item.key),
        section=section,
        section_order=section_order,
        position=position,
        label=item.label,
        url=item.url,
        title=item.title,
        context=_links(item.context),
        refs=_links(item.refs),
        assignees=_links(item.assignees),
        status=item.status,
        importance=item.importance,
        updated=item.updated,
        releases=[[letter, state] for letter, state in item.releases],
        further=list(item.further),
        chips=chips,
    )


def triage_items(items: list[ReportItem]) -> list[TriageItemData]:
    """Group items into startriage's html report sections, keeping its order."""
    rows: list[TriageItemData] = []
    for section_order, (section, section_items) in enumerate(triage_sections(items)):
        for position, item in enumerate(section_items):
            rows.append(item_data(item, section, section_order, position))
    return rows


def context_label(sources: list[str]) -> str:
    """Context column header for a section, e.g. "Package" or "Package / Repo"."""
    return " / ".join(CONTEXT_LABELS.get(source, "") for source in dict.fromkeys(sources))
