"""Helper functions and constants for data_manager tasks."""

from debian.changelog import ChangeBlock, Changelog, ChangelogParseError
from debian.debian_support import Version
from ubq import QueryService
from ubq.errors import RequestTimeoutError
from ubq.models import (
    BugRecord,
    BugSearchRecord,
    BugSubmissionRecord,
    MergeRequestRecord,
    MergeRequestVoteRecord,
    UserRecord,
    VersionRecord,
)

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
    "Code failed to merge": Review.STATUS_NEEDS_FIXING,
    "Merged": Review.STATUS_APPROVED,
}

# Launchpad merge-proposal statuses that should not appear on the review board.
LP_REVIEW_SKIP_STATUSES: frozenset[str] = frozenset({"Rejected", "Superseded"})

# Map Launchpad code-review vote values to Review status choices.
LP_VOTE_STATUS_MAP: dict[str, str] = {
    "Needs Fixing": Review.STATUS_NEEDS_FIXING,
    "Needs Information": Review.STATUS_NEEDS_INFORMATION,
    "Approve": Review.STATUS_APPROVED,
}

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


def _changelog_text(version: VersionRecord | None) -> str:
    """Return the changelog text from a version record, or an empty string."""
    if version is None:
        return ""
    changelog = version.changelog
    return changelog if isinstance(changelog, str) else ""


def _blocks_before_version(blocks: list[ChangeBlock], version: str) -> list[ChangeBlock]:
    """Return the changelog blocks that appear before (are newer than) *version*."""
    collected: list[ChangeBlock] = []
    for block in blocks:
        if block.version is not None and str(block.version) == version:
            break
        collected.append(block)
    return collected


def changelog_diff_since_common(ubuntu_changelog: str, debian_changelog: str) -> str:
    """Return changelog entries newer than the version common to both changelogs.

    Parses the raw Ubuntu and Debian changelog text, finds the most recent
    version that appears in both, and returns the Ubuntu and Debian changelog
    blocks that are newer than that common version, grouped under headings.

    Returns an empty string when either changelog is missing or no common
    version can be found.
    """
    if not ubuntu_changelog or not debian_changelog:
        return ""

    try:
        ubuntu_blocks = list(Changelog(ubuntu_changelog))
        debian_blocks = list(Changelog(debian_changelog))
    except ChangelogParseError:
        return ""

    debian_versions = {str(block.version) for block in debian_blocks if block.version is not None}

    common_version = next(
        (
            str(block.version)
            for block in ubuntu_blocks
            if block.version is not None and str(block.version) in debian_versions
        ),
        None,
    )
    if common_version is None:
        return ""

    ubuntu_new = _blocks_before_version(ubuntu_blocks, common_version)
    debian_new = _blocks_before_version(debian_blocks, common_version)

    sections: list[str] = []

    if debian_new:
        sections.append(
            "### New Debian Changes ###\n\n"
            + "".join(str(block) for block in debian_new)
        )

    if ubuntu_new:
        sections.append(
            "### Old Ubuntu Delta ###\n\n"
            + "".join(str(block) for block in ubuntu_new)
        )
    return "\n".join(sections)


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

        self._proposed_changelog: str = ""
        self._release_changelog: str = ""
        self._debian_unstable_changelog: str = ""
        self._debian_experimental_changelog: str = ""

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

        ubuntu_changelog = (
            self._proposed_changelog if self._use_proposed else self._release_changelog
        )
        debian_changelog = (
            self._debian_experimental_changelog
            if self._use_experimental
            else self._debian_unstable_changelog
        )
        changelog_diff = changelog_diff_since_common(ubuntu_changelog, debian_changelog)
        if changelog_diff:
            full_str += f"\n{changelog_diff}\n"

        return full_str

    def _get_version(
        self, archive: str, series: str, pocket: str = "Release"
    ) -> VersionRecord | None:
        """Get the package version record for archive, series, and pocket."""
        try:
            return self._queryService.get_version(
                self._package_name,
                archive=archive,
                series=series,
                pocket=pocket,
                provider_name="launchpad",
            )
        except RequestTimeoutError:
            return None

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
        """Refresh all version strings and changelogs from Launchpad."""
        proposed = self._get_version("ubuntu", self._devel_series, pocket="Proposed")
        release = self._get_version("ubuntu", self._devel_series, pocket="Release")
        unstable = self._get_version("debian", "sid")
        experimental = self._get_version("debian", "experimental")

        self._proposed_version = proposed.version_string if proposed else ""
        self._release_version = release.version_string if release else ""
        self._debian_unstable_version = unstable.version_string if unstable else ""
        self._debian_experimental_version = experimental.version_string if experimental else ""

        self._proposed_changelog = _changelog_text(proposed)
        self._release_changelog = _changelog_text(release)
        self._debian_unstable_changelog = _changelog_text(unstable)
        self._debian_experimental_changelog = _changelog_text(experimental)

        self._determine_versions_to_use()

    def ready_for_merge(self) -> bool:
        """Return True if the package is ready for merge."""
        return self._ready_for_merge

    def get_debian_merge_version(self) -> str:
        """Return the Debian version being merged (experimental or unstable)."""
        if self._use_experimental:
            return self._debian_experimental_version
        return self._debian_unstable_version

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
    ``refs/heads/ubuntu/<SERIES>-proposed``. If a Debian branch
    is used, assume this is a merge and use devel.
    """
    if not branch:
        return ""
    parts = branch.split("/")
    for i, part in enumerate(parts):
        if part == "ubuntu" and i + 1 < len(parts):
            return parts[i + 1].split("-")[0]
        if part == "debian":
            return "devel"
    return ""


def review_status_from_merge_request(
    mr: MergeRequestRecord,
    team_usernames: set[str],
) -> str:
    """Determine the Review status for a Launchpad merge proposal.

    The Launchpad queue status is mapped first.  When it maps to
    ``STATUS_NEEDS_REVIEW`` the individual review votes are inspected to check for
    a more specific status: needs fixing, needs information, or team/community
    approval. A voter listed in *team_usernames* counts as a team approval;
    any other approving voter counts as a community approval. Blocking votes
    take precedence over approvals. When a voter has cast multiple votes, only
    their latest vote is considered.
    """
    status = LP_STATUS_MAP.get(mr.status or "", Review.STATUS_NEEDS_REVIEW)
    if status != Review.STATUS_NEEDS_REVIEW:
        return status

    latest_votes: dict[str, MergeRequestVoteRecord] = {}
    for vote in mr.votes:
        username = vote.voter.username
        current = latest_votes.get(username)
        if current is None:
            latest_votes[username] = vote
            continue
        if vote.voted_at is not None and (
            current.voted_at is None or vote.voted_at >= current.voted_at
        ):
            latest_votes[username] = vote

    has_needs_fixing = False
    has_needs_information = False
    has_team_approval = False
    has_community_approval = False

    for vote in latest_votes.values():
        mapped = LP_VOTE_STATUS_MAP.get(vote.vote or "")
        if mapped == Review.STATUS_NEEDS_FIXING:
            has_needs_fixing = True
        elif mapped == Review.STATUS_NEEDS_INFORMATION:
            has_needs_information = True
        elif mapped == Review.STATUS_APPROVED:
            if vote.voter.username in team_usernames:
                has_team_approval = True
            else:
                has_community_approval = True

    if has_needs_fixing:
        return Review.STATUS_NEEDS_FIXING
    if has_needs_information:
        return Review.STATUS_NEEDS_INFORMATION
    if has_team_approval:
        return Review.STATUS_TEAM_APPROVED
    if has_community_approval:
        return Review.STATUS_COMMUNITY_APPROVED
    return Review.STATUS_NEEDS_REVIEW


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
            try:
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
            except RequestTimeoutError:
                continue


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

    debian_version = new_merge_version_info.get_debian_merge_version()
    bug_submission = BugSubmissionRecord(
        provider_name="launchpad",
        title=(
            f"Merge {package_settings.package} {debian_version} "
            f"from Debian for {ubuntu_release.adjective} cycle"
        ),
        package_names=[package_settings.package],
        description=str(new_merge_version_info),
        importance="Wishlist",
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


def prepare_backport_bug(
    ubuntu_release: UbuntuRelease,
    package_settings: BackportBugPackageInfo,
    filter_settings: MergeBugFilterSettings,
) -> BugSubmissionRecord | None:
    """Prepare a bug submission for a backport if one is needed."""
    if package_settings.bug_filed_this_cycle:
        return None

    possible_milestones = sorted(milestones_for_release(ubuntu_release.version))
    if package_settings.milestone_offset < len(possible_milestones):
        use_milestone = f"ubuntu-{possible_milestones[package_settings.milestone_offset]}"
    else:
        use_milestone = f"ubuntu-{possible_milestones[0]}"

    return BugSubmissionRecord(
        provider_name="launchpad",
        title=f"Backport {package_settings.name} for {ubuntu_release.adjective} cycle",
        package_names=package_settings.packages,
        description=package_settings.description_template,
        importance="Wishlist",
        tags=filter_settings.tags,
        milestone=use_milestone,
        subscribers=[UserRecord(username=sub) for sub in filter_settings.subscribers],
    )


def prepare_backport_bugs_for_all_packages(
    ubuntu_release: UbuntuRelease,
    filter_settings: MergeBugFilterSettings,
) -> list[tuple[str, BugSubmissionRecord]]:
    """Prepare backport bug submissions for every configured backport package.

    Returns ``(package_name, submission)`` pairs for packages that currently
    require a backport bug.
    """
    submissions: list[tuple[str, BugSubmissionRecord]] = []
    for package_settings in BackportBugPackageInfo.objects.order_by("name"):
        submission = prepare_backport_bug(
            ubuntu_release=ubuntu_release,
            package_settings=package_settings,
            filter_settings=filter_settings,
        )
        if submission is not None:
            print(f"Prepared backport bug for {package_settings.name}")
            submissions.append((package_settings.name, submission))
    return submissions
