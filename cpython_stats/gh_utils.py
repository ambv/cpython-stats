# © Copyright 2021 Łukasz Langa.  Licensed under Apache License, Version 2.0.

from __future__ import annotations
from typing import *

import datetime
import sqlite3
import time

from github import Github, GithubException
from rich.progress import Progress, TaskID
from sqlite_utils import Database

from . import env


RateLimitDomain = Literal["core", "search", "graphql"]


def find_user(email: str, /, *, gh: Github, progress: Progress, task: TaskID) -> str:
    """Return a Github username from `email`."""

    try:
        return maybe_github_ui_email(email)
    except ValueError:
        pass

    if "@" not in email:
        raise ValueError(f"Invalid email passed: {email}")

    sqlite = Database(env.CACHE_SQLITE_PATH)
    try:
        result = _get_cached_gh_user_for_email(sqlite, email)
    except LookupError:
        nice(gh, "search", progress, task, precise=True)
        results = []
        for named_user in gh.search_users(f"{email} in:email"):
            nice(gh, "core", progress, task, precise=True)
            results.append(named_user.login)
        if len(results) > 1:
            all_names = ", ".join(results)
            raise ValueError(f"Multiple users returned for {email!r}: {all_names}")
        elif len(results) == 1:
            result = results[0]
        table = sqlite["email_to_gh_user"]
        table.insert({"email": email, "gh_user": result})
        table.create_index(["email"], unique=True, if_not_exists=True)

    if result is None:
        raise LookupError(email)

    return result


def maybe_github_ui_email(email: str) -> str:
    # example: 31488909+miss-islington@users.noreply.github.com
    domain = "@users.noreply.github.com"
    if email.endswith(domain):
        user = email[: -len(domain)]
        if "+" in user:
            user_id, username = user.split("+", 1)
            try:
                int(user_id)
            except ValueError:
                pass
            else:
                return username
        else:
            return user

    raise ValueError("e-mail address doesn't match")


def _get_cached_gh_user_for_email(sqlite: Database, email: str) -> str | None:
    """Return cached Github username.

    Can be None if the Github API doesn't recognize the email.
    If nothing is cached, raise LookupError.
    """
    try:
        cache_rows = list(
            sqlite.query(
                "SELECT gh_user FROM email_to_gh_user WHERE email = :email",
                {"email": email},
            )
        )
    except sqlite3.OperationalError:
        # cache not created yet
        cache_rows = []

    for row in cache_rows:
        return row["gh_user"]

    raise LookupError(email)


def nice(
    gh: Github,
    domain: RateLimitDomain,
    progress: Progress,
    task: TaskID,
    *,
    precise: bool = False,
) -> None:
    while True:
        while True:
            try:
                rl = gh.get_rate_limit()
            except Exception:
                time.sleep(1)
            else:
                break

        rl_domain = getattr(rl, domain)
        remaining = rl_domain.remaining
        limit = rl_domain.limit
        reset_ts = rl_domain.reset

        if precise and remaining > 1:
            return

        if remaining / limit > 0.25:
            return

        if remaining > 50:
            time.sleep(1)
            return

        delta = reset_ts - datetime.datetime.utcnow()
        if delta.days < 0:
            time.sleep(1)
            return

        delta_sec = delta.seconds + 3
        for i in range(delta_sec):
            progress.update(
                task,
                description=(
                    f"sleeping for [bold blue]{delta_sec-i}[/bold blue] seconds"
                    f" ([red]{remaining}/[bold]{limit}[/bold][/red] requests remaining)"
                ),
            )
            time.sleep(1)
