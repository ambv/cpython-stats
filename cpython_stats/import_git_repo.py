# © Copyright 2021 Łukasz Langa.  Licensed under Apache License, Version 2.0.

from __future__ import annotations
from typing import *

from collections import Counter
import datetime
from email.utils import parseaddr
from pathlib import Path
import re
import shelve

from dulwich.repo import Repo
from dulwich.objects import Commit
from dulwich import porcelain as git
from github import Github
from rich.progress import Progress, TextColumn, BarColumn, TimeRemainingColumn

from . import models as m
from . import console
from . import env
from . import gh_utils


print = console.print


def main() -> None:
    with shelve.open(env.STATS_SHELVE_PATH, protocol=4) as db:
        update_db(db)


def update_db(db: shelve.Shelf) -> None:
    git_repo_path = Path(env.GIT_REPO_LOCATION)
    if not git_repo_path.is_dir():
        print("Cloning repo", end="... ")
        git.clone("git://github.com/python/cpython", git_repo_path)
        print("done!")

    repo = Repo(git_repo_path)
    print("Fetching all heads", end="... ")
    result = git.fetch(repo)
    print("done!")

    branches = {}
    for branch in env.GIT_REPO_BRANCHES.split(","):
        branch = branch.strip()
        if ref := result.refs.get(f"refs/tags/{branch}".encode("utf8")):
            branches[branch] = ref
        elif ref := result.refs.get(f"refs/heads/{branch}".encode("utf8")):
            branches[branch] = ref
        else:
            print(f"[bold yellow]warning:[/bold yellow] branch {branch!r} not found")

    python_using_github_since = datetime.datetime(2017, 2, 10)
    commits = list(
        entry.commit
        for entry in repo.get_walker(
            include=branches.values(), since=python_using_github_since.timestamp()
        )
    )

    gh = Github(env.GITHUB_API_TOKEN)
    seen_pr_ids: set[m.PR_ID] = set()
    for commit_sha1, pr_id, gh_user in gen_github_users_from_commits(
        commits, gh=gh, db=db
    ):
        if pr_id:
            pk = f"GH-{pr_id}"
            try:
                change: m.Change = db[pk]
            except KeyError:
                if pr_id not in seen_pr_ids:
                    print(
                        f"[yellow bold]warning:[/yellow bold]"
                        f" (in {commit_sha1}) unknown PR #{pr_id}",
                    )
                continue
            finally:
                seen_pr_ids.add(pr_id)

            if gh_user not in change.contributors:
                change.contributors.add(gh_user)
                db[pk] = change


def gen_github_users_from_commits(
    commits: list[Commit], *, gh: Github, db: shelve.Shelf
) -> Iterator[tuple[m.SHA1, m.PR_ID, m.User]]:
    sha1_to_pr = gh_utils.build_commit_id_to_pr_index(db)

    unknown_emails: Counter[str] = Counter()
    unknown_email_prs: dict[str, dict[m.PR_ID, m.SHA1]] = {}
    multiple_accounts: Counter[str] = Counter()
    total = len(commits)
    print(f"{total} commits to parse e-mails...")
    with Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[green]{task.completed}/[bold]{task.total}"),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Import in progress...", total=total)
        for commit in commits:
            commit_sha1 = m.SHA1(commit.id.decode("ascii"))
            message_lines = commit.message.decode("utf8", errors="ignore").splitlines()
            progress.update(task, description="%-50s" % message_lines[0][:50])
            email = get_commit_author_email(commit)
            pr_id = sha1_to_pr.get(commit_sha1, m.UnknownPR)
            try:
                gh_user = gh_utils.find_user(email, gh=gh, progress=progress, task=task)
            except LookupError:
                if pr_id:
                    unknown_email_prs.setdefault(email, {})[pr_id] = commit_sha1
                unknown_emails[email] += 1
            except ValueError as ve:
                if email not in multiple_accounts:
                    print(
                        f"[bold yellow]warning:[/bold yellow] (in {commit_sha1}) {ve}"
                    )
                multiple_accounts[email] += 1
            else:
                yield commit_sha1, pr_id, gh_user

            for email in get_commit_co_author_emails(message_lines):
                try:
                    gh_user = gh_utils.find_user(
                        email, gh=gh, progress=progress, task=task
                    )
                except LookupError:
                    # for co-authors we won't use `update_unknown_emails_from_prs` so
                    # we don't add those to `unknown_email_prs`
                    unknown_emails[email] += 1
                except ValueError as ve:
                    if email not in multiple_accounts:
                        print(f"[bold yellow]warning:[/bold yellow] ({commit.id}) {ve}")
                    multiple_accounts[email] += 1
                else:
                    yield commit_sha1, pr_id, gh_user

            progress.advance(task)

    yield from resolve_unknown_emails_from_prs(
        prs_per_email=unknown_email_prs, email_commit_counts=unknown_emails, gh=gh
    )


def resolve_unknown_emails_from_prs(
    *,
    prs_per_email: dict[str, dict[m.PR_ID, m.SHA1]],
    email_commit_counts: Counter[str],
    gh: Github,
) -> Iterator[tuple[m.SHA1, m.PR_ID, m.User]]:
    cpython = gh.get_repo("python/cpython")
    total = len(email_commit_counts)
    if total:
        print(f"{total} unknown e-mails to recheck against PRs...")
    with Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[green]{task.completed}/[bold]{task.total}"),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Check in progress...", total=total)
        for email, count in email_commit_counts.most_common():
            if email in prs_per_email:
                prs = prs_per_email[email]
                progress.update(task, description=f"{email} ({len(prs)} PRs)")
                try:
                    gh_user = gh_utils.most_common_user_in_prs(
                        email,
                        set(prs),
                        gh=gh,
                        repo=cpython,
                        progress=progress,
                        task=task,
                    )
                except LookupError:
                    print(
                        f"[bold yellow]warning:[/bold yellow] couldn't find Github user"
                        f" for e-mail {email} (seen in {count} commits)"
                    )
                else:
                    print(
                        f"{email} most likely belongs to {gh_user}"
                        f" (checked {len(prs)} PRs)"
                    )
                    for pr_id, commit_sha1 in prs.items():
                        yield commit_sha1, pr_id, gh_user
            else:
                print(
                    f"[bold yellow]warning:[/bold yellow] couldn't find Github user"
                    f" for e-mail {email} (seen in {count} commits)"
                )
            progress.advance(task)


def get_commit_author_email(commit: Commit) -> str:
    author = commit.author.decode("utf8")
    author = author.replace(", ", " ").replace(",", " ")
    name, email = parseaddr("From: " + author)
    return email


# Co-authored-by: Priyank <5903604+cpriyank@users.noreply.github.com>
# Co-authored-by: blurb-it[bot] <43283697+blurb-it[bot]@users.noreply.github.com>
CO_AUTHORED_BY_RE = re.compile(
    r"^\s*(Co-authored-by:|Authored-by:) ([^<]+ )?<(?P<email>.+)>$", re.IGNORECASE
)


def get_commit_co_author_emails(lines: Iterable[str]) -> Iterator[str]:
    for line in lines:
        if match := CO_AUTHORED_BY_RE.match(line):
            yield match.group("email")


def _get_commit_pr_id(line: str) -> m.PR_ID:
    raise NotImplementedError(
        "This is unreliable. Use `gh_utils.build_commit_id_to_pr_index()` instead."
    )

    GH_PR_ID_RE = re.compile(r"^.*\((GH-|#)(?P<pr_id>\d+)\)$", re.IGNORECASE)
    if match := GH_PR_ID_RE.match(line):
        return m.PR_ID(int(match.group("pr_id")))

    return m.UnknownPR


if __name__ == "__main__":
    main()
