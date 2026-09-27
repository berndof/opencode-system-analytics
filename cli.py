#!/usr/bin/env python3
"""
CLI Analytics Terminal Dashboard for OpenCode System Analytics.
Displays ASCII/ANSI colored reports, KPI breakdown tables, step health, plan statuses, and optimization recommendations.
"""

import sys
import os

# Ensure package directory is in sys.path when executed directly
PARENT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)

from orchestrator_analytics.config import APP_TITLE
from orchestrator_analytics.collector import AnalyticsCollector
from orchestrator_analytics.engine import AnalyticsEngine, KPIRecord

# ANSI Color Codes for Terminal Output
CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
MAGENTA = "\033[95m"
BLUE = "\033[94m"
BOLD = "\033[1m"
RESET = "\033[0m"
DIM = "\033[2m"

def format_tokens(tokens: int) -> str:
    if tokens >= 1_000_000:
        return f"{tokens / 1_000_000:.2f}M"
    elif tokens >= 1_000:
        return f"{tokens / 1_000:.1f}k"
    return str(tokens)

def get_ier_badge(ier: float) -> str:
    if ier > 2.0:
        return f"{RED}[HIGH IDEATION]{RESET}"
    elif ier < 0.5:
        return f"{BLUE}[EXECUTION FOCUSED]{RESET}"
    return f"{GREEN}[BALANCED]{RESET}"

def render_cli_dashboard():
    collector = AnalyticsCollector()
    engine = AnalyticsEngine(collector=collector)
    kpis: KPIRecord = engine.compute_all()

    agent_stats = kpis.agent_distribution
    total_delegations = sum(s.invocation_count for s in agent_stats.values())

    print(f"\n{BOLD}{CYAN}╔═════════════════════════════════════════════════════════════════════════════════════════════╗{RESET}")
    print(f"{BOLD}{CYAN}║                             OPENCODE SYSTEM ANALYTICS DASHBOARD                             ║{RESET}")
    print(f"{BOLD}{CYAN}╚═════════════════════════════════════════════════════════════════════════════════════════════╝{RESET}\n")

    # 1. OVERALL STATS
    print(f"{BOLD}{MAGENTA}── OVERALL TELEMETRY STATS ───────────────────────────────────────────────────────────────────{RESET}")
    print(f"  • Total Sessions:         {BOLD}{kpis.total_sessions}{RESET}")
    print(f"  • Subagent Delegations:   {BOLD}{total_delegations}{RESET}")
    print(f"  • Total Token Consumption:{BOLD} {format_tokens(kpis.total_tokens)}{RESET} ({kpis.total_tokens:,} tokens)")
    print(f"  • Estimated Cost:         {BOLD}${kpis.total_cost:.4f} USD{RESET}")
    print(f"  • Workspace Plans Tracked: {BOLD}{kpis.pcr_breakdown.get('total_plans', 0)}{RESET}\n")

    # 2. IDEATION VS EXECUTION & HEALTH
    ier = kpis.ideation_vs_execution_ratio
    ier_badge = get_ier_badge(ier)
    pcr = kpis.plan_completion_rate
    pai = kpis.practical_actionability_index

    print(f"{BOLD}{MAGENTA}── IDEATION VS EXECUTION HEALTH ──────────────────────────────────────────────────────────────{RESET}")
    print(f"  • Ideation/Execution Ratio (IER): {BOLD}{ier:.2f}{RESET}  {ier_badge}")
    print(f"    └─ Ideation Tokens:  {format_tokens(kpis.ier_breakdown.get('ideation_tokens', 0))}")
    print(f"    └─ Execution Tokens: {format_tokens(kpis.ier_breakdown.get('execution_tokens', 0))}")
    print(f"  • Plan Completion Rate (PCR):     {BOLD}{pcr:.1f}%{RESET} ({kpis.pcr_breakdown.get('total_completed_tasks', 0)}/{kpis.pcr_breakdown.get('total_tasks', 0)} tasks)")
    print(f"  • Practical Actionability Index:  {BOLD}{pai:.2f}{RESET} (Files modified per ideation step)\n")

    # 3. AGENT BREAKDOWN TABLE (INCLUDING AVG STEPS & BREACHES)
    print(f"{BOLD}{MAGENTA}── SUBAGENT USAGE & STEP HEALTH BREAKDOWN ────────────────────────────────────────────────────{RESET}")
    print(f"{BOLD}{'Agent':<14} {'Calls':<7} {'Share %':<8} {'AvgSteps':<9} {'P95Steps':<9} {'Breach%':<9} {'Tokens':<11} {'Cost ($)':<9} {'Err %':<7}{RESET}")
    print(f"{DIM}─────────────────────────────────────────────────────────────────────────────────────────────{RESET}")

    for agent_name, stats in sorted(agent_stats.items(), key=lambda item: item[1].tokens_total, reverse=True):
        share_pct = stats.share_pct
        err_color = RED if stats.error_rate > 10 else GREEN
        breach_color = YELLOW if stats.breach_rate > 0 else DIM
        agent_disp = f"@{agent_name}" if not agent_name.startswith("@") else agent_name
        
        print(f"{agent_disp:<14} {stats.invocation_count:<7} {share_pct:>5.1f}%   {stats.avg_steps:<9.1f} {stats.p95_steps:<9.1f} {breach_color}{stats.breach_rate:>5.1f}%{RESET}    {format_tokens(stats.tokens_total):<11} ${stats.cost:<8.4f} {err_color}{stats.error_rate:>5.1f}%{RESET}")
    print()

    # 4. RECENT PLANS STATUS
    plans = kpis.pcr_breakdown.get("plans", [])
    print(f"{BOLD}{MAGENTA}── RECENT PLANS CHECKLIST STATUS ─────────────────────────────────────────────────────────────{RESET}")
    if not plans:
        print(f"  {DIM}No plan files found in workspace plans directories{RESET}")
    else:
        for plan in plans[:5]:
            fn = plan.get("filename", "")
            comp = plan.get("completed_tasks", 0)
            tot = plan.get("total_tasks", 0)
            rate = plan.get("completion_rate", 0.0)
            status_icon = f"{GREEN}[x]{RESET}" if comp == tot and tot > 0 else f"{YELLOW}[ ]{RESET}"
            print(f"  {status_icon} {BOLD}{fn:<32}{RESET} {comp}/{tot} tasks ({rate:.0f}%)")
            for task in plan.get("tasks", [])[:3]:
                t_icon = f"{GREEN}[x]{RESET}" if task.get("completed") else f"{DIM}[ ]{RESET}"
                desc = task.get("description", "")
                if len(desc) > 60:
                    desc = desc[:57] + "..."
                print(f"      {t_icon} {desc}")
            if len(plan.get("tasks", [])) > 3:
                print(f"      {DIM}... and {len(plan['tasks']) - 3} more tasks{RESET}")
    print()

    # 5. OPTIMIZATION RECOMMENDATIONS
    print(f"{BOLD}{MAGENTA}── OPTIMIZATION RECOMMENDATIONS ──────────────────────────────────────────────────────────────{RESET}")
    recs = []

    if ier > 2.0:
        recs.append(f"{YELLOW}⚠️  High ideation overhead detected (IER = {ier:.2f} > 2.0). Increase direct execution delegations to execute code rather than planning.{RESET}")
    elif ier < 0.5:
        recs.append(f"{BLUE}ℹ️  Low ideation ratio (IER = {ier:.2f} < 0.5). Consider using @architect or @explorer before implementation.{RESET}")
    else:
        recs.append(f"{GREEN}✅ Ideation vs Execution ratio is optimal (IER = {ier:.2f}).{RESET}")

    if pcr < 50.0 and kpis.pcr_breakdown.get("total_tasks", 0) > 0:
        recs.append(f"{YELLOW}⚠️  Plan completion rate is low ({pcr:.1f}%). Ensure completed tasks are marked with [x] in plan files.{RESET}")

    if kpis.step_health_alerts:
        recs.append(f"{RED}⚠️  {len(kpis.step_health_alerts)} session(s) reached or approached agent step ceilings. Check tool efficiency.{RESET}")

    if pai < 0.2:
        recs.append(f"{YELLOW}⚠️  Actionability index is low ({pai:.2f}). Sessions produce few file edits relative to planning steps.{RESET}")

    for rec in recs:
        print(f"  {rec}")
    print(f"\n{BOLD}{CYAN}═════════════════════════════════════════════════════════════════════════════════════════════{RESET}\n")

if __name__ == "__main__":
    render_cli_dashboard()
