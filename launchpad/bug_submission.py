from django.http import QueryDict

class BugSubmission:
    """Handles bug submission form data from POST requests."""

    def __init__(self, post_data: QueryDict):
        """Initialize BugSubmission with form data from POST request.

        Args:
            post_data: Django request.POST QueryDict containing form data
        """
        self._package = post_data.get("package", "").strip()
        self._milestone = post_data.get("milestone", "").strip()
        self._assignee = post_data.get("assignee", "").strip()
        self._bug_type = post_data.get("bug_type", "merge").strip()
        self._affected_releases = post_data.getlist("affected_releases")

    def to_dict(self) -> dict:
        """Convert submission data to dictionary.

        Returns:
            Dictionary representation of the bug submission
        """
        return {
            "package": self._package,
            "milestone": self._milestone,
            "assignee": self._assignee,
            "bug_type": self._bug_type,
            "affected_releases": self._affected_releases,
        }

    def get_title(self, cycleName: str) -> str | None:
        """Generate a bug title based on the submission data.

        Args:
            cycleName: The name of the current development cycle (e.g. "resolute")

        Returns:
            A string representing the bug title, or None if the bug type is unrecognized
        """
        if cycleName == "":
            cycleName = "upcoming"

        if self._bug_type == "merge":
            return f"Merge {self._package} for {cycleName} cycle"
        elif self._bug_type == "backport":
            return f"Backport {self._package} for {cycleName} cycle"
        else:
            return None

    def get_milestone(self) -> str | None:
        """Get the Launchpad milestone for the bug.

        Returns:
            The milestone string, or None if not specified
        """
        if self._milestone != "":
            return f"ubuntu-{self._milestone}"

        return None

    def get_assignee(self) -> str | None:
        """Get the Launchpad assignee for the bug.

        Returns:
            The assignee string, or None if not specified
        """
        if self._assignee != "":
            return self._assignee

        return None

    def get_affected_releases(self) -> list[str]:
        """Get the list of affected Ubuntu releases for a backport bug.

        Returns:
            A list of release strings, or an empty list if not specified or if not a backport bug
        """
        if self._bug_type == "backport":
            return self._affected_releases

        return []
