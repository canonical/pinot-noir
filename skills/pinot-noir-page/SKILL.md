---
name: pinot-noir-page
description: "Use when adding a new data page (sidebar entry + table backed by a Launchpad/ubq sync task) to the Pinot Noir Django app. Checklist: AppConfig page declaration (registry drives nav, URLs, PageMetadata, scheduling, refresh_page), model, sync/tasks split, template, tests, tox."
version: 1.1.0
author: Lena Voytek
metadata:
    tags: [pinot-noir, django, pages, ubq, launchpad, vanilla-framework]
    related_skills: [ubq]
---

# Adding a page to Pinot Noir

## Overview

Each data page in Pinot Noir is its own Django app under `pinot_noir/<app>/`.
The two existing pages are the reference implementations:

- `pinot_noir/reviews/` (simplest; copy this one)
- `pinot_noir/merges_schedule/` (adds per-row follow-up tasks and a panel)

A page app owns everything specific to it:

| File | Purpose |
|------|---------|
| `models.py` | Table rows shown on the page |
| `sync.py` | Pure functions: ubq records -> plain dataclasses. No DB, no network. |
| `tasks.py` | `@task()` that fetches via ubq, then writes inside `transaction.atomic()` and calls `PageMetadata.touch(<slug>)` |
| `views.py` | `index` view: query, sort, build filter-chip lists, render |
| `apps.py` | `PAGE_SLUG` constant + `page = Page(...)` on the AppConfig |
| `urls.py` | `app_name = "<app label>"`, `path(PAGE_SLUG, views.index, name="index")` |
| `templates/<app>/index.html` | Extends `base.html` |
| `admin.py` | ModelAdmin for the rows |
| `tests.py`, `test_sync.py` | View smoke test + pure sync tests |

Shared code lives elsewhere:

- `pinot_noir/pages/`: the page registry (`registry.py`: `Page`,
  `get_pages()`), `PageMetadata` (slug, `enabled`, `last_refreshed_at`), the
  nav context processor, `page_urlpatterns()`, a post_migrate hook creating a
  PageMetadata row per page, system checks (`checks.py`, ids `pages.E00x`),
  and the `refresh_page` management command.
- `pinot_noir/data_manager/common.py`: `get_launchpad_service_for_user(username)`,
  `get_devel_or_requested_release(adjective)`, `milestones_for_release`.
- `pinot_noir/data_manager/tasks.py`: weekly scheduler. Page refresh tasks
  are picked up from the registry automatically.
- ubq: query APIs. Load the `ubq` skill in `../ubq/skills/ubq/` for those.

## Checklist

Pick names up front:

- app module and label: `snake_case` (e.g. `sru_queue`)
- page slug: `kebab-case` (e.g. `sru-queue`). It is also the URL path.
- refresh task: `refresh_<app>` (e.g. `refresh_sru_queue`)

### 1. App skeleton and page declaration

```
mkdir pinot_noir/<app> && uv run manage.py startapp <app> pinot_noir/<app>
```

`apps.py` is the single source of truth for the page:

```python
from django.apps import AppConfig

from pinot_noir.pages.registry import Page

PAGE_SLUG = "sru-queue"


class SruQueueConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "pinot_noir.sru_queue"
    label = "sru_queue"
    page = Page(
        slug=PAGE_SLUG,
        label="SRU Queue",
        icon="circle-of-friends",  # Vanilla p-icon--* name
        refresh_task="pinot_noir.sru_queue.tasks.refresh_sru_queue",
        order=30,  # sidebar position; existing pages use 10, 20
    )
```

Add `"pinot_noir.<app>"` under "Pinot Noir web page applications" in
`INSTALLED_APPS` (`pinot_noir/settings/base.py`). That's the only edit outside
the app. The registry then provides:

- the sidebar entry
- the URL include (via `page_urlpatterns()` in the root urls.py)
- the PageMetadata row, created on `migrate`
- a "Refresh <label>" choice in the WeeklyTask admin, plus scheduling
- `manage.py refresh_page <slug> --username <you>`

Import `PAGE_SLUG` from `.apps` everywhere else (views, tasks, urls). Never
retype the string.

### 2. Model

- Use a stable natural key from the source as a `unique=True` field (reviews
  use `mp_url`, merges use `bug_id`). The sync upserts on it.
- Link Launchpad people with `ForeignKey(LPUser, null=True, on_delete=SET_NULL)`
  and keep the raw username string beside it (see `Review.reviewer` /
  `reviewer_user`), because not every Launchpad user has an LPUser row.
- Put status values in class constants plus `STATUS_CHOICES`.
- Run `uv run manage.py makemigrations <app>`.

### 3. sync.py (pure mapping)

- Input: ubq records (`MergeRequestRecord`, `BugRecord`, ...). Output: a frozen
  dataclass (`ReviewData` is the template) or `None` to drop the record.
- No ORM calls and no QueryService calls in here. That keeps it unit-testable
  with `MagicMock` records (see `reviews/test_sync.py`).

### 4. tasks.py (fetch, then write)

Follow `reviews/tasks.py`:

1. Delete stale READY duplicates of this task from `DBTaskResult`.
2. `service = get_launchpad_service_for_user(username)`.
3. Fetch everything first. Catch `RequestTimeoutError` per item and continue.
4. Inside one `transaction.atomic()`: `update_or_create` on the natural key,
   then delete rows not seen. Only delete if the import is non-empty, so a
   failed or empty fetch never wipes the page.
5. `PageMetadata.touch(PAGE_SLUG)` after the transaction.

The task's first parameter must be `username: str` (the scheduler and
`refresh_page` pass it as a keyword). An optional `release_adjective` works
with `refresh_page --release`.

Never make network calls inside the transaction.

### 5. Views and URLs

- `urls.py`: `app_name = "<app label>"`,
  `path(PAGE_SLUG, views.index, name="index")`. The registry derives the URL
  name `<label>:index`, and the `pages.E003`/`E004` checks fail if it doesn't
  resolve or doesn't match the slug.
- The view must pass `page_meta`
  (`PageMetadata.objects.filter(slug=PAGE_SLUG).first()`) so the "Last
  refreshed" footer renders, plus `title` and the filter-chip lists.
- Run `uv run manage.py migrate`. Toggle `enabled` on the page's PageMetadata
  row in admin to hide it from the sidebar.

### 6. Template

Copy `reviews/templates/reviews/index.html` and change:

- the title default
- one `p-filter-panel-section` per filter. `searchandfilter.js` maps chip
  `data-filter-type` to a column by the lowercased `<th>` text, so
  `data-filter-type="release"` needs a `<th>Release</th>` column. A `status`
  column gets special handling.
- the table columns: `<th aria-sort="none">` makes a column sortable via
  `tablesorting.js`
- keep the `page_meta.last_refreshed_at` footer block

### 7. Scheduling and a manual trigger

Nothing to do. Declaring `refresh_task` on the Page:

- adds it to the WeeklyTask admin dropdown (`WeeklyTask.task_choices()`; the
  model field has no `choices=`, so no data_manager migration is needed)
- adds it to the scheduler (`get_schedulable_tasks()`)
- makes it available as `uv run manage.py refresh_page <slug> --username <you>`

Only non-page tasks (pruning, bug submission) are listed by hand, in
`WeeklyTask.BASE_TASK_CHOICES` and `get_schedulable_tasks()`.

### 8. Admin and tests

- Register a ModelAdmin with `list_display`, `list_filter`, `search_fields`.
- `test_sync.py`: mapping cases, including `None` returns.
- `pages/tests.py` already loads every registered page, checks the nav and
  scheduler wiring, and runs the `pages.*` checks. Update
  `test_pages_registered`'s expected slug list.
- `tests.py`: view sorting/context tests,
  and the task test patches `get_launchpad_service_for_user` at
  `pinot_noir.<app>.tasks.get_launchpad_service_for_user`.

### 9. Verify

```
DJANGO_SETTINGS_MODULE=pinot_noir.settings.dev uv run manage.py test
uv run manage.py check
uvx tox            # codespell, ruff check, ruff format --check, ty
uv run manage.py refresh_page <slug> --username <you>   # with a worker running
```

`uvx tox -e format` fixes formatting. ty needs django-stubs (already in the
lint group).

## Pitfalls

- `uv run manage.py check` validates every page (slug format, duplicate
  slugs, URL resolves and matches the slug, refresh task imports and is a
  `@task`). Run it first when a page doesn't show up.
- `WeeklyTask.task` stores the task function name. Renaming a refresh task
  orphans existing WeeklyTask rows (the scheduler skips unknown names), so
  update those rows in admin.
- Moving or renaming a task changes its `module_path`. Queued DBTaskResult
  rows still reference the old path, so re-export from the old module until
  they drain (`data_manager/tasks.py` does this for the moved sync tasks).
- Renaming a table header breaks its filter chips (see step 6).
- Templates load page JS in `{% block includes %}`. `navigation.js` is
  already loaded by `base.html`, so don't load it again.
