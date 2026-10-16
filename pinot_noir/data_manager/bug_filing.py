"""Merge/backport bug preparation helpers for data_manager tasks."""

from debian.changelog import ChangeBlock, Changelog, ChangelogParseError
from debian.debian_support import Version
from ubq import QueryService
from ubq.errors import RequestTimeoutError
from ubq.models import BugSubmissionRecord, UserRecord, VersionRecord

from pinot_noir.data_manager.common import milestones_for_release
from pinot_noir.data_manager.models import (
    BackportBugPackageInfo,
    MergeBugFilterSettings,
    MergeBugPackageInfo,
)
from pinot_noir.launchpad.models import UbuntuRelease


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
            "### New Debian Changes ###\n\n" + "".join(str(block) for block in debian_new)
        )

    if ubuntu_new:
        sections.append(
            "### Old Ubuntu Delta ###\n\n" + "".join(str(block) for block in ubuntu_new)
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
