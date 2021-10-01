# © Copyright 2021 Łukasz Langa.  Licensed under Apache License, Version 2.0.

from __future__ import annotations
from typing import *

import os

from dotenv import load_dotenv

load_dotenv()
GITHUB_API_TOKEN = os.environ["GITHUB_API_TOKEN"]
GIT_REPO_LOCATION = os.environ.get("GIT_REPO_LOCATION", "cpython")
STATS_SHELVE_PATH = os.environ.get("STATS_SHELVE_PATH", "shelve.db")
STATS_SQLITE_PATH = os.environ.get("STATS_SQLITE_PATH", "db.sqlite")
CACHE_SQLITE_PATH = os.environ.get("CACHE_SQLITE_PATH", "cache.sqlite")
GIT_REPO_BRANCHES = os.environ.get("GIT_REPO_BRANCHES", "main,3.10,3.9,3.8,3.7,3.6,2.7")
