# © Copyright 2021 Łukasz Langa.  Licensed under Apache License, Version 2.0.

from __future__ import annotations
from typing import *

from collections import Counter, defaultdict
from functools import lru_cache
from pathlib import Path
import shelve

from dulwich import porcelain as git
from rich import progress

from . import console
from . import env
from . import models as m


print = console.print


FileName = str


directory_depth = defaultdict(lambda: 2)
directory_depth.update(
    {
        "Parser": 1,
        "PCbuild": 1,
        "PC": 1,
        "Mac": 1,
        "Grammar": 1,
        "Doc/library": 3,
        "Doc/using": 3,
        "Doc/whatsnew": 3,
        "Include/cpython": 3,
        "Include/internal": 3,
        "Lib/test": 3,
        "Lib/xml/": 3,
        ".azure-pipelines": 1,
        ".github": 1,
        ".vsts": 1,
    }
)

SKIP_CONTRIBUTORS = {
    "miss-islington",
    "web-flow",
    "mariatta-bot",
    "blurb-it",
    "blurb-it[bot]",
}

SKIP_CATEGORIES = {
    "Python.framework",
    "TODO",
    "f.py",
    "j.py",
    "t.py",
    "x.py",
    "Misc/ACKS",
    "Misc/HISTORY",
    "Misc/NEWS",
    "Misc/NEWS.d",
    "LICENSE",
    "README.rst",
    "Tools/README",
}


def main() -> None:
    with shelve.open(env.STATS_SHELVE_PATH, protocol=4) as db:
        analyze_db(db)


def analyze_db(db: shelve.Shelf) -> None:
    pk: str

    categories_files: dict[str, set[FileName]] = {}
    categories_contrib: dict[str, Counter[m.User]] = {}

    print("Categorizing file paths...")
    for pk, item in progress.track(db.items(), transient=True):
        assert isinstance(item, m.Change)

        if item.merged_at is None:
            continue

        for file in item.files:
            cat = category_for_file(file.name)
            if not cat:
                continue

            categories_files.setdefault(cat, set()).add(file.name)
            for contrib in item.contributors:
                if contrib in SKIP_CONTRIBUTORS:
                    continue

                if contrib.startswith("blurb"):
                    breakpoint()
                categories_contrib.setdefault(cat, Counter())[contrib] += 1

    normalize_categories(categories_contrib)
    git_repo_path = Path(env.GIT_REPO_LOCATION)
    if not git_repo_path.is_dir():
        print("Cloning repo", end="... ")
        git.clone("git://github.com/python/cpython", git_repo_path)
        print("done!")

    print("Top 5 contributors per category:")
    shown_count = 0
    for cat in sorted(categories_contrib):
        glob_cat = cat
        if not glob_cat.endswith((".c", ".h", ".py", ".rst")):
            glob_cat += "*"
        if not len(list(git_repo_path.glob(glob_cat))):
            continue  # skip non-existing files
            print(
                f"[bold red]warning:[/bold red] category {cat} points"
                f" at a non-existing path"
            )

        contributors = categories_contrib[cat]
        change_count = sum(count for _, count in contributors.most_common())
        if change_count < 10:
            continue

        limit = 5 if change_count > 30 else None

        message = ", ".join(
            f"{user} ({count})"
            for user, count in contributors.most_common(limit)
            if count > 1
        )
        if not message:
            message = "[red]NOBODY[/red]"

        print(f"[bold]{cat}[/bold]: " + message)
        shown_count += 1

    print(f"{shown_count} categories.")


@lru_cache(maxsize=None)
def category_for_file(file: str) -> str:
    depth = 0
    for pre, depth in directory_depth.items():
        if file.startswith(pre):
            break
    else:
        depth = directory_depth[file]

    result = "/".join(file.split("/")[:depth])
    if result in SKIP_CATEGORIES:
        return ""

    if result.startswith("Lib/test") and not result.startswith(
        ("Lib/test/test_", "Lib/test/_test")
    ):
        return ""

    return result


def normalize_categories(categories_contrib: dict[str, Counter[m.User]]) -> None:
    doclib = "Doc/library/"
    internal_module = "Modules/_"
    libtest = "Lib/test/test_"
    libundertest = "Lib/test/_test_"

    print("Normalizing categories")
    for old_category in progress.track(list(categories_contrib)):
        if old_category.startswith(internal_module):
            new_category = old_category[len(internal_module) :]
            if new_category.endswith((".c", ".h")):
                new_category = new_category[: -len(".c")]
            if new_category.endswith("module"):
                new_category = new_category[: -len("module")]

            if f"Lib/{new_category}" in categories_contrib:
                new_category = f"Lib/{new_category}"
            elif f"Lib/{new_category}.py" in categories_contrib:
                new_category = f"Lib/{new_category}.py"
            else:
                continue

            for user, count in categories_contrib[old_category].items():
                categories_contrib[new_category][user] += count
            del categories_contrib[old_category]

        if old_category.startswith(doclib):
            new_category = old_category[len(doclib) :]
            if "xml" in new_category:
                new_category = new_category[: -len(".rst")]
                new_category = "/".join(new_category.split(".")[:2])
            else:
                new_category = new_category.split(".", 1)[0]
            if "asyncio" in new_category:
                new_category = "asyncio"

            if f"Lib/{new_category}" in categories_contrib:
                new_category = f"Lib/{new_category}"
            elif f"Lib/{new_category}.py" in categories_contrib:
                new_category = f"Lib/{new_category}.py"
            elif f"Modules/{new_category}module.c" in categories_contrib:
                new_category = f"Modules/{new_category}module.c"
            else:
                continue

            for user, count in categories_contrib[old_category].items():
                categories_contrib[new_category][user] += count
            del categories_contrib[old_category]

        if old_category.startswith((libundertest, libtest)):
            if old_category.startswith(libundertest):
                new_category = old_category[len(libundertest) :]
            else:
                new_category = old_category[len(libtest) :]
            if new_category.endswith(".py"):
                new_category = new_category[: -len(".py")]

            if f"Lib/{new_category}" in categories_contrib:
                new_category = f"Lib/{new_category}"
            elif f"Lib/{new_category}.py" in categories_contrib:
                new_category = f"Lib/{new_category}.py"
            elif f"Modules/{new_category}module.c" in categories_contrib:
                new_category = f"Modules/{new_category}module.c"
            else:
                continue

            for user, count in categories_contrib[old_category].items():
                categories_contrib[new_category][user] += count
            del categories_contrib[old_category]


if __name__ == "__main__":
    main()
