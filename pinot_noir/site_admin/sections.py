"""The site admin's own side navigation."""

from dataclasses import dataclass

from django.urls import reverse


@dataclass(frozen=True)
class Section:
    url_name: str
    label: str


# Add new admin subpages here; the first one is the /manage/ landing page.
SECTIONS: tuple[Section, ...] = (
    Section("site_admin:team", "My team"),
    Section("site_admin:tokens", "My tokens"),
    Section("site_admin:pages", "Pages"),
)


def section_entries(current_path: str) -> list[dict]:
    entries = []
    for section in SECTIONS:
        url = reverse(section.url_name)
        entries.append(
            {
                "label": section.label,
                "url": url,
                "is_active": current_path == url,
            }
        )
    return entries
