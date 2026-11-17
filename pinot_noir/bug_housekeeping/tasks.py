"""Generate startriage's housekeeping HTML and persist its saved-bug lists in Git."""

import asyncio
import io
import os
import shlex
import subprocess
import tempfile
from contextlib import contextmanager
from datetime import date
from pathlib import Path

from django.contrib.auth.models import User
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.utils import timezone
from django_tasks import task
from django_tasks_db.models import DBTaskResult
from startriage.output import OutputConfig, OutputFormat
from startriage.report import todo as startriage_todo
from startriage.savebugs import BugPersistor, SaveConfig
from startriage.triage import build_filter

from pinot_noir.bug_triage.models import StartriageTeam
from pinot_noir.bug_triage.sync import build_config
from pinot_noir.bug_triage.tasks import _launchpad_credentials
from pinot_noir.data_manager.models import UserTokens
from pinot_noir.pages.models import PageMetadata

from .apps import PAGE_SLUG
from .models import HousekeepingReport, HousekeepingSettings


@contextmanager
def _git_environment(private_key: str):
    """Return a Git environment, with a temporary SSH identity when one is configured."""
    with tempfile.TemporaryDirectory(prefix="pinot-noir-git-") as directory:
        env = os.environ.copy()
        # A background worker must never wait for an interactive credential prompt.
        env["GIT_TERMINAL_PROMPT"] = "0"
        if private_key:
            key_path = Path(directory) / "id_ed25519"
            key_path.write_text(private_key.rstrip() + "\n", encoding="utf-8")
            key_path.chmod(0o600)
            env["GIT_SSH_COMMAND"] = (
                f"ssh -i {shlex.quote(str(key_path))} -o IdentitiesOnly=yes "
                "-o StrictHostKeyChecking=accept-new"
            )
        yield env


def _git(
    cwd: Path, *args: str, env: dict[str, str], check: bool = True
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if check and result.returncode:
        detail = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"Git {args[0]} failed: {detail}")
    return result


def _prepare_repository(settings: HousekeepingSettings, env: dict[str, str]) -> Path:
    """Clone or fast-forward the saved-bugs repository and return its work tree."""
    workdir = settings.checkout_path()
    if not (workdir / ".git").exists():
        if workdir.exists() and any(workdir.iterdir()):
            raise RuntimeError(f"Git checkout {workdir} exists but is not a Git work tree.")
        workdir.parent.mkdir(parents=True, exist_ok=True)
        _git(workdir.parent, "clone", settings.repository, str(workdir), env=env)
    else:
        origin = _git(workdir, "remote", "get-url", "origin", env=env).stdout.strip()
        if origin != settings.repository:
            raise RuntimeError(
                f"Git checkout {workdir} belongs to {origin!r}, not the configured repository."
            )

    # Never inherit a user's or system's automatic-signing policy in this
    # application-owned checkout. The commit command also overrides it below.
    _git(workdir, "config", "--local", "commit.gpgsign", "false", env=env)
    _git(workdir, "fetch", "--prune", "origin", env=env)
    branch = _git(workdir, "symbolic-ref", "--short", "HEAD", env=env).stdout.strip()
    remote_ref = f"refs/remotes/origin/{branch}"
    remote = _git(workdir, "show-ref", "--verify", "--quiet", remote_ref, env=env, check=False)
    if remote.returncode == 0:
        _git(workdir, "merge", "--ff-only", f"origin/{branch}", env=env)
    elif remote.returncode != 1:
        raise RuntimeError(f"Git could not inspect {remote_ref}: {remote.stderr.strip()}")
    return workdir


def _commit_and_push(
    workdir: Path,
    saved_bugs_file: str,
    user: User,
    push: bool,
    env: dict[str, str],
) -> tuple[str, bool]:
    """Commit only the new saved-bug list, then push all local commits when requested."""
    branch = _git(workdir, "symbolic-ref", "--short", "HEAD", env=env).stdout.strip()
    _git(workdir, "add", "--", saved_bugs_file, env=env)
    changed = _git(
        workdir, "diff", "--cached", "--quiet", "--", saved_bugs_file, env=env, check=False
    )
    if changed.returncode not in (0, 1):
        raise RuntimeError(f"Git diff failed: {changed.stderr.strip()}")

    commit_hash = ""
    if changed.returncode == 1:
        _git(
            workdir,
            "-c",
            f"user.name={user.get_full_name() or user.username}",
            "-c",
            f"user.email={user.email or f'{user.username}@localhost'}",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "-m",
            f"Update {saved_bugs_file}",
            "--",
            saved_bugs_file,
            env=env,
        )
        commit_hash = _git(workdir, "rev-parse", "HEAD", env=env).stdout.strip()

    if push:
        # Push even when this run had nothing new: earlier runs without a key
        # may have left local commits waiting to be published.
        _git(workdir, "push", "--set-upstream", "origin", branch, env=env)
    return commit_hash, push


def _store_report(report: HousekeepingReport) -> None:
    """Publish a report even when its associated Git update failed."""
    with transaction.atomic():
        HousekeepingReport.objects.all().delete()
        report.save()
    PageMetadata.touch(PAGE_SLUG)


@task()
def refresh_bug_housekeeping(username: str, team: str | None = None) -> None:
    """Replace the page with ``startriage todo --html`` and commit its saved-bug list.

    The default startriage team is used unless *team* names another configured
    team. The refreshing user's SSH key is used for Git fetch, clone and push.
    Without a key, the saved-bug list is still committed to the local checkout.
    """
    DBTaskResult.objects.filter(
        task_path=refresh_bug_housekeeping.module_path,
        status="READY",
        run_after__lte=timezone.now(),
    ).delete()

    user = User.objects.get(username=username)
    tokens = UserTokens.objects.filter(user=user).first()
    if tokens is None or not tokens.lp_token:
        raise ObjectDoesNotExist(f"No Launchpad token configured for user '{username}'.")
    housekeeping = HousekeepingSettings.objects.first()
    if housekeeping is None:
        raise ObjectDoesNotExist(
            "Configure the saved-bugs Git repository in Bug Housekeeping settings first."
        )

    teams = list(StartriageTeam.objects.all())
    default_team = next((item.name for item in teams if item.is_default), None)
    config = build_config(
        {item.name: item.to_team_config() for item in teams},
        default_team=default_team,
        github_token=tokens.github_token,
    )
    opts = build_filter(
        config,
        team=team,
        source_filter={"launchpad", "github"},
        flag_recent=6,
    )

    report_date = date.today()
    saved_bugs_file = f"todo-{report_date.isoformat()}.yaml"
    filename = f"todo-{report_date.isoformat()}.html"
    with _git_environment(tokens.ssh_private_key) as env:
        workdir = _prepare_repository(housekeeping, env)
        with tempfile.TemporaryDirectory(prefix="pinot-noir-housekeeping-") as directory:
            html_path = Path(directory) / filename
            persistor = BugPersistor(
                SaveConfig(
                    savebugs_dir=workdir,
                    override_save=None,
                    override_compare=None,
                    no_save=False,
                )
            )
            output = OutputConfig(
                fmt=OutputFormat.JSON,
                out=io.StringIO(),
                open_in_browser=False,
                terminal_links=False,
                html_path=html_path,
                bug_persistor=persistor,
            )
            with _launchpad_credentials(tokens.lp_token):
                results = asyncio.run(startriage_todo(config, opts, output))
            html = html_path.read_text(encoding="utf-8")

        failed = sorted(name for name, result in results.items() if result.error is not None)
        if not results or len(failed) == len(results):
            raise RuntimeError(
                f"All startriage sources failed: {', '.join(failed) or 'no sources returned'}"
            )
        report = HousekeepingReport(
            team=opts.team,
            html=html,
            filename=filename,
            saved_bugs_file=saved_bugs_file,
            failed_sources=failed,
        )
        try:
            report.commit_hash, report.pushed = _commit_and_push(
                workdir,
                saved_bugs_file,
                user,
                bool(tokens.ssh_private_key),
                env,
            )
        except Exception as exc:
            # The task must still fail so the worker reports the Git problem,
            # but a signing/commit/push failure must not hide the useful HTML.
            report.git_error = str(exc)
            _store_report(report)
            raise

    _store_report(report)
