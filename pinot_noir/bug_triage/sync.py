"""Small startriage configuration helpers shared by the startriage pages."""

from startriage.config import AIConfig, GeneralConfig, StarTriageConfig, TeamConfig
from startriage.dates import last_day
from startriage.source import TaskFilterOptions


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


def markdown_filename(opts: TaskFilterOptions) -> str:
    """Return the file name startriage's ``triage --html`` saves the markdown as."""
    days = dict.fromkeys(d.isoformat() for d in (opts.start.date(), last_day(opts.end)))
    return "-".join(["triage", *days]) + ".md"
