# © Copyright 2021 Łukasz Langa.  Licensed under Apache License, Version 2.0.

from __future__ import annotations
from typing import *

import os

from dotenv import load_dotenv

load_dotenv()
GITHUB_API_TOKEN = os.environ["GITHUB_API_TOKEN"]
STATS_SHELVE_PATH = os.environ["STATS_SHELVE_PATH"]
