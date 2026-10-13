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

# --- Alert thresholds (E2) ----------------------------------------------------
# Every value can be overridden by env. A threshold is "breached" when the
# measured value goes in the alarming direction defined in engine.ALERT_RULES.

def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


# Plan Completion Rate below this is flagged as abandoned planning.
ALERT_PCR_MIN = _env_float("ALERT_PCR_MIN", 50.0)
# Minimum number of checklist tasks before the PCR alert is meaningful.
ALERT_PCR_MIN_TASKS = _env_int("ALERT_PCR_MIN_TASKS", 10)
# A single agent holding more than this share of total cost is a routing smell.
ALERT_COST_CONCENTRATION_MAX = _env_float("ALERT_COST_CONCENTRATION_MAX", 90.0)
# Per-agent breach rate above this is flagged (needs at least the invocations below).
ALERT_BREACH_RATE_MAX = _env_float("ALERT_BREACH_RATE_MAX", 50.0)
ALERT_BREACH_MIN_INVOCATIONS = _env_int("ALERT_BREACH_MIN_INVOCATIONS", 3)
# Per-agent tool error rate above this is flagged.
ALERT_ERROR_RATE_MAX = _env_float("ALERT_ERROR_RATE_MAX", 15.0)
# Practical Actionability Index below this means ideation without delivery.
ALERT_PAI_MIN = _env_float("ALERT_PAI_MIN", 0.20)
# A session dispatching at least this many subagents is considered over-delegation.
ALERT_FANOUT_MAX = _env_int("ALERT_FANOUT_MAX", 5)
# Cost floor (USD) before cost-based alerts are worth reporting.
ALERT_COST_FLOOR = _env_float("ALERT_COST_FLOOR", 0.01)
