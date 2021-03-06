# © Copyright 2021 Łukasz Langa.  Licensed under Apache License, Version 2.0.

from __future__ import annotations as _
from typing import *

from dataclasses import asdict
import shelve

from rich import progress
from sqlite_utils import Database
from sqlite_utils.db import Table

from . import env
from . import gh_utils
from . import models


def main() -> None:
    core_devs = gh_utils.get_core_devs_from_cache()
    with shelve.open(env.STATS_SHELVE_PATH, protocol=4) as db:
        convert_db(db, core_devs)


def convert_db(db: shelve.Shelf, core_devs: set[models.User]) -> None:
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
        authors = change.pop("authors")
        merged_by = change.pop("merged_by")
        comments = change.pop("comments")
        labels = change.pop("labels")

        if not item.pr_id:
            raise NotImplementedError("Non-PR changes not implemented yet.")
        else:
            change["id"] = f"GH-{item.pr_id}"

        contributors_data = [
            {
                "name": contributor,
                "is_pr_author": contributor in authors,
                "did_merge_pr": contributor and contributor == merged_by,
                "is_core_dev": contributor in core_devs,
            }
            for contributor in sorted(contributors)
        ]

        changes_table.insert(
            change,
            pk="id",
            column_order=("id", "branch", "title"),
        )
        insert_foreign_data(files_table, change["id"], files)
        insert_foreign_data(
            contributors_table,
            change["id"],
            contributors_data,
        )
        insert_foreign_data(comments_table, change["id"], comments)
        insert_foreign_data(
            labels_table,
            change["id"],
            [{"label": label} for label in sorted(labels)],
        )

    sqlite.index_foreign_keys()
    print("done.")


def insert_foreign_data(table: Table, id: int, data: Sequence[Dict[str, Any]]) -> None:
    fks = [
        ("change_id", "changes", "id"),
    ]
    for item in data:
        item["id"] = (table.last_pk or 0) + 1
        item["change_id"] = id
        table.insert(item, pk="id", foreign_keys=fks)


if __name__ == "__main__":
    main()
