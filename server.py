#!/usr/bin/env python3
"""
REST & Dashboard HTTP Server for OpenCode System Analytics.
Supports FastAPI/Uvicorn if available, with robust zero-dependency http.server fallback.
"""

import sys
import os
import json
import argparse
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

# Ensure package directory is in sys.path when executed directly
PARENT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)

from orchestrator_analytics.config import HOST, PORT, APP_TITLE, PLANS_DIRS
from orchestrator_analytics.collector import AnalyticsCollector
from orchestrator_analytics.engine import AnalyticsEngine

TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")
INDEX_PATH = os.path.join(TEMPLATE_DIR, "index.html")

def delete_plan_file(plan_path: str) -> tuple:
    if not plan_path or not plan_path.lower().endswith('.md'):
        return False, {"error": "forbidden"}, 403
    
    real = os.path.realpath(plan_path)
    if not real.lower().endswith('.md'):
        return False, {"error": "forbidden"}, 403
        
    allowed_dirs = {os.path.realpath(d) for d in PLANS_DIRS}
    parent_dir = os.path.realpath(os.path.dirname(real))
    if parent_dir not in allowed_dirs:
        return False, {"error": "forbidden"}, 403
        
    if not os.path.exists(real):
        return False, {"error": "not found"}, 404
        
    try:
        os.remove(real)
        return True, {"deleted": True, "path": real}, 200
    except OSError as e:
        return False, {"error": str(e)}, 500

def get_html_content() -> str:
    if os.path.exists(INDEX_PATH):
        with open(INDEX_PATH, "r", encoding="utf-8") as f:
            return f.read()
    return f"<html><body><h1>{APP_TITLE} Dashboard</h1><p>index.html template not found.</p></body></html>"

def get_metrics_data() -> dict:
    collector = AnalyticsCollector()
    engine = AnalyticsEngine(collector=collector)
    return engine.compute_all().to_dict()

def get_agents_data() -> list:
    collector = AnalyticsCollector()
    engine = AnalyticsEngine(collector=collector)
    agent_dist = engine.compute_agent_usage_distribution()
    return [v.to_dict() for v in agent_dist.values()]

def get_plans_data() -> list:
    collector = AnalyticsCollector()
    plans = collector.get_plans()
    return [p.to_dict() for p in plans]

def get_sessions_data() -> list:
    collector = AnalyticsCollector()
    engine = AnalyticsEngine(collector=collector)
    return [s.to_dict() for s in engine.data.sessions]

def get_health_data() -> dict:
    return {"status": "ok", "app": APP_TITLE}


# Standard Library Fallback HTTP Request Handler
class AnalyticsHTTPRequestHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Suppress noisy standard request log output
        sys.stderr.write(f"[{self.log_date_time_string()}] {format % args}\n")

    def _send_json(self, data, status=200):
        body = json.dumps(data, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html_content, status=200):
        body = html_content.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path in ("/", "/index.html"):
            self._send_html(get_html_content())
        elif path == "/api/metrics":
            self._send_json(get_metrics_data())
        elif path == "/api/agents":
            self._send_json(get_agents_data())
        elif path == "/api/plans":
            self._send_json(get_plans_data())
        elif path == "/api/sessions":
            self._send_json(get_sessions_data())
        elif path == "/api/health":
            self._send_json(get_health_data())
        else:
            self._send_json({"error": "Not Found", "path": path}, status=404)

    def do_DELETE(self):
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/api/plans":
            query_params = parse_qs(parsed.query)
            plan_path_list = query_params.get("path")
            if not plan_path_list or not plan_path_list[0]:
                self._send_json({"error": "missing path"}, status=400)
                return
            ok, payload, http_status = delete_plan_file(plan_path_list[0])
            self._send_json(payload, status=http_status)
        else:
            self._send_json({"error": "Not Found", "path": path}, status=404)


def run_fastapi_server(host: str, port: int):
    import fastapi
    from fastapi.responses import HTMLResponse, JSONResponse
    import uvicorn

    app = fastapi.FastAPI(title=APP_TITLE)

    @app.get("/", response_class=HTMLResponse)
    async def render_dashboard():
        return HTMLResponse(content=get_html_content())

    @app.get("/api/metrics")
    async def api_metrics():
        return JSONResponse(content=get_metrics_data())

    @app.get("/api/agents")
    async def api_agents():
        return JSONResponse(content=get_agents_data())

    @app.get("/api/plans")
    async def api_plans():
        return JSONResponse(content=get_plans_data())

    @app.delete("/api/plans")
    async def api_delete_plan(path: str = fastapi.Query(...)):
        ok, payload, http_status = delete_plan_file(path)
        return JSONResponse(content=payload, status_code=http_status)

    @app.get("/api/sessions")
    async def api_sessions():
        return JSONResponse(content=get_sessions_data())

    @app.get("/api/health")
    async def api_health():
        return JSONResponse(content=get_health_data())

    print(f"🚀 Starting FastAPI server on http://{host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="info")


def run_stdlib_server(host: str, port: int):
    server_address = (host, port)
    httpd = HTTPServer(server_address, AnalyticsHTTPRequestHandler)
    print(f"🚀 Starting HTTP server on http://{host}:{port}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print(f"\nStopping {APP_TITLE} server.")
        httpd.server_close()


def main():
    parser = argparse.ArgumentParser(description=APP_TITLE)
    parser.add_argument("--host", default=HOST, help=f"Host IP to bind (default: {HOST})")
    parser.add_argument("--port", type=int, default=PORT, help=f"Port to bind (default: {PORT})")
    args = parser.parse_args()

    try:
        import fastapi
        import uvicorn
        run_fastapi_server(args.host, args.port)
    except ImportError:
        run_stdlib_server(args.host, args.port)


if __name__ == "__main__":
    main()
