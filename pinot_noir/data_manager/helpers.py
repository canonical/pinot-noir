"""Helper functions and constants for data_manager tasks."""

from debian.debian_support import Version
from ubq import QueryService
from ubq.models import BugRecord, BugSearchRecord, BugSubmissionRecord, UserRecord

from pinot_noir.data_manager.models import (
    BackportBugPackageInfo,
    MergeBugFilterSettings,
    MergeBugPackageInfo,
)
from pinot_noir.launchpad.models import LPUser, UbuntuRelease
from pinot_noir.merges_schedule.models import Merge
from pinot_noir.reviews.models import Review

# Map Launchpad queue_status values to Review status choices.
LP_STATUS_MAP: dict[str, str] = {
    "Work in progress": Review.STATUS_WORK_IN_PROGRESS,
    "Needs review": Review.STATUS_NEEDS_REVIEW,
    "Approved": Review.STATUS_APPROVED,
    "Rejected": Review.STATUS_NEEDS_FIXING,
    "Code failed to merge": Review.STATUS_NEEDS_FIXING,
    "Queued": Review.STATUS_UNDER_REVIEW,
    "Merged": Review.STATUS_APPROVED,
    "Superseded": Review.STATUS_NEEDS_FIXING,
}

# Map Launchpad bug task status values to Merge status choices.
LP_BUG_STATUS_MAP: dict[str, str] = {
    "New": Merge.STATUS_NEW,
    "Incomplete": Merge.STATUS_NEW,
    "Confirmed": Merge.STATUS_NEW,
    "Triaged": Merge.STATUS_NEW,
    "In Progress": Merge.STATUS_STARTED,
    "Fix Committed": Merge.STATUS_STARTED,
    "Fix Released": Merge.STATUS_DONE,
}


class MergePackageVersionInfo:
    """Current version strings associated with a package in preparation for merge."""

    def __init__(self, package_name: str, devel_series: str, queryService: QueryService) -> None:
        self._package_name = package_name
        self._devel_series = devel_series
        self._queryService = queryService

        self._proposed_version: str = ""
        self._release_version: str = ""
        self._debian_unstable_version: str = ""
        self._debian_experimental_version: str = ""

        self._use_proposed: bool = False
        self._use_experimental: bool = False
        self._ready_for_merge: bool = False

    def __str__(self) -> str:
        """String representation for description entry."""
        full_str = (
            f"A new release of {self._package_name} is available for merging from Debian.\n\n"
        )

        if self._use_proposed:
            full_str += f"Ubuntu Proposed: {self._proposed_version}\n"
        else:
            full_str += f"Ubuntu: {self._release_version}\n"

        if self._use_experimental:
            full_str += f"Debian Experimental: {self._debian_experimental_version}\n"

        full_str += f"Debian Unstable: {self._debian_unstable_version}\n"

        return full_str

    def _get_version_string(self, series: str, pocket: str | None = None) -> str:
        """Get package version string for series and pocket."""
        package_version = self._queryService.get_version(
            self._package_name, series=series, pocket=pocket, provider_name="launchpad"
        )
        if package_version:
            return package_version.version_string
        return ""

    def _determine_versions_to_use(self) -> None:
        """Check if merge is ready and what versions should be used."""
        if self._proposed_version == "":
            proposed = Version("0")
        else:
            proposed = Version(self._proposed_version)

        if self._release_version == "":
            release = Version("0")
        else:
            release = Version(self._release_version)

        if self._debian_unstable_version == "":
            unstable = Version("0")
        else:
            unstable = Version(self._debian_unstable_version)

        if self._debian_experimental_version == "":
            experimental = Version("0")
        else:
            experimental = Version(self._debian_experimental_version)

        self._use_proposed = proposed > release
        self._use_experimental = experimental > unstable

        self._ready_for_merge = False

        ubuntu_version = proposed if self._use_proposed else release
        debian_version = experimental if self._use_experimental else unstable

        # Check debian version greater, ubuntu version available, and ubuntu version not a sync
        if debian_version > ubuntu_version > Version("0") and "ubuntu" in str(ubuntu_version):
            self._ready_for_merge = True

    def refresh_versions(self) -> None:
        """Refresh all version strings from Launchpad."""
        self._proposed_version = self._get_version_string(self._devel_series, pocket="Proposed")
        self._release_version = self._get_version_string(self._devel_series, pocket="Release")
        self._debian_unstable_version = self._get_version_string("debian-sid")
        self._debian_experimental_version = self._get_version_string("debian-experimental")

        self._determine_versions_to_use()

    def ready_for_merge(self) -> bool:
        """Return True if the package is ready for merge."""
        return self._ready_for_merge

    def get_package_name(self) -> str:
        """Return the package name."""
        return self._package_name


def package_from_url(web_url: str) -> str:
    """Extract the source package name from a Launchpad merge proposal URL.

    Expected URL form:
    ``https://code.launchpad.net/~.../ubuntu/+source/<PACKAGE>/...``
    """
    try:
        return web_url.split("/+source/", 1)[1].split("/", maxsplit=1)[0]
    except IndexError:
        return ""


def release_from_branch(branch: str | None) -> str:
    """Extract the Ubuntu release series from a git branch path.

    Branch paths are typically ``refs/heads/ubuntu/<SERIES>`` or
    ``refs/heads/ubuntu/<SERIES>-proposed``.
    """
    if not branch:
        return ""
    parts = branch.split("/")
    for i, part in enumerate(parts):
        if part == "ubuntu" and i + 1 < len(parts):
            return parts[i + 1].split("-")[0]
    return ""


def milestones_for_release(version: str) -> set[str]:
    """Return the set of valid LP milestone names for a Ubuntu release cycle.

    Given a version like ``'26.04'``, returns the six monthly milestones
    spanning the cycle: ``{'25.11', '25.12', '26.01', '26.02', '26.03', '26.04'}``.
    """
    year_str, month_str = version.split(".")
    year = int(year_str)
    month = int(month_str)

    milestones: set[str] = set()
    for i in range(6):
        m = month - i
        y = year
        while m <= 0:
            m += 12
            y -= 1
        milestones.add(f"{y:02d}.{m:02d}")
    return milestones


def backport_package_name(packages: list[str]) -> str:
    """Return the BackportBugPackageInfo group name matching the bug's packages.

    Falls back to the first package name if no matching group is found.
    """
    package_set = set(packages)
    for info in BackportBugPackageInfo.objects.all():
        if set(info.packages) <= package_set:
            return info.name
    return packages[0]


def collect_bugs_for_type(
    service: QueryService,
    filter_settings: MergeBugFilterSettings,
    valid_milestones: set[str],
    merge_type: str,
    bugs: dict[str, tuple],
) -> None:
    """Search LP for bugs matching filter_settings across all valid milestones."""
    if not filter_settings.tags:
        return
    for raw_milestone in valid_milestones:
        lp_milestone = f"ubuntu-{raw_milestone}"
        for status in (None, "Fix Released"):
            for bug in service.search_bugs(
                BugSearchRecord(
                    provider_name="launchpad",
                    tags=filter_settings.tags,
                    milestone=lp_milestone,
                    status=status,
                ),
                provider_name="launchpad",
            ):
                bugs.setdefault(bug.id, (bug, raw_milestone, merge_type))


def merge_from_bug(
    bug_id: str,
    full_bug: BugRecord,
    milestone: str,
    merge_type: str,
) -> Merge | None:
    """Build a Merge instance from a full bug record, or None if it should be skipped."""
    if not full_bug.bug_tasks:
        return None

    if merge_type == Merge.TYPE_BACKPORT:
        packages = [p for bug_task in full_bug.bug_tasks if (p := bug_task.package_name or "")]
        if not packages:
            return None
        package = backport_package_name(packages)
    else:
        package = full_bug.bug_tasks[0].package_name or ""
        if not package:
            return None

    first_task = full_bug.bug_tasks[0]
    assignee_username = ""
    assignee_user = None
    status = Merge.STATUS_NEW
    if first_task.assignee and first_task.assignee.username:
        assignee_username = first_task.assignee.username
        assignee_user = LPUser.objects.filter(username=assignee_username).first()
    if first_task.status:
        status = LP_BUG_STATUS_MAP.get(first_task.status, Merge.STATUS_NEW)

    try:
        bug_number = int(bug_id)
    except ValueError:
        return None

    return Merge(
        lp_bug=bug_number,
        package=package,
        merge_type=merge_type,
        assignee=assignee_username,
        assignee_user=assignee_user,
        milestone=milestone,
        status=status,
    )


def prepare_merge_bug(
    queryService: QueryService,
    ubuntu_release: UbuntuRelease,
    package_settings: MergeBugPackageInfo,
    filter_settings: MergeBugFilterSettings,
) -> BugSubmissionRecord | None:
    """Prepare a bug submission for a merge if one is needed."""
    # Package already has merge bug, skip
    if package_settings.bug_filed_this_cycle:
        return None

    # Determine milestone by offset
    possible_milestones = sorted(milestones_for_release(ubuntu_release.version))

    if package_settings.milestone_offset < len(possible_milestones):
        use_milestone = f"ubuntu-{possible_milestones[package_settings.milestone_offset]}"
    else:
        use_milestone = f"ubuntu-{possible_milestones[0]}"

    # Check Debian and Ubuntu versions
    new_merge_version_info = MergePackageVersionInfo(
        package_settings.package, ubuntu_release.adjective, queryService
    )

    new_merge_version_info.refresh_versions()
    if not new_merge_version_info.ready_for_merge():
        return None

    bug_submission = BugSubmissionRecord(
        provider_name="launchpad",
        title=f"Merge {package_settings.package} from Debian for {ubuntu_release.adjective} cycle",
        package_names=[package_settings.package],
        description=str(new_merge_version_info),
        tags=filter_settings.tags,
        milestone=use_milestone,
        subscribers=[UserRecord(username=sub) for sub in filter_settings.subscribers],
    )
    return bug_submission


def prepare_merge_bugs_for_all_packages(
    queryService: QueryService,
    ubuntu_release: UbuntuRelease,
    filter_settings: MergeBugFilterSettings,
) -> list[tuple[str, BugSubmissionRecord]]:
    """Prepare merge bug submissions for every configured merge package.

    Returns ``(package_name, submission)`` pairs for packages that currently
    require a merge bug.
    """
    submissions: list[tuple[str, BugSubmissionRecord]] = []
    for package_settings in MergeBugPackageInfo.objects.order_by("package"):
        submission = prepare_merge_bug(
            queryService=queryService,
            ubuntu_release=ubuntu_release,
            package_settings=package_settings,
            filter_settings=filter_settings,
        )
        if submission is not None:
            print(f"Prepared merge bug for {package_settings.package}")
            submissions.append((package_settings.package, submission))
    return submissions
