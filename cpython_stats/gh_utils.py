# © Copyright 2021 Łukasz Langa.  Licensed under Apache License, Version 2.0.

from __future__ import annotations
from typing import *

import datetime
import time

from github import Github
from rich.progress import Progress, TaskID


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

