# © Copyright 2021 Łukasz Langa.  Licensed under Apache License, Version 2.0.

from __future__ import annotations
from typing import *

from dataclasses import dataclass, field
from datetime import datetime


PR_ID = NewType("PR_ID", int)
SHA1 = NewType("SHA1", str)
Label = NewType("Label", str)
User = NewType("User", str)  # a GitHub username, not an e-mail
Branch = NewType("Branch", str)
ChangeState = Literal["open", "merged", "closed"]  # closed == not merged
NotMerged = SHA1("")
UnknownPR = PR_ID(0)
NoUser = User("")


@dataclass
class File:
    name: str
    additions: int = 0
    changes: int = 0
    deletions: int = 0


@dataclass
class Comment:
    author: User
    text: str


@dataclass
class Change:
    title: str
    description: str
    files: list[File]
    branch: Branch
    contributors: set[User]  # only: PR authors, commit authors, commit committers

    opened_at: datetime | None
    merged_at: datetime | None
    closed_at: datetime | None
    updated_at: datetime | None

    commit_id: SHA1 = NotMerged
    pr_id: PR_ID = UnknownPR

    comments: list[Comment] = field(default_factory=list)  # including reviews
    labels: set[Label] = field(default_factory=set)

    @property
    def state(self) -> ChangeState:
        if self.merged_at is not None:
            return "merged"
        if self.closed_at is not None:
            return "closed"
        if self.opened_at is not None:
            return "open"
        return "closed"
