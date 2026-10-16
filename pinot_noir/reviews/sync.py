"""Launchpad -> Review mapping for the reviews page.

Everything here is free of database access: callers pass in the relevant
usernames so the mapping can be tested without a database or a Launchpad mock.
"""

from dataclasses import dataclass

from ubq.models import MergeRequestRecord, MergeRequestVoteRecord

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


@dataclass(frozen=True)
class ReviewData:
    """Review row values derived from a merge proposal, before any DB lookups."""

    mp_url: str
    package: str
    release_version: str
    source_branch: str
    lines_added: int | None
    lines_removed: int | None
    reviewer: str
    submitter: str
    status: str


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

    return _status_from_votes(_latest_votes(mr.votes), team_usernames)


def _latest_votes(votes: list[MergeRequestVoteRecord]) -> list[MergeRequestVoteRecord]:
    """Return only the most recent vote from each voter."""
    latest_votes: dict[str, MergeRequestVoteRecord] = {}
    for vote in votes:
        username = vote.voter.username or ""
        current = latest_votes.get(username)
        if current is None:
            latest_votes[username] = vote
            continue
        if vote.voted_at is not None and (
            current.voted_at is None or vote.voted_at >= current.voted_at
        ):
            latest_votes[username] = vote
    return list(latest_votes.values())


def _status_from_votes(votes: list[MergeRequestVoteRecord], team_usernames: set[str]) -> str:
    """Return the Review status implied by a set of (latest) review votes."""
    has_needs_fixing = False
    has_needs_information = False
    has_team_approval = False
    has_community_approval = False

    for vote in votes:
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


def review_from_merge_request(
    mr: MergeRequestRecord,
    submitter: str,
    team_usernames: set[str],
    marker_usernames: set[str],
    reviewer_usernames: set[str],
) -> ReviewData | None:
    """Build ReviewData for a merge proposal, or None if it is not on the board.

    Only proposals with a review-marker assignee (e.g. a team) are kept. The
    reviewer is the first assignee in *reviewer_usernames* (known non-marker
    LP users).
    """
    if mr.status in LP_REVIEW_SKIP_STATUSES:
        return None
    if not mr.assignees or not any(a.username in marker_usernames for a in mr.assignees):
        return None

    reviewer = next(
        (a.username for a in mr.assignees if a.username in reviewer_usernames),
        "",
    )

    return ReviewData(
        mp_url=mr.web_url or "",
        package=package_from_url(mr.web_url or ""),
        release_version=release_from_branch(mr.target_branch),
        source_branch=mr.source_branch or "",
        lines_added=mr.added_lines,
        lines_removed=mr.removed_lines,
        reviewer=reviewer,
        submitter=submitter,
        status=review_status_from_merge_request(mr, team_usernames),
    )
