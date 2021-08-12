# © Copyright 2021 Łukasz Langa.  Licensed under Apache License, Version 2.0.

from __future__ import annotations
from typing import *

import datetime
import os
import shelve
import time

from dotenv import load_dotenv
from github import Github
from github.NamedUser import NamedUser
from github.PullRequest import PullRequest
from github.GithubException import IncompletableObject
from rich.progress import Progress, TaskID, TextColumn, BarColumn, TimeRemainingColumn

from . import models as m
from . import console


print = console.print


load_dotenv()
GITHUB_API_TOKEN = os.environ["GITHUB_API_TOKEN"]
STATS_SHELVE_PATH = os.environ["STATS_SHELVE_PATH"]


def main() -> None:
    with shelve.open(STATS_SHELVE_PATH, protocol=4, writeback=True) as db:
        update_db(db)


def update_db(db: shelve.Shelf) -> None:
    gh = Github(GITHUB_API_TOKEN)
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
            if old:
                progress.update(task, description=f"Skipping {pr_id}")
                # print(f"Updating {pr_id}")
                # update_in_place(old, pr)
            else:
                progress.update(task, description=f"Importing {pr_id}")
                db[pr_id] = new_change_from(pr)
            progress.advance(task)


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

    labels: set[m.Label] = {
        m.Label(label.name)
        for label in pr.get_labels()
    }

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
        rl = gh.get_rate_limit()
        remaining = rl.core.remaining
        limit = rl.core.limit
        reset_ts = rl.core.reset
        if remaining / limit > 0.5:
            return

        if remaining > 100:
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
