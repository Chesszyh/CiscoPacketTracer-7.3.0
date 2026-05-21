"""Local PT 7.3 command bridge server.

This is a small compatibility bridge for the Packet Tracer Script Module
bootstrap loop.  It intentionally lives in pt730 instead of patching the
upstream MCP-Packet-Tracer submodule so the published repository can use the
upstream catalog as a clean submodule while keeping the PT 7.3 request-tagging
fix local and testable.
"""

from __future__ import annotations

import http.server
import json
import threading
import time
import urllib.parse
from http.server import ThreadingHTTPServer
from queue import Empty, Queue


class PTCommandBridge:
    def __init__(self, host: str = "127.0.0.1", port: int = 54321) -> None:
        self.host = host
        self.port = port
        self._queue: Queue[str] = Queue()
        self._results: Queue[str] = Queue()
        self._tagged_results: dict[str, Queue[str]] = {}
        self._tagged_lock = threading.Lock()
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._last_poll_time = 0.0

    def start(self) -> None:
        bridge = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                parsed = urllib.parse.urlparse(self.path)
                path = parsed.path
                query = urllib.parse.parse_qs(parsed.query)
                if path == "/next":
                    try:
                        command = bridge._queue.get_nowait()
                    except Empty:
                        command = ""
                    bridge._last_poll_time = time.time()
                    self._respond(200, command)
                elif path == "/ping":
                    bridge._last_poll_time = time.time()
                    self._respond(200, "pong")
                elif path == "/status":
                    ago = time.time() - bridge._last_poll_time
                    connected = bridge._last_poll_time > 0 and ago < 5.0
                    self._respond(200, json.dumps({"connected": connected, "last_poll_ago": round(ago, 1)}))
                elif path == "/result":
                    request_id = query.get("request_id", [""])[0]
                    try:
                        result = bridge._get_result(request_id)
                        self._respond(200, result)
                    except Empty:
                        self._respond(204, "")
                else:
                    self._respond(404, "")

            def do_POST(self) -> None:  # noqa: N802
                parsed = urllib.parse.urlparse(self.path)
                path = parsed.path
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length).decode("utf-8") if length else ""
                if path == "/result":
                    bridge._put_result(body)
                    self._respond(200, "ok")
                elif path == "/queue":
                    if body:
                        bridge._queue.put(body)
                    self._respond(200, "queued")
                else:
                    self._respond(404, "")

            def log_message(self, fmt: str, *args: object) -> None:
                return

            def _respond(self, status: int, body: str) -> None:
                payload = body.encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

        self._server = ThreadingHTTPServer((self.host, self.port), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()
            self._server.server_close()
        if self._thread:
            self._thread.join(timeout=2.0)

    def bootstrap_script(self) -> str:
        url = f"http://{self.host}:{self.port}/next"
        return (
            'window.webview.evaluateJavaScriptAsync("setInterval(function(){'
            f"var x=new XMLHttpRequest();x.open('GET','{url}',true);"
            "x.onload=function(){if(x.status===200&&x.responseText){$se('runCode',x.responseText)}};"
            "x.onerror=function(){};x.send()},500)\");"
        )

    def queue(self, command: str) -> None:
        self._queue.put(command)

    def _get_result(self, request_id: str) -> str:
        if not request_id:
            return self._results.get(timeout=9.0)
        with self._tagged_lock:
            queue = self._tagged_results.setdefault(request_id, Queue())
        result = queue.get(timeout=9.0)
        if queue.empty():
            with self._tagged_lock:
                if self._tagged_results.get(request_id) is queue and queue.empty():
                    self._tagged_results.pop(request_id, None)
        return result

    def _put_result(self, body: str) -> None:
        request_id = ""
        try:
            payload = json.loads(body)
            if isinstance(payload, dict):
                request_id = str(payload.get("pt730_request_id", ""))
        except json.JSONDecodeError:
            request_id = ""
        if not request_id:
            self._results.put(body)
            return
        with self._tagged_lock:
            queue = self._tagged_results.setdefault(request_id, Queue())
        queue.put(body)
