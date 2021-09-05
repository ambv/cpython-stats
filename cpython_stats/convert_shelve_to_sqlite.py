# © Copyright 2021 Łukasz Langa.  Licensed under Apache License, Version 2.0.

from __future__ import annotations as _
from typing import *

from dataclasses import asdict
import shelve

from rich import progress
from sqlite_utils import Database
from sqlite_utils.db import Table

from . import env
from . import models


def main() -> None:
    with shelve.open(env.STATS_SHELVE_PATH, protocol=4) as db:
        convert_db(db)


def convert_db(db: shelve.Shelf) -> None:
    sqlite = Database(env.STATS_SQLITE_PATH)
    changes_table = sqlite["changes"]
    files_table = sqlite["files"]
    contributors_table = sqlite["contributors"]
    comments_table = sqlite["comments"]
    labels_table = sqlite["labels"]
    for pk, item in progress.track(db.items(), transient=True):
        assert isinstance(item, models.Change)
        change = asdict(item)
        files = change.pop("files")
        contributors = change.pop("contributors")
        comments = change.pop("comments")
        labels = change.pop("labels")

        if not item.pr_id:
            raise NotImplementedError("Non-PR changes not implemented yet.")
        else:
            change["kind"] = "GH"
            change["id"] = item.pr_id

        changes_table.insert(
            change,
            pk=("kind", "id"),
            column_order=("kind", "id", "branch", "title"),
        )
        insert_foreign_data(files_table, change["kind"], change["id"], files)
        insert_foreign_data(
            contributors_table,
            change["kind"],
            change["id"],
            [{"name": contributor} for contributor in sorted(contributors)],
        )
        insert_foreign_data(comments_table, change["kind"], change["id"], comments)
        insert_foreign_data(
            labels_table,
            change["kind"],
            change["id"],
            [{"label": label} for label in sorted(labels)],
        )

    print("done.")


def insert_foreign_data(
    table: Table, kind: str, id: int, data: Sequence[Dict[str, Any]]
) -> None:
    fks = [
        ("change_kind", "changes", "kind"),
        ("change_id", "changes", "id"),
    ]
    for item in data:
        item["id"] = (table.last_pk or 0) + 1
        item["change_kind"] = kind
        item["change_id"] = id
        table.insert(item, pk="id", foreign_keys=fks)


if __name__ == "__main__":
    main()
