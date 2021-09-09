# © Copyright 2021 Łukasz Langa.  Licensed under Apache License, Version 2.0.

from __future__ import annotations
from typing import *

import datetime
import shelve
import time

from dateutil.parser import parse as dt_parse
from github import Github
from github.NamedUser import NamedUser
from github.PullRequest import PullRequest
from github.GithubException import IncompletableObject
from rich.progress import Progress, TaskID, TextColumn, BarColumn, TimeRemainingColumn

from . import models as m
from . import console
from . import env


print = console.print


def main() -> None:
    with shelve.open(env.STATS_SHELVE_PATH, protocol=4) as db:
        update_db(db)


def update_db(db: shelve.Shelf) -> None:
    gh = Github(env.GITHUB_API_TOKEN)
    cpython = gh.get_repo("python/cpython")
    prs = cpython.get_pulls(state="all")
    total = prs.totalCount
    with Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[green]{task.completed}/[bold]{task.total}"),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Import in progress...", total=total)
        for pr in prs:
            nice(gh, progress, task)
            pr_id = f"GH-{pr.number}"
            old: m.Change | None
            try:
                old = db[pr_id]
            except KeyError:
                old = None

            try:
                if old:
                    if is_up_to_date(old, pr):
                        progress.update(task, description=f"Skipping {pr_id}")
                    else:
                        progress.update(
                            task, description=f"[yellow]Updating {pr_id}[/yellow]"
                        )
                        update_in_place(old, pr)
                        db[pr_id] = old
                else:
                    progress.update(
                        task, description=f"[green]Importing {pr_id}[/green]"
                    )
                    db[pr_id] = new_change_from(pr)
            except Exception as exc:
                print(f"[bold red]warning[/bold red]: skipped {pr_id} due to error")
                print(exc)
            progress.advance(task)


def is_up_to_date(old: m.Change, pr: PullRequest) -> bool:
    if pr.updated_at:
        return old.updated_at == pr.updated_at

    elif pr.last_modified is not None:
        last_mod = dt_parse(pr.last_modified, ignoretz=True)
        if old.merged_at and last_mod == old.merged_at:
            return True

        if old.closed_at and last_mod == old.closed_at:
            return True

    else:
        raise ValueError(f"{old.pr_id} doesn't have [bold]last_modified[/bold] set")

    return False


def update_in_place(old: m.Change, pr: PullRequest) -> None:
    current = new_change_from(pr)
    fields: list[str]
    fields = list(m.Change.__dataclass_fields__)  # type: ignore
    for field in fields:
        current_value = getattr(current, field)
        old_value = getattr(old, field, None)
        if current_value or not old_value:
            # Only update if current value is set
            # or when the old one wasn't anyway.
            setattr(old, field, current_value)


def new_change_from(pr: PullRequest) -> m.Change:
    files: list[m.File] = [
        m.File(
            name=file.filename,
            additions=file.additions,
            deletions=file.deletions,
            changes=file.changes,
        )
        for file in pr.get_files()
    ]

    contributors: set[m.User] = set()
    if user := maybe_user(pr.user):
        contributors.add(user)
    if user := maybe_user(pr.merged_by):
        contributors.add(user)
    for commit in pr.get_commits():
        if user := maybe_user(commit.author):
            contributors.add(user)
        if user := maybe_user(commit.committer):
            contributors.add(user)

    comments: list[m.Comment] = [
        m.Comment(
            author=maybe_user(comment.user),
            text=comment.body,
        )
        for comment in pr.get_issue_comments()
        if maybe_user(comment.user)
    ]
    for review in pr.get_reviews():
        if not (author := maybe_user(review.user)):
            continue
        if review.body:
            comments.append(m.Comment(author=author, text=review.body))
        elif review.state != "COMMENTED":
            comments.append(m.Comment(author=author, text=review.state))
    for comment in pr.get_review_comments():
        if not (author := maybe_user(comment.user)):
            continue
        comments.append(m.Comment(author=author, text=comment.body))

    labels: set[m.Label] = {m.Label(label.name) for label in pr.get_labels()}

    return m.Change(
        pr_id=m.PR_ID(pr.number),
        title=pr.title,
        description=pr.body,
        files=files,
        branch=m.Branch(pr.base.ref),
        contributors=contributors,
        opened_at=pr.created_at,
        merged_at=pr.merged_at,
        closed_at=pr.closed_at,
        updated_at=pr.updated_at,
        comments=comments,
        labels=labels,
    )


def maybe_user(nu: NamedUser | None) -> m.User:
    if nu is None:
        return m.NoUser

    try:
        return m.User(nu.login)
    except IncompletableObject:
        return m.NoUser


def nice(gh: Github, progress: Progress, task: TaskID) -> None:
    while True:
        while True:
            try:
                rl = gh.get_rate_limit()
            except Exception:
                time.sleep(1)
            else:
                break
        remaining = rl.core.remaining
        limit = rl.core.limit
        reset_ts = rl.core.reset
        if remaining / limit > 0.25:
            return

        if remaining > 50:
            time.sleep(1)
            return

        delta = (reset_ts - datetime.datetime.utcnow()).seconds
        for i in range(max(delta, 30)):
            progress.update(
                task,
                description=(
                    f"sleeping for [bold blue]{delta-i}[/bold blue] seconds"
                    f" ([red]{remaining}/[bold]{limit}[/bold][/red] requests remaining)"
                ),
            )
            time.sleep(1)


if __name__ == "__main__":
    main()
