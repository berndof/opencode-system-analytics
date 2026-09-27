"""
Metrics & Efficiency Engine for OpenCode System Analytics.
Computes KPIs including Per-Agent Stats, System-wide Scopes (Projects/Workspaces, Models),
Ideation vs Execution Ratio (IER), Plan Completion Rate (PCR), Practical Actionability Index (PAI),
Step Health & Breach Rates, and Time-Series Trends.
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime
import math
from typing import List, Dict, Any, Optional

from .collector import AnalyticsCollector, AnalyticsData, SessionRecord, PlanRecord, normalize_agent_name

AGENT_STEP_CEILINGS = {
    "orchestrator": 12,
    "worker": 10,
    "explorer": 8,
    "explore": 8,
    "librarian": 6,
    "cloudflare": 8,
    "browser": 8,
    "general": 10,
    "architect": 10,
    "plan": 12,
    "build": 10,
}
DEFAULT_STEP_CEILING = 10

IDEATION_AGENTS = {"architect", "explorer", "explore", "librarian", "plan"}
EXECUTION_AGENTS = {"worker", "build"}


def calculate_median(values: List[float]) -> float:
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    mid = n // 2
    if n % 2 == 1:
        return float(sorted_vals[mid])
    else:
        return float(sorted_vals[mid - 1] + sorted_vals[mid]) / 2.0


def calculate_percentile(values: List[float], percentile: float) -> float:
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    k = (len(sorted_vals) - 1) * (percentile / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return float(sorted_vals[int(k)])
    d0 = sorted_vals[int(f)] * (c - k)
    d1 = sorted_vals[int(c)] * (k - f)
    return float(d0 + d1)


@dataclass
class AgentUsageStats:
    agent: str
    invocation_count: int = 0
    share_pct: float = 0.0
    tokens_input: int = 0
    tokens_output: int = 0
    tokens_reasoning: int = 0
    tokens_cache_read: int = 0
    tokens_cache_write: int = 0
    tokens_cache_total: int = 0
    tokens_total: int = 0
    avg_tokens: float = 0.0
    med_tokens: float = 0.0
    cost: float = 0.0
    avg_cost: float = 0.0
    total_duration_seconds: float = 0.0
    avg_duration_seconds: float = 0.0
    total_tool_calls: int = 0
    error_tool_calls: int = 0
    error_rate: float = 0.0
    step_ceiling: int = DEFAULT_STEP_CEILING
    max_steps_observed: int = 0
    avg_steps: float = 0.0
    med_steps: float = 0.0
    p95_steps: float = 0.0
    breach_count: int = 0
    breach_rate: float = 0.0
    sessions_near_ceiling: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class StepHealthAlert:
    session_id: str
    title: str
    agent: str
    step_count: int
    ceiling: int
    percentage: float


@dataclass
class TimeSeriesPoint:
    time_key: str
    session_count: int = 0
    tokens_total: int = 0
    cost: float = 0.0
    error_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class KPIRecord:
    agent_distribution: Dict[str, AgentUsageStats]
    project_breakdown: Dict[str, Dict[str, Any]]
    model_breakdown: Dict[str, Dict[str, Any]]
    ideation_vs_execution_ratio: float
    ier_breakdown: Dict[str, Any]
    plan_completion_rate: float
    pcr_breakdown: Dict[str, Any]
    practical_actionability_index: float
    pai_breakdown: Dict[str, Any]
    step_health_alerts: List[StepHealthAlert]
    time_series_daily: List[TimeSeriesPoint]
    time_series_hourly: List[TimeSeriesPoint]
    total_sessions: int
    total_cost: float
    total_tokens: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_distribution": {k: v.to_dict() for k, v in self.agent_distribution.items()},
            "project_breakdown": self.project_breakdown,
            "model_breakdown": self.model_breakdown,
            "ideation_vs_execution_ratio": self.ideation_vs_execution_ratio,
            "ier_breakdown": self.ier_breakdown,
            "plan_completion_rate": self.plan_completion_rate,
            "pcr_breakdown": self.pcr_breakdown,
            "practical_actionability_index": self.practical_actionability_index,
            "pai_breakdown": self.pai_breakdown,
            "step_health_alerts": [asdict(a) for a in self.step_health_alerts],
            "time_series_daily": [p.to_dict() for p in self.time_series_daily],
            "time_series_hourly": [p.to_dict() for p in self.time_series_hourly],
            "total_sessions": self.total_sessions,
            "total_cost": round(self.total_cost, 4),
            "total_tokens": self.total_tokens,
        }


class AnalyticsEngine:
    """Computes all telemetry KPIs and metrics from collected AnalyticsData."""

    def __init__(self, data: Optional[AnalyticsData] = None, collector: Optional[AnalyticsCollector] = None):
        if data:
            self.data = data
        elif collector:
            self.data = collector.collect_all()
        else:
            self.data = AnalyticsCollector().collect_all()

    def compute_agent_usage_distribution(self) -> Dict[str, AgentUsageStats]:
        stats: Dict[str, AgentUsageStats] = {}
        agent_steps_map: Dict[str, List[float]] = {}
        agent_tokens_map: Dict[str, List[float]] = {}

        total_sessions_count = len(self.data.sessions)
        
        for session in self.data.sessions:
            agent = normalize_agent_name(session.agent)
            if agent not in stats:
                ceiling = AGENT_STEP_CEILINGS.get(agent, DEFAULT_STEP_CEILING)
                stats[agent] = AgentUsageStats(agent=agent, step_ceiling=ceiling)
                agent_steps_map[agent] = []
                agent_tokens_map[agent] = []

            s = stats[agent]
            s.invocation_count += 1
            s.tokens_input += session.tokens_input
            s.tokens_output += session.tokens_output
            s.tokens_reasoning += session.tokens_reasoning
            s.tokens_cache_read += session.tokens_cache_read
            s.tokens_cache_write += session.tokens_cache_write
            
            cache_sum = session.tokens_cache_read + session.tokens_cache_write
            s.tokens_cache_total += cache_sum
            
            tot_tokens = (
                session.tokens_input
                + session.tokens_output
                + session.tokens_reasoning
                + cache_sum
            )
            s.tokens_total += tot_tokens
            agent_tokens_map[agent].append(float(tot_tokens))

            s.cost += session.cost
            s.total_duration_seconds += session.duration_seconds

            s.max_steps_observed = max(s.max_steps_observed, session.step_count)
            agent_steps_map[agent].append(float(session.step_count))

            if session.step_count >= s.step_ceiling:
                s.breach_count += 1

            if session.step_count >= (s.step_ceiling - 2):
                s.sessions_near_ceiling += 1

            tool_calls = session.tool_calls
            s.total_tool_calls += len(tool_calls)
            for tc in tool_calls:
                if tc.status in ("error", "failed") or tc.error is not None:
                    s.error_tool_calls += 1

        for agent, s in stats.items():
            if s.invocation_count > 0:
                s.share_pct = round((s.invocation_count / max(1, total_sessions_count)) * 100.0, 2)
                s.avg_duration_seconds = round(s.total_duration_seconds / s.invocation_count, 2)
                s.avg_cost = round(s.cost / s.invocation_count, 4)
                s.avg_tokens = round(s.tokens_total / s.invocation_count, 2)
                s.med_tokens = round(calculate_median(agent_tokens_map[agent]), 2)
                
                steps_list = agent_steps_map[agent]
                s.avg_steps = round(sum(steps_list) / len(steps_list), 2)
                s.med_steps = round(calculate_median(steps_list), 2)
                s.p95_steps = round(calculate_percentile(steps_list, 95.0), 2)

                s.breach_rate = round((s.breach_count / s.invocation_count) * 100.0, 2)

            if s.total_tool_calls > 0:
                s.error_rate = round((s.error_tool_calls / s.total_tool_calls) * 100.0, 2)

            s.cost = round(s.cost, 4)

        return stats

    def compute_project_breakdown(self) -> Dict[str, Dict[str, Any]]:
        projects: Dict[str, Dict[str, Any]] = {}
        for session in self.data.sessions:
            proj = session.project or "default"
            if proj not in projects:
                projects[proj] = {
                    "project": proj,
                    "session_count": 0,
                    "tokens_total": 0,
                    "cost": 0.0,
                    "files_modified": 0,
                }
            p = projects[proj]
            p["session_count"] += 1
            p["tokens_total"] += (
                session.tokens_input + session.tokens_output + session.tokens_reasoning +
                session.tokens_cache_read + session.tokens_cache_write
            )
            p["cost"] += session.cost
            p["files_modified"] += session.files_modified

        for p in projects.values():
            p["cost"] = round(p["cost"], 4)
        return projects

    def compute_model_breakdown(self) -> Dict[str, Dict[str, Any]]:
        models: Dict[str, Dict[str, Any]] = {}
        for session in self.data.sessions:
            model = session.model or "unknown"
            if model not in models:
                models[model] = {
                    "model": model,
                    "session_count": 0,
                    "tokens_total": 0,
                    "cost": 0.0,
                }
            m = models[model]
            m["session_count"] += 1
            m["tokens_total"] += (
                session.tokens_input + session.tokens_output + session.tokens_reasoning +
                session.tokens_cache_read + session.tokens_cache_write
            )
            m["cost"] += session.cost

        for m in models.values():
            m["cost"] = round(m["cost"], 4)
        return models

    def compute_ideation_vs_execution_ratio(self, agent_stats: Dict[str, AgentUsageStats]) -> Dict[str, Any]:
        ideation_tokens = 0
        execution_tokens = 0
        ideation_input_tokens = 0
        execution_input_tokens = 0

        agent_tokens_map = {}

        for agent, stats in agent_stats.items():
            agent_tokens_map[agent] = stats.tokens_total
            if agent in IDEATION_AGENTS:
                ideation_tokens += stats.tokens_total
                ideation_input_tokens += stats.tokens_input
            elif agent in EXECUTION_AGENTS:
                execution_tokens += stats.tokens_total
                execution_input_tokens += stats.tokens_input

        ier_total = ideation_tokens / max(1, execution_tokens)
        ier_input = ideation_input_tokens / max(1, execution_input_tokens)

        return {
            "ier": round(ier_total, 4),
            "ier_input_only": round(ier_input, 4),
            "ideation_tokens": ideation_tokens,
            "execution_tokens": execution_tokens,
            "ideation_input_tokens": ideation_input_tokens,
            "execution_input_tokens": execution_input_tokens,
            "breakdown": agent_tokens_map,
        }

    def compute_plan_completion_rate(self) -> Dict[str, Any]:
        plans = self.data.plans
        if not plans:
            return {
                "overall_pcr": 0.0,
                "total_plans": 0,
                "total_completed_tasks": 0,
                "total_tasks": 0,
                "plans": [],
            }

        total_completed = sum(p.completed_tasks for p in plans)
        total_tasks = sum(p.total_tasks for p in plans)
        overall_pcr = (total_completed / max(1, total_tasks)) * 100.0

        plan_details = [
            {
                "filename": p.filename,
                "date": p.date_str,
                "completion_rate": round(p.completion_rate, 2),
                "completed_tasks": p.completed_tasks,
                "total_tasks": p.total_tasks,
            }
            for p in plans
        ]

        return {
            "overall_pcr": round(overall_pcr, 2),
            "total_plans": len(plans),
            "total_completed_tasks": total_completed,
            "total_tasks": total_tasks,
            "plans": plan_details,
        }

    def compute_practical_actionability_index(self, agent_stats: Dict[str, AgentUsageStats]) -> Dict[str, Any]:
        total_files_modified = sum(s.files_modified for s in self.data.sessions)
        
        ideation_steps = 0
        for session in self.data.sessions:
            agent = normalize_agent_name(session.agent)
            if agent in IDEATION_AGENTS:
                ideation_steps += session.step_count

        pai = total_files_modified / max(1, ideation_steps)

        return {
            "pai": round(pai, 4),
            "total_files_modified": total_files_modified,
            "ideation_steps": ideation_steps,
        }

    def compute_step_health_alerts(self) -> List[StepHealthAlert]:
        alerts: List[StepHealthAlert] = []

        for session in self.data.sessions:
            agent = normalize_agent_name(session.agent)
            ceiling = AGENT_STEP_CEILINGS.get(agent, DEFAULT_STEP_CEILING)

            if session.step_count >= (ceiling - 2):
                pct = round((session.step_count / ceiling) * 100.0, 1)
                alerts.append(
                    StepHealthAlert(
                        session_id=session.id,
                        title=session.title,
                        agent=agent,
                        step_count=session.step_count,
                        ceiling=ceiling,
                        percentage=pct,
                    )
                )

        alerts.sort(key=lambda a: a.percentage, reverse=True)
        return alerts

    def compute_time_series(self) -> Dict[str, List[TimeSeriesPoint]]:
        daily_dict: Dict[str, TimeSeriesPoint] = {}
        hourly_dict: Dict[str, TimeSeriesPoint] = {}

        for session in self.data.sessions:
            if not session.time_created:
                continue

            dt = datetime.fromtimestamp(session.time_created / 1000.0)
            day_key = dt.strftime("%Y-%m-%d")
            hour_key = dt.strftime("%Y-%m-%d %H:00")

            tot_tokens = (
                session.tokens_input
                + session.tokens_output
                + session.tokens_reasoning
                + session.tokens_cache_read
                + session.tokens_cache_write
            )

            error_count = sum(
                1 for tc in session.tool_calls if tc.status in ("error", "failed") or tc.error
            )

            # Daily update
            if day_key not in daily_dict:
                daily_dict[day_key] = TimeSeriesPoint(time_key=day_key)
            d = daily_dict[day_key]
            d.session_count += 1
            d.tokens_total += tot_tokens
            d.cost += session.cost
            d.error_count += error_count

            # Hourly update
            if hour_key not in hourly_dict:
                hourly_dict[hour_key] = TimeSeriesPoint(time_key=hour_key)
            h = hourly_dict[hour_key]
            h.session_count += 1
            h.tokens_total += tot_tokens
            h.cost += session.cost
            h.error_count += error_count

        daily_sorted = [daily_dict[k] for k in sorted(daily_dict.keys())]
        hourly_sorted = [hourly_dict[k] for k in sorted(hourly_dict.keys())]

        for p in daily_sorted + hourly_sorted:
            p.cost = round(p.cost, 4)

        return {
            "daily": daily_sorted,
            "hourly": hourly_sorted,
        }

    def compute_all(self) -> KPIRecord:
        agent_stats = self.compute_agent_usage_distribution()
        project_breakdown = self.compute_project_breakdown()
        model_breakdown = self.compute_model_breakdown()
        ier_data = self.compute_ideation_vs_execution_ratio(agent_stats)
        pcr_data = self.compute_plan_completion_rate()
        pai_data = self.compute_practical_actionability_index(agent_stats)
        step_alerts = self.compute_step_health_alerts()
        ts_data = self.compute_time_series()

        total_sessions = len(self.data.sessions)
        total_cost = sum(s.cost for s in self.data.sessions)
        total_tokens = sum(
            s.tokens_input + s.tokens_output + s.tokens_reasoning + s.tokens_cache_read + s.tokens_cache_write
            for s in self.data.sessions
        )

        return KPIRecord(
            agent_distribution=agent_stats,
            project_breakdown=project_breakdown,
            model_breakdown=model_breakdown,
            ideation_vs_execution_ratio=ier_data["ier"],
            ier_breakdown=ier_data,
            plan_completion_rate=pcr_data["overall_pcr"],
            pcr_breakdown=pcr_data,
            practical_actionability_index=pai_data["pai"],
            pai_breakdown=pai_data,
            step_health_alerts=step_alerts,
            time_series_daily=ts_data["daily"],
            time_series_hourly=ts_data["hourly"],
            total_sessions=total_sessions,
            total_cost=total_cost,
            total_tokens=total_tokens,
        )
