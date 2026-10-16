"""Launchpad -> Merge mapping for the merge schedule.

Everything here is free of database access: callers pass in any lookups
(LP users, backport groups) so the mapping can be tested without a database
or a Launchpad mock.
"""

from dataclasses import dataclass

from ubq import QueryService
from ubq.errors import RequestTimeoutError
from ubq.models import BugRecord, BugSearchRecord

from pinot_noir.merges_schedule.models import Merge

# Map Launchpad bug task status values to Merge status choices.
LP_BUG_STATUS_MAP: dict[str, str] = {
    "New": Merge.STATUS_NEW,
    "Incomplete": Merge.STATUS_NEW,
    "Confirmed": Merge.STATUS_NEW,
    "Triaged": Merge.STATUS_NEW,
    "In Progress": Merge.STATUS_STARTED,
    "Fix Committed": Merge.STATUS_UPLOADED,
    "Fix Released": Merge.STATUS_DONE,
}


@dataclass(frozen=True)
class MergeData:
    """Merge row values derived from a Launchpad bug, before any DB lookups."""

    lp_bug: int
    package: str
    merge_type: str
    assignee: str
    milestone: str
    status: str


def backport_package_name(packages: list[str], backport_groups: list[tuple[str, set[str]]]) -> str:
    """Return the backport group name matching the bug's packages.

    *backport_groups* is a list of ``(name, packages)`` pairs. Falls back to
    the first package name if no group matches.
    """
    package_set = set(packages)
    for name, group_packages in backport_groups:
        if group_packages <= package_set:
            return name
    return packages[0]


def collect_bugs_for_type(
    service: QueryService,
    tags: list[str],
    valid_milestones: set[str],
    merge_type: str,
    bugs: dict[str, tuple],
) -> None:
    """Search LP for bugs with *tags* across all valid milestones.

    Adds ``bug_id -> (bug, milestone, merge_type)`` to *bugs*; the first
    match for a bug wins.
    """
    if not tags:
        return
    for raw_milestone in valid_milestones:
        lp_milestone = f"ubuntu-{raw_milestone}"
        for status in (None, "Fix Released"):
            try:
                for bug in service.search_bugs(
                    BugSearchRecord(
                        provider_name="launchpad",
                        tags=tags,
                        milestone=lp_milestone,
                        status=status,
                    ),
                    provider_name="launchpad",
                ):
                    bugs.setdefault(bug.id, (bug, raw_milestone, merge_type))
            except RequestTimeoutError:
                continue


def merge_from_bug(
    bug_id: str,
    full_bug: BugRecord,
    milestone: str,
    merge_type: str,
    backport_groups: list[tuple[str, set[str]]],
) -> MergeData | None:
    """Build MergeData from a full bug record, or None if it should be skipped."""
    if not full_bug.bug_tasks:
        return None

    if merge_type == Merge.TYPE_BACKPORT:
        packages = [p for bug_task in full_bug.bug_tasks if (p := bug_task.package_name or "")]
        if not packages:
            return None
        package = backport_package_name(packages, backport_groups)
    else:
        package = full_bug.bug_tasks[0].package_name or ""
        if not package:
            return None

    first_task = full_bug.bug_tasks[0]
    assignee = ""
    if first_task.assignee and first_task.assignee.username:
        assignee = first_task.assignee.username
    status = Merge.STATUS_NEW
    if first_task.status:
        status = LP_BUG_STATUS_MAP.get(first_task.status, Merge.STATUS_NEW)

    try:
        bug_number = int(bug_id)
    except ValueError:
        return None

    return MergeData(
        lp_bug=bug_number,
        package=package,
        merge_type=merge_type,
        assignee=assignee,
        milestone=milestone,
        status=status,
    )
