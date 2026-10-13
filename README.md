# OpenCode System Analytics Dashboard

OpenCode System Analytics is a system-wide observability and efficiency metrics tool for OpenCode multi-agent orchestrations. It aggregates real-time and historical telemetry across sessions, calculating key indicators such as Ideation-to-Execution Ratio (IER), Plan Completion Rate (PCR), Practical Actionability Index (PAI), average steps per agent, token/cost distribution, and multi-agent interaction profiles.

## Core Features & System-Wide Scope
- **System-Wide Scope:** Inspects sessions, transcripts, and logs across `.opencode` and agent workspaces to present system-level KPIs.
- **Per-Agent Average Steps & Cost Metrics:** Tracks step counts, tool usage, duration, and token usage for all subagents (`orchestrator`, `architect`, `worker`, `explorer`, `librarian`, `coder`, `tester`, `reviewer`, `debugger`, `documenter`, `infra`, `cloudflare`, `browser`, `general`, `sec-audit`, `sec-pentest`, `sec-fix`).
- **Routing Breakdown:** Classifies every session by how it delegated — `solo`, `specialist` (lightweight only, the intended cheap route), `heavy` (at least one heavy execution agent) or `mixed` — and reports the share of total cost carried by the heavy route. Dispatch targets outside the agent roster are flagged instead of being silently counted.
- **Step-Ceiling Breach Root Causes:** For each session past its ceiling, the data-backed reason: `recon without edits`, `one tool repeated`, `tool errors`, `over-delegation`, `failed dispatch`, or `no data-backed cause`. Only signals present in the collected data are used; nothing is attributed to a guess.
- **Actionable Alerts:** Cost concentration, abandoned plans (PCR), per-agent breach rate, per-agent tool error rate, low actionability, failed dispatches, unknown dispatch targets and ceiling mismatch. Every alert ships with a concrete suggested action.
- **Slash-Command Integration:** Toggle, start, stop, or inspect dashboard status directly in OpenCode via `/analytics`.

## Data correctness notes
Two metrics were historically misleading and are now fixed:

- **Delegation counting.** Dispatches are read from dispatch tool calls (`task`, `mc_dispatch`, …) and the target is resolved from `subagent_type` / `to`. The previous implementation looked for an `agent` key that never existed, so it reported zero delegations while printing the session count under the "Subagent Delegations" label.
- **IER coverage.** Every agent is classified as ideation or execution; anything unknown is reported as `unclassified_tokens` with an explicit `coverage_pct`. Previously, unclassified agents (86M tokens, ~30% of the total) were dropped from the ratio, which understated the denominator and inflated the result.

## Quickstart

### Launch via Command Line
```bash
./launch.sh cli
```

### Launch Web Dashboard
```bash
./launch.sh web [--port 8765]
```

### Check Status & Stop
```bash
./launch.sh status
./launch.sh stop
```

## Slash Command Usage (`/analytics`)
You can use the `/analytics` slash command inside OpenCode to control the analytics server:
- `/analytics` or `/analytics status`: Check if web server is running on port 8765.
- `/analytics start`: Start background web server on `http://localhost:8765`.
- `/analytics stop`: Stop background web server.
- `/analytics cli`: Output CLI analytics report in chat.
- `/analytics alerts`: Output only the actionable findings with their suggested actions.

## Environment Variables
- `PORT` / `HOST`: HTTP server bind address (defaults: `8765`, `127.0.0.1`).
- `OPENCODE_DB_PATH`: Path to the OpenCode SQLite database (default: `~/.local/share/opencode/opencode.db`).
- `PLANS_DIRS`: Comma-separated plan directories to scan (default: `~/.opencode/plans`).

Alert thresholds — each one is independently overridable:

| Variable | Default | Meaning |
| --- | --- | --- |
| `ALERT_PCR_MIN` | `50.0` | Plan Completion Rate below this is flagged |
| `ALERT_PCR_MIN_TASKS` | `10` | Minimum checklist tasks before that alert fires |
| `ALERT_COST_CONCENTRATION_MAX` | `90.0` | Share of total cost held by one agent, above which it is flagged |
| `ALERT_BREACH_RATE_MAX` | `50.0` | Per-agent step-ceiling breach rate, above which it is flagged |
| `ALERT_BREACH_MIN_INVOCATIONS` | `3` | Minimum sessions before the breach-rate alert fires |
| `ALERT_ERROR_RATE_MAX` | `15.0` | Per-agent tool error rate, above which it is flagged |
| `ALERT_PAI_MIN` | `0.20` | Practical Actionability Index below this is flagged |
| `ALERT_FANOUT_MAX` | `5` | Delegations per session above which it counts as over-delegation |
| `ALERT_COST_FLOOR` | `0.01` | Cost floor (USD) below which cost alerts are suppressed as noise |

## REST API Endpoints
- `GET /api/metrics`: Full metric payload (IER + coverage, PCR, PAI, agent steps, costs, routing breakdown, breach causes, alerts).
- `GET /api/health`: Health status endpoint returning HTTP 200 `{"status": "ok"}`.
- `GET /`: Interactive web dashboard user interface.

## License
MIT License
