# © Copyright 2021 Łukasz Langa.  Licensed under Apache License, Version 2.0.

from __future__ import annotations
from typing import *

from pathlib import Path
import sys

from sqlite_utils import Database
import tomli

from . import console
from . import env
from . import gh_utils


print = console.print


def main() -> int:
    toml_path = Path("python-core.toml")
    if not toml_path.is_file():
        print(f"[bold red]error:[/bold red] {toml_path} doesn't exist")
        return 1

    with toml_path.open("rb") as toml_file:
        core_devs = tomli.load(toml_file)

    sqlite = Database(env.CACHE_SQLITE_PATH)

    for core_dev in core_devs["core-dev"]:
        try:
            name = core_dev["name"]
            email = core_dev["voting_address"]
            gh_user = core_dev["github"]
        except KeyError:
            continue
        print(f"Updating {name}")
        update_db(sqlite, email, gh_user)

    return 0


def update_db(sqlite: Database, email: str, gh_user: str) -> None:
    if not email or not gh_user:
        return

    try:
        cached_user = gh_utils._get_cached_gh_user_for_email(sqlite, email)
    except LookupError:
        pass
    else:
        if cached_user is not None:
            if gh_user != cached_user:
                print(
                    f"[bold yellow]warning:[bold yellow] cached Github user for e-mail"
                    f" {email} is {cached_user}, expected {gh_user}"
                )
            return

        sqlite.execute(
            "DELETE FROM email_to_gh_user WHERE email = :email", {"email": email}
        )

    table = sqlite["email_to_gh_user"]
    table.insert({"email": email, "gh_user": gh_user})


if __name__ == "__main__":
    sys.exit(main())
