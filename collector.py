"""
Data collector for OpenCode System Analytics.
Extracts session metrics, tool calls, message stats, and plan checklists from OpenCode DB and workspace plans.
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime
import json
import os
import glob
import re
import sqlite3
from typing import List, Dict, Any, Optional

from .config import OPENCODE_DB_PATH, PLANS_DIRS


def normalize_agent_name(raw_name: Optional[str]) -> str:
    if not raw_name:
        return "unknown"
    name = str(raw_name).strip().lower()
    if name.startswith("@"):
        name = name[1:]
    return name or "unknown"


@dataclass
class ToolCallRecord:
    call_id: str
    tool: str
    status: str
    error: Optional[str] = None
    input_summary: Optional[str] = None
    time_start: Optional[int] = None
    time_end: Optional[int] = None
    target_agent: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SessionRecord:
    id: str
    parent_id: Optional[str]
    title: str
    agent: str
    model: str
    project: str
    cost: float
    tokens_input: int
    tokens_output: int
    tokens_reasoning: int
    tokens_cache_read: int
    tokens_cache_write: int
    time_created: int
    time_updated: int
    duration_seconds: float
    status: str
    step_count: int = 0
    files_modified: int = 0
    tool_calls: List[ToolCallRecord] = field(default_factory=list)
    subagent_calls: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data['tool_calls'] = [t.to_dict() if hasattr(t, 'to_dict') else t for t in self.tool_calls]
        return data


@dataclass
class PlanTaskRecord:
    description: str
    completed: bool


@dataclass
class PlanRecord:
    path: str
    filename: str
    date_str: Optional[str]
    total_tasks: int
    completed_tasks: int
    pending_tasks: int
    completion_rate: float
    tasks: List[PlanTaskRecord] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data['tasks'] = [asdict(t) for t in self.tasks]
        return data


@dataclass
class AnalyticsData:
    sessions: List[SessionRecord]
    plans: List[PlanRecord]
    collected_at: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sessions": [s.to_dict() for s in self.sessions],
            "plans": [p.to_dict() for p in self.plans],
            "collected_at": self.collected_at,
        }


class AnalyticsCollector:
    """Collects session metrics from SQLite DB and plan progress from Markdown files."""

    def __init__(self, db_path: Optional[str] = None, plans_dirs: Optional[List[str]] = None):
        self.db_path = db_path or OPENCODE_DB_PATH
        self.plans_dirs = plans_dirs or PLANS_DIRS

    def connect_db(self) -> Optional[sqlite3.Connection]:
        """Connects to SQLite database in read-only mode with URI fallback."""
        if not os.path.exists(self.db_path):
            return None

        try:
            uri_path = f"file:{self.db_path}?mode=ro"
            conn = sqlite3.connect(uri_path, uri=True)
        except Exception:
            try:
                conn = sqlite3.connect(self.db_path)
            except Exception:
                return None
        
        conn.row_factory = sqlite3.Row
        return conn

    def get_existing_tables(self, conn: sqlite3.Connection) -> List[str]:
        try:
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table';")
            return [row[0] for row in cursor.fetchall()]
        except Exception:
            return []

    def extract_sessions(self, conn: sqlite3.Connection) -> Dict[str, SessionRecord]:
        tables = self.get_existing_tables(conn)
        session_tables = [t for t in ['session_v2', 'session'] if t in tables]

        sessions_by_id: Dict[str, SessionRecord] = {}
        if not session_tables:
            return sessions_by_id

        for table in session_tables:
            try:
                cursor = conn.execute(f"PRAGMA table_info({table})")
                columns = {row['name'] for row in cursor.fetchall()}

                query = f"SELECT * FROM {table}"
                rows = conn.execute(query).fetchall()
            except Exception:
                continue

            for row in rows:
                sid = row['id']
                if sid in sessions_by_id:
                    continue  # Keep session_v2 record if present first

                parent_id = row['parent_id'] if 'parent_id' in columns else None
                title = row['title'] if 'title' in columns and row['title'] else "Untitled Session"
                raw_agent = row['agent'] if 'agent' in columns and row['agent'] else "unknown"
                agent = normalize_agent_name(raw_agent)
                model = row['model'] if 'model' in columns and row['model'] else "unknown"
                project = row['directory'] if 'directory' in columns and row['directory'] else (
                    row['workspace'] if 'workspace' in columns and row['workspace'] else "default"
                )
                cost = float(row['cost']) if 'cost' in columns and row['cost'] is not None else 0.0
                tokens_input = int(row['tokens_input']) if 'tokens_input' in columns and row['tokens_input'] is not None else 0
                tokens_output = int(row['tokens_output']) if 'tokens_output' in columns and row['tokens_output'] is not None else 0
                tokens_reasoning = int(row['tokens_reasoning']) if 'tokens_reasoning' in columns and row['tokens_reasoning'] is not None else 0
                tokens_cache_read = int(row['tokens_cache_read']) if 'tokens_cache_read' in columns and row['tokens_cache_read'] is not None else 0
                tokens_cache_write = int(row['tokens_cache_write']) if 'tokens_cache_write' in columns and row['tokens_cache_write'] is not None else 0
                
                time_created = int(row['time_created']) if 'time_created' in columns and row['time_created'] is not None else 0
                time_updated = int(row['time_updated']) if 'time_updated' in columns and row['time_updated'] is not None else time_created
                time_archived = row['time_archived'] if 'time_archived' in columns else None

                status = "archived" if time_archived else "active"
                duration = max(0.0, (time_updated - time_created) / 1000.0) if time_created else 0.0

                sessions_by_id[sid] = SessionRecord(
                    id=sid,
                    parent_id=parent_id,
                    title=title,
                    agent=agent,
                    model=model,
                    project=project,
                    cost=cost,
                    tokens_input=tokens_input,
                    tokens_output=tokens_output,
                    tokens_reasoning=tokens_reasoning,
                    tokens_cache_read=tokens_cache_read,
                    tokens_cache_write=tokens_cache_write,
                    time_created=time_created,
                    time_updated=time_updated,
                    duration_seconds=duration,
                    status=status,
                )

        return sessions_by_id

    def extract_parts_and_tool_calls(self, conn: sqlite3.Connection, sessions: Dict[str, SessionRecord]):
        tables = self.get_existing_tables(conn)
        if 'part' not in tables:
            return

        try:
            rows = conn.execute("SELECT session_id, data FROM part WHERE data IS NOT NULL").fetchall()
        except Exception:
            return

        for row in rows:
            sid = row['session_id']
            if sid not in sessions:
                continue

            session = sessions[sid]

            try:
                part_data = json.loads(row['data'])
            except Exception:
                continue

            part_type = part_data.get("type")

            if part_type == "step-start" or part_type == "step":
                session.step_count += 1
            elif part_type == "tool":
                tool_name = part_data.get("tool", "unknown")
                call_id = part_data.get("callID", "")
                state = part_data.get("state", {})
                status = state.get("status", "unknown")
                error_msg = state.get("error")
                
                time_info = state.get("time", {})
                time_start = time_info.get("start")
                time_end = time_info.get("end")

                input_data = state.get("input", {})
                input_summary = None
                target_agent = None

                if isinstance(input_data, dict):
                    if "description" in input_data:
                        input_summary = str(input_data["description"])[:100]
                    elif "prompt" in input_data:
                        input_summary = str(input_data["prompt"])[:100]
                    elif "pattern" in input_data:
                        input_summary = f"pattern: {input_data['pattern']}"
                    elif "command" in input_data:
                        input_summary = str(input_data["command"])[:100]

                    raw_target = input_data.get("agent") or input_data.get("subagent") or input_data.get("target")
                    if raw_target:
                        target_agent = normalize_agent_name(raw_target)

                if tool_name in ("edit", "write", "apply_patch", "write_to_file", "replace_file_content"):
                    session.files_modified += 1

                if tool_name in ("task", "mc_dispatch", "subagent", "invoke_subagent"):
                    if target_agent:
                        session.subagent_calls.append(target_agent)

                tool_record = ToolCallRecord(
                    call_id=call_id,
                    tool=tool_name,
                    status=status,
                    error=error_msg,
                    input_summary=input_summary,
                    time_start=time_start,
                    time_end=time_end,
                    target_agent=target_agent,
                )
                session.tool_calls.append(tool_record)

    def get_plans(self) -> List[PlanRecord]:
        plans: List[PlanRecord] = []
        date_pattern = re.compile(r"(\d{4}-\d{2}-\d{2})")

        for p_dir in self.plans_dirs:
            if not os.path.exists(p_dir):
                continue

            plan_files = glob.glob(os.path.join(p_dir, "*.md"))

            for file_path in plan_files:
                filename = os.path.basename(file_path)
                match = date_pattern.search(filename)
                if match:
                    date_str = match.group(1)
                else:
                    mtime = os.path.getmtime(file_path)
                    date_str = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d")

                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        content = f.read()
                except Exception:
                    continue

                tasks: List[PlanTaskRecord] = []
                for line in content.splitlines():
                    line_strip = line.strip()
                    if line_strip.startswith("- [x]") or line_strip.startswith("- [X]"):
                        desc = line_strip[5:].strip()
                        tasks.append(PlanTaskRecord(description=desc, completed=True))
                    elif line_strip.startswith("- [ ]"):
                        desc = line_strip[5:].strip()
                        tasks.append(PlanTaskRecord(description=desc, completed=False))

                completed_count = sum(1 for t in tasks if t.completed)
                pending_count = sum(1 for t in tasks if not t.completed)
                total_count = len(tasks)
                completion_rate = (completed_count / total_count * 100.0) if total_count > 0 else 0.0

                plans.append(
                    PlanRecord(
                        path=file_path,
                        filename=filename,
                        date_str=date_str,
                        total_tasks=total_count,
                        completed_tasks=completed_count,
                        pending_tasks=pending_count,
                        completion_rate=completion_rate,
                        tasks=tasks,
                    )
                )

        plans.sort(key=lambda p: p.filename)
        return plans

    def collect_all(self) -> AnalyticsData:
        conn = self.connect_db()
        sessions_dict: Dict[str, SessionRecord] = {}
        if conn:
            try:
                sessions_dict = self.extract_sessions(conn)
                self.extract_parts_and_tool_calls(conn, sessions_dict)
            finally:
                conn.close()

        plans = self.get_plans()
        sessions = list(sessions_dict.values())
        collected_at = datetime.utcnow().isoformat() + "Z"

        return AnalyticsData(
            sessions=sessions,
            plans=plans,
            collected_at=collected_at,
        )
