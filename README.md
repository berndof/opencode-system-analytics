# OpenCode System Analytics Dashboard

OpenCode System Analytics is a system-wide observability and efficiency metrics tool for OpenCode multi-agent orchestrations. It aggregates real-time and historical telemetry across sessions, calculating key indicators such as Ideation-to-Execution Ratio (IER), Plan Completion Rate (PCR), Practical Actionability Index (PAI), average steps per agent, token/cost distribution, and multi-agent interaction profiles.

## Core Features & System-Wide Scope
- **System-Wide Scope:** Inspects sessions, transcripts, and logs across `.opencode` and agent workspaces to present system-level KPIs.
- **Per-Agent Average Steps & Cost Metrics:** Tracks step counts, tool usage, duration, and token usage for all subagents (`orchestrator`, `architect`, `worker`, `explorer`, `librarian`, `cloudflare`, `browser`).
- **Slash-Command Integration:** Toggle, start, stop, or inspect dashboard status directly in OpenCode via `/analytics`.

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

## Environment Variables
- `ANALYTICS_PORT`: HTTP server listening port (default: `8765`).
- `ANALYTICS_HOST`: Host address to bind (default: `127.0.0.1`).
- `OPENCODE_SESSIONS_DIR`: Custom path to OpenCode sessions/transcripts.

## REST API Endpoints
- `GET /api/metrics`: Full metric payload (IER, PCR, PAI, agent steps, costs).
- `GET /api/health`: Health status endpoint returning HTTP 200 `{"status": "ok"}`.
- `GET /`: Interactive web dashboard user interface.

## License
MIT License
