"""
Metrics & Efficiency Engine for OpenCode System Analytics.
Computes KPIs including Per-Agent Stats, System-wide Scopes (Projects/Workspaces, Models),
Ideation vs Execution Ratio (IER), Plan Completion Rate (PCR), Practical Actionability Index (PAI),
Step Health & Breach Rates, and Time-Series Trends.
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime
import math
from collections import Counter
from typing import List, Dict, Any, Optional

from .collector import (
    AnalyticsCollector,
    AnalyticsData,
    SessionRecord,
    PlanRecord,
    normalize_agent_name,
    DISPATCH_TOOLS,
)
from . import config

# Step ceilings for the current agent roster. Legacy keys are kept on purpose:
# historical sessions were recorded under those names and would otherwise be
# scored against the wrong ceiling.
AGENT_STEP_CEILINGS = {
    # current suite
    "orchestrator": 12,
    "architect": 10,
    "worker": 10,
    "explorer": 8,
    "librarian": 6,
    "coder": 10,
    "tester": 8,
    "reviewer": 6,
    "debugger": 8,
    "documenter": 6,
    "infra": 10,
    "browser": 8,
    "cloudflare": 8,
    "general": 10,
    "sec-audit": 12,
    "sec-pentest": 15,
    "sec-fix": 15,
    # legacy (historical sessions only)
    "plan": 12,
    "build": 10,
    "explore": 8,
}
DEFAULT_STEP_CEILING = 10

# Every agent is classified so no token silently drops out of the IER ratio.
# `unclassified` is reported explicitly instead of being ignored.
IDEATION_AGENTS = {
    "architect", "orchestrator", "explorer", "librarian", "reviewer",
    "sec-audit", "sec-pentest",
    # legacy: historical sessions recorded under these names
    "plan", "explore",
}
EXECUTION_AGENTS = {
    "build", "worker", "coder", "debugger", "documenter", "tester", "infra",
    "browser", "cloudflare", "general", "sec-fix",
}

# Agents that mutate state: routing a whole task to one of these is the
# expensive path the orchestrator is supposed to avoid.
HEAVY_EXECUTION_AGENTS = {"build", "general", "coder", "infra", "sec-fix"}

# The agent roster the suite is supposed to use. A dispatch target outside this
# set is reported as an unknown route instead of being silently counted.
KNOWN_AGENT_ROSTER = set(AGENT_STEP_CEILINGS.keys())


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
class KPIAlert:
    """An actionable finding: what is wrong, how bad, and what to do about it."""

    id: str
    severity: str          # critical | warn | info
    title: str
    detail: str
    suggestion: str
    value: float = 0.0
    threshold: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class BreachCause:
    """Why a single session blew past its step ceiling, derived from real data."""

    session_id: str
    title: str
    agent: str
    step_count: int
    ceiling: int
    causes: List[str] = field(default_factory=list)
    evidence: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RouteRecord:
    """How one session was routed: what it delegated, and what it cost."""

    session_id: str
    title: str
    primary_agent: str
    route_class: str        # solo | specialist | heavy | mixed
    delegates: List[str]
    unknown_delegates: List[str]
    dispatches: int
    steps: int
    files_modified: int
    tokens_total: int
    cost: float

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
    routing_breakdown: Dict[str, Any] = field(default_factory=dict)
    breach_causes: Dict[str, Any] = field(default_factory=dict)
    alerts: List[KPIAlert] = field(default_factory=list)

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
            "routing_breakdown": self.routing_breakdown,
            "breach_causes": self.breach_causes,
            "alerts": [a.to_dict() for a in self.alerts],
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
        unclassified_tokens = 0

        agent_tokens_map = {}

        for agent, stats in agent_stats.items():
            agent_tokens_map[agent] = stats.tokens_total
            if agent in IDEATION_AGENTS:
                ideation_tokens += stats.tokens_total
                ideation_input_tokens += stats.tokens_input
            elif agent in EXECUTION_AGENTS:
                execution_tokens += stats.tokens_total
                execution_input_tokens += stats.tokens_input
            else:
                # Previously dropped silently, which understated the denominator
                # and inflated the ratio. Reported explicitly instead.
                unclassified_tokens += stats.tokens_total

        total_classified = ideation_tokens + execution_tokens
        ier_total = ideation_tokens / max(1, execution_tokens)
        ier_input = ideation_input_tokens / max(1, execution_input_tokens)
        coverage_pct = (
            (total_classified / max(1, total_classified + unclassified_tokens)) * 100.0
        )

        return {
            "ier": round(ier_total, 4),
            "ier_input_only": round(ier_input, 4),
            "ideation_tokens": ideation_tokens,
            "execution_tokens": execution_tokens,
            "unclassified_tokens": unclassified_tokens,
            "coverage_pct": round(coverage_pct, 2),
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

    def compute_routing_breakdown(self) -> Dict[str, Any]:
        """E1: who dispatched whom, and which sessions took the expensive route.

        A session is classified by the shape of its delegations:
          solo       - no delegation at all
          specialist - only lightweight specialists (the intended cheap route)
          heavy      - at least one heavy execution agent (build/coder/general/...)
          mixed      - heavy plus specialists
        """
        routes: List[RouteRecord] = []

        for session in self.data.sessions:
            delegates = [normalize_agent_name(a) for a in session.subagent_calls]
            if not delegates:
                continue  # solo sessions are counted separately, not itemized

            unique_delegates = sorted(set(delegates))
            unknown = sorted({d for d in unique_delegates if d not in KNOWN_AGENT_ROSTER})
            heavy = [d for d in unique_delegates if d in HEAVY_EXECUTION_AGENTS]
            light = [d for d in unique_delegates if d not in HEAVY_EXECUTION_AGENTS]

            if heavy and light:
                route_class = "mixed"
            elif heavy:
                route_class = "heavy"
            else:
                route_class = "specialist"

            tot_tokens = (
                session.tokens_input + session.tokens_output + session.tokens_reasoning
                + session.tokens_cache_read + session.tokens_cache_write
            )

            routes.append(
                RouteRecord(
                    session_id=session.id,
                    title=session.title,
                    primary_agent=normalize_agent_name(session.agent),
                    route_class=route_class,
                    delegates=unique_delegates,
                    unknown_delegates=unknown,
                    dispatches=len(delegates),
                    steps=session.step_count,
                    files_modified=session.files_modified,
                    tokens_total=tot_tokens,
                    cost=round(session.cost, 4),
                )
            )

        class_counts = Counter(r.route_class for r in routes)
        total_sessions = len(self.data.sessions)
        solo_sessions = total_sessions - len(routes)

        # Cost carried by the heavy path: the number that motivated routing rules.
        heavy_sessions = [r for r in routes if r.route_class in ("heavy", "mixed")]
        heavy_cost = sum(r.cost for r in heavy_sessions)
        total_cost = sum(s.cost for s in self.data.sessions)

        dispatch_targets = Counter()
        failed_dispatch_count = 0
        for session in self.data.sessions:
            for target in session.subagent_calls:
                dispatch_targets[normalize_agent_name(target)] += 1
            failed_dispatch_count += sum(
                1 for tc in session.tool_calls
                if tc.tool in DISPATCH_TOOLS and (tc.status in ("error", "failed") or tc.error)
            )

        top_expensive = sorted(routes, key=lambda r: r.cost, reverse=True)[:10]

        return {
            "sessions_with_delegation": len(routes),
            "sessions_solo": solo_sessions,
            "route_classes": {
                "solo": solo_sessions,
                "specialist": class_counts.get("specialist", 0),
                "heavy": class_counts.get("heavy", 0),
                "mixed": class_counts.get("mixed", 0),
            },
            "heavy_route_cost": round(heavy_cost, 4),
            "heavy_route_cost_share_pct": round((heavy_cost / max(1e-9, total_cost)) * 100.0, 2),
            "total_dispatches": sum(dispatch_targets.values()),
            "failed_dispatches": failed_dispatch_count,
            "dispatch_targets": dict(dispatch_targets.most_common()),
            "unknown_dispatch_targets": sorted(
                {t for t in dispatch_targets if t not in KNOWN_AGENT_ROSTER}
            ),
            "top_cost_routes": [r.to_dict() for r in top_expensive],
        }

    def compute_breach_root_causes(self) -> Dict[str, Any]:
        """E1: for every session past its ceiling, the data-backed reason why.

        Only signals actually present in the collected data are used; a breach
        with no matching signal is reported as `unexplained` rather than
        attributed to a guess.
        """
        causes: List[BreachCause] = []

        for session in self.data.sessions:
            agent = normalize_agent_name(session.agent)
            ceiling = AGENT_STEP_CEILINGS.get(agent, DEFAULT_STEP_CEILING)
            if session.step_count < ceiling:
                continue

            tool_calls = session.tool_calls
            total_tools = len(tool_calls)
            errors = sum(1 for tc in tool_calls if tc.status in ("error", "failed") or tc.error)
            error_pct = (errors / total_tools * 100.0) if total_tools else 0.0

            tool_counter = Counter(tc.tool for tc in tool_calls)
            top_tool, top_tool_count = (tool_counter.most_common(1) or [(None, 0)])[0]
            top_tool_share = (top_tool_count / total_tools * 100.0) if total_tools else 0.0

            dispatches = len(session.subagent_calls)
            failed_dispatches = sum(
                1 for tc in tool_calls
                if tc.tool in DISPATCH_TOOLS and (tc.status in ("error", "failed") or tc.error)
            )

            labels: List[str] = []
            evidence: Dict[str, Any] = {}

            if failed_dispatches:
                labels.append("failed_dispatch")
                evidence["failed_dispatches"] = failed_dispatches

            if total_tools and error_pct >= 25.0:
                labels.append("tool_errors")
                evidence["tool_error_pct"] = round(error_pct, 1)
                evidence["error_count"] = errors

            if session.files_modified == 0:
                labels.append("no_output")
                evidence["files_modified"] = 0

            if dispatches >= config.ALERT_FANOUT_MAX:
                labels.append("over_delegation")
                evidence["dispatches"] = dispatches

            if top_tool and top_tool_share >= 60.0 and top_tool_count >= 5:
                labels.append("tool_loop")
                evidence["dominant_tool"] = top_tool
                evidence["dominant_tool_share_pct"] = round(top_tool_share, 1)
                evidence["dominant_tool_count"] = top_tool_count

            if not labels:
                labels.append("unexplained")
                evidence["tool_calls"] = total_tools

            causes.append(
                BreachCause(
                    session_id=session.id,
                    title=session.title,
                    agent=agent,
                    step_count=session.step_count,
                    ceiling=ceiling,
                    causes=labels,
                    evidence=evidence,
                )
            )

        causes.sort(key=lambda c: (c.step_count / max(1, c.ceiling)), reverse=True)

        aggregate = Counter()
        per_agent = Counter()
        for c in causes:
            for label in c.causes:
                aggregate[label] += 1
            per_agent[c.agent] += 1

        return {
            "total_breaches": len(causes),
            "cause_distribution": dict(aggregate.most_common()),
            "breaches_by_agent": dict(per_agent.most_common()),
            "breaches": [c.to_dict() for c in causes],
        }

    def compute_alerts(
        self,
        agent_stats: Dict[str, AgentUsageStats],
        pcr_data: Dict[str, Any],
        pai_data: Dict[str, Any],
        routing: Dict[str, Any],
        breach_data: Dict[str, Any],
    ) -> List[KPIAlert]:
        """E2: actionable findings, each with a concrete suggested action."""
        alerts: List[KPIAlert] = []

        total_cost = sum(s.cost for s in self.data.sessions)
        cost_noise = total_cost < config.ALERT_COST_FLOOR

        # 1. Cost concentration in a single agent.
        if agent_stats and total_cost > 0 and not cost_noise:
            top_agent, top_stats = max(agent_stats.items(), key=lambda kv: kv[1].cost)
            share = (top_stats.cost / total_cost) * 100.0
            if share > config.ALERT_COST_CONCENTRATION_MAX:
                alerts.append(KPIAlert(
                    id="cost_concentration",
                    severity="critical" if share > 95.0 else "warn",
                    title=f"{share:.1f}% of all cost sits in one agent: {top_agent}",
                    detail=(
                        f"{top_agent} absorbed ${top_stats.cost:.4f} of ${total_cost:.4f} "
                        f"across {top_stats.invocation_count} session(s)."
                    ),
                    suggestion=(
                        "Route surgical work to a cheap specialist (@coder/@worker) and keep "
                        "broad work at the primary; delegate only recon, tests and review."
                    ),
                    value=round(share, 2),
                    threshold=config.ALERT_COST_CONCENTRATION_MAX,
                ))

        # 2. Abandoned planning.
        pcr = pcr_data.get("overall_pcr", 0.0)
        total_tasks = pcr_data.get("total_tasks", 0)
        if total_tasks >= config.ALERT_PCR_MIN_TASKS and pcr < config.ALERT_PCR_MIN:
            alerts.append(KPIAlert(
                id="pcr_low",
                severity="warn",
                title=f"Plan Completion Rate is {pcr:.1f}%",
                detail=(
                    f"{pcr_data.get('total_completed_tasks', 0)}/{total_tasks} checklist items "
                    f"were ever checked across {pcr_data.get('total_plans', 0)} plan file(s)."
                ),
                suggestion=(
                    "Plans are being written but not executed. Either shrink the plan to the "
                    "next verifiable step, or stop writing one for single-step tasks."
                ),
                value=round(pcr, 2),
                threshold=config.ALERT_PCR_MIN,
            ))

        # 3. Step-ceiling breaches per agent.
        for agent, stats in sorted(
            agent_stats.items(), key=lambda kv: kv[1].breach_rate, reverse=True
        ):
            if (
                stats.breach_rate > config.ALERT_BREACH_RATE_MAX
                and stats.invocation_count >= config.ALERT_BREACH_MIN_INVOCATIONS
            ):
                alerts.append(KPIAlert(
                    id=f"breach_rate:{agent}",
                    severity="warn",
                    title=f"{agent} breaches its step ceiling {stats.breach_rate:.0f}% of the time",
                    detail=(
                        f"{stats.breach_count}/{stats.invocation_count} sessions hit or passed "
                        f"{stats.step_ceiling} steps (max observed: {stats.max_steps_observed})."
                    ),
                    suggestion="Check the breach causes below for this agent and split the scope.",
                    value=stats.breach_rate,
                    threshold=config.ALERT_BREACH_RATE_MAX,
                ))

        # 4. Tool error rate per agent.
        for agent, stats in sorted(
            agent_stats.items(), key=lambda kv: kv[1].error_rate, reverse=True
        ):
            if stats.total_tool_calls >= 10 and stats.error_rate > config.ALERT_ERROR_RATE_MAX:
                alerts.append(KPIAlert(
                    id=f"error_rate:{agent}",
                    severity="warn",
                    title=f"{agent} fails {stats.error_rate:.0f}% of its tool calls",
                    detail=(
                        f"{stats.error_tool_calls}/{stats.total_tool_calls} tool calls errored."
                    ),
                    suggestion="Verify the tool grants in the agent frontmatter (a missing or renamed tool fails every call).",
                    value=stats.error_rate,
                    threshold=config.ALERT_ERROR_RATE_MAX,
                ))

        # 5. Ideation without delivery.
        pai = pai_data.get("pai", 0.0)
        if pai_data.get("ideation_steps", 0) >= 50 and pai < config.ALERT_PAI_MIN:
            alerts.append(KPIAlert(
                id="pai_low",
                severity="warn",
                title=f"Practical Actionability Index is {pai:.2f}",
                detail=(
                    f"{pai_data.get('total_files_modified', 0)} files modified across "
                    f"{pai_data.get('ideation_steps', 0)} ideation steps."
                ),
                suggestion="Recon is producing no edits: move the design gate earlier or delegate the edit step.",
                value=round(pai, 4),
                threshold=config.ALERT_PAI_MIN,
            ))

        # 6. Over-delegation fan-out.
        route_classes = routing.get("route_classes", {})
        if route_classes.get("solo", 0) == len(self.data.sessions) and self.data.sessions:
            alerts.append(KPIAlert(
                id="no_delegation",
                severity="info",
                title="No subagent delegation recorded at all",
                detail="Every session handled everything inline; the specialist roster is idle.",
                suggestion="Use recon/design specialists for anything non-trivial to cut primary context.",
                value=0.0,
                threshold=0.0,
            ))

        # 7. Dispatches to agents outside the roster (renamed / removed agents).
        unknown_targets = routing.get("unknown_dispatch_targets", [])
        if unknown_targets:
            alerts.append(KPIAlert(
                id="unknown_dispatch_target",
                severity="warn",
                title=f"Delegations to unknown agent(s): {', '.join(unknown_targets)}",
                detail=(
                    "These targets are not in the agent roster, so their step ceilings and "
                    "token classification fall back to defaults."
                ),
                suggestion="Update AGENT_STEP_CEILINGS/roster, or fix the routing rule naming a removed agent.",
                value=float(len(unknown_targets)),
                threshold=0.0,
            ))

        # 7b. Dispatches that failed: the spec was not closed enough to execute.
        failed_dispatches = routing.get("failed_dispatches", 0)
        total_dispatches = routing.get("total_dispatches", 0)
        if failed_dispatches and total_dispatches:
            fail_pct = (failed_dispatches / total_dispatches) * 100.0
            if fail_pct >= 20.0:
                alerts.append(KPIAlert(
                    id="failed_dispatch",
                    severity="warn",
                    title=f"{failed_dispatches}/{total_dispatches} delegations failed ({fail_pct:.0f}%)",
                    detail="A dispatch that errors usually means the closed spec was incomplete or the target agent does not exist.",
                    suggestion="Check the unknown_dispatch_target alert first, then tighten the spec before dispatching.",
                    value=round(fail_pct, 2),
                    threshold=20.0,
                ))

        # 8. Unexplained breaches: the ceiling is wrong, not the behaviour.
        cause_dist = breach_data.get("cause_distribution", {})
        unexplained = cause_dist.get("unexplained", 0)
        total_breaches = breach_data.get("total_breaches", 0)
        if total_breaches and unexplained / total_breaches >= 0.5:
            alerts.append(KPIAlert(
                id="ceiling_mismatch",
                severity="info",
                title=f"{unexplained}/{total_breaches} breaches have no data-backed cause",
                detail="No error loop, no missing output, no fan-out, no dominant tool.",
                suggestion="The agent's real working size no longer matches its declared ceiling: retune it.",
                value=float(unexplained),
                threshold=float(total_breaches) * 0.5,
            ))

        order = {"critical": 0, "warn": 1, "info": 2}
        alerts.sort(key=lambda a: (order.get(a.severity, 3), -a.value))
        return alerts

    def compute_all(self) -> KPIRecord:
        agent_stats = self.compute_agent_usage_distribution()
        project_breakdown = self.compute_project_breakdown()
        model_breakdown = self.compute_model_breakdown()
        ier_data = self.compute_ideation_vs_execution_ratio(agent_stats)
        pcr_data = self.compute_plan_completion_rate()
        pai_data = self.compute_practical_actionability_index(agent_stats)
        step_alerts = self.compute_step_health_alerts()
        ts_data = self.compute_time_series()
        routing = self.compute_routing_breakdown()
        breach_data = self.compute_breach_root_causes()
        alerts = self.compute_alerts(agent_stats, pcr_data, pai_data, routing, breach_data)

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
            routing_breakdown=routing,
            breach_causes=breach_data,
            alerts=alerts,
        )
