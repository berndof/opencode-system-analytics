"""
Configuration for OpenCode System Analytics.
Supports environment overrides with sensible defaults.
"""

import os
from typing import List

# Database Path
DEFAULT_DB_PATH = os.path.expanduser("~/.local/share/opencode/opencode.db")
OPENCODE_DB_PATH = os.getenv("OPENCODE_DB_PATH", DEFAULT_DB_PATH)

# Plans Directories
DEFAULT_PLANS_DIR = os.path.expanduser("~/.opencode/plans")
env_plans_dirs = os.getenv("PLANS_DIRS")
if env_plans_dirs:
    PLANS_DIRS = [d.strip() for d in env_plans_dirs.split(",") if d.strip()]
else:
    PLANS_DIRS = [DEFAULT_PLANS_DIR]

# Server Config
HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "8765"))

# App Branding & Title
APP_TITLE = "OpenCode System Analytics"
