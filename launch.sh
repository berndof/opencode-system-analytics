#!/usr/bin/env bash
# OpenCode System Analytics Launcher Script

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PYTHONPATH="${SCRIPT_DIR}/..:${PYTHONPATH}"

PID_FILE="${SCRIPT_DIR}/.analytics_server.pid"

MODE="${1:-cli}"

case "${MODE}" in
    start|daemon)
        if pgrep -f "orchestrator_analytics.server" > /dev/null 2>&1; then
            echo "OpenCode System Analytics server is already running on http://localhost:8765"
            exit 0
        fi
        echo "Starting OpenCode System Analytics Web Server in background..."
        (
            cd "${SCRIPT_DIR}/.." || exit 1
            setsid python3 -m orchestrator_analytics.server "${@:2}" > "${SCRIPT_DIR}/server.log" 2>&1 < /dev/null &
            echo $! > "${PID_FILE}"
        )
        sleep 1
        if [ -f "${PID_FILE}" ]; then
            PID="$(cat "${PID_FILE}")"
            if kill -0 "${PID}" 2>/dev/null; then
                echo "OpenCode System Analytics Web Server started successfully (PID ${PID}) on http://localhost:8765"
                exit 0
            fi
        fi
        echo "Failed to start server. Check logs at ${SCRIPT_DIR}/server.log"
        exit 1
        ;;
    web|server|run)
        echo "Starting OpenCode System Analytics Web Server in foreground..."
        python3 -m orchestrator_analytics.server "${@:2}" &
        PID=$!
        echo "${PID}" > "${PID_FILE}"
        echo "OpenCode System Analytics Web Server started with PID ${PID} on http://localhost:8765"
        wait "${PID}"
        ;;
    restart)
        "${BASH_SOURCE[0]}" stop
        sleep 1
        "${BASH_SOURCE[0]}" start "${@:2}"
        ;;
    cli|terminal)
        exec python3 -m orchestrator_analytics.cli "${@:2}"
        ;;
    status)
        if pgrep -f "orchestrator_analytics.server" > /dev/null 2>&1; then
            echo "OpenCode System Analytics server is running on http://localhost:8765"
        elif [ -f "${PID_FILE}" ] && kill -0 "$(cat "${PID_FILE}")" 2>/dev/null; then
            echo "OpenCode System Analytics server is running (PID $(cat "${PID_FILE}")) on http://localhost:8765"
        else
            echo "OpenCode System Analytics server is NOT running."
        fi
        ;;
    stop)
        PIDS=$(pgrep -f "orchestrator_analytics.server" || true)
        if [ -n "${PIDS}" ]; then
            echo "Stopping OpenCode System Analytics server processes: ${PIDS}..."
            kill ${PIDS} 2>/dev/null || true
            rm -f "${PID_FILE}"
            echo "Stopped."
        elif [ -f "${PID_FILE}" ]; then
            PID="$(cat "${PID_FILE}")"
            if kill -0 "${PID}" 2>/dev/null; then
                echo "Stopping OpenCode System Analytics server (PID ${PID})..."
                kill "${PID}"
                rm -f "${PID_FILE}"
                echo "Stopped."
            else
                echo "Server process ${PID} not found. Cleaning stale PID file."
                rm -f "${PID_FILE}"
            fi
        else
            echo "No running server process found."
        fi
        ;;
    help|-h|--help)
        echo "OpenCode System Analytics Launcher"
        echo "Usage:"
        echo "  ./launch.sh start         Start web server in background (http://127.0.0.1:8765)"
        echo "  ./launch.sh stop          Stop running web server process"
        echo "  ./launch.sh restart       Restart web server"
        echo "  ./launch.sh status        Check running status of web server"
        echo "  ./launch.sh cli           Render ANSI CLI terminal dashboard report"
        echo "  ./launch.sh web           Start web server in foreground"
        ;;
    *)
        echo "Unknown mode: ${MODE}"
        echo "Usage: ./launch.sh [start|stop|restart|status|cli|web]"
        exit 1
        ;;
esac
