"""Loopback-only web server, adapted from credential-ui-demo's local UI."""
from datetime import datetime
import hmac
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import secrets
import threading
import time
from urllib.parse import urlsplit

from .errors import SetupError
from .ui_errors import public_error
from .ui_model import ConfigurationUI
from .ui_storage import write_json, instance_lock

ASSETS = Path(__file__).resolve().parents[2] / "assets"
IDLE_SECONDS = 3600


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False

    def __init__(self, directory, options):
        self.model = ConfigurationUI(directory, options)
        super().__init__(("127.0.0.1", 0), Handler)
        self.origin = f"http://127.0.0.1:{self.server_port}"
        self.instance = secrets.token_hex(16)
        # Cookies are scoped by hostname, not port. Parallel local sessions
        # must not overwrite each other's authentication cookie.
        self.cookie_name = "setup_session_" + self.instance
        self.launch_token = secrets.token_urlsafe(24)
        self.cookie_token = secrets.token_urlsafe(32)
        self.csrf = secrets.token_urlsafe(32)
        self.last_use = time.monotonic()
        self.last_use_epoch = time.time()
        self.session_lock = threading.RLock()
        self.closed = threading.Event()

    def lifetime(self, renew=False):
        with self.session_lock:
            remaining = IDLE_SECONDS - (time.monotonic() - self.last_use)
            if remaining <= 0:
                raise SetupError("session_expired")
            if renew:
                self.last_use = time.monotonic()
                self.last_use_epoch = time.time()
                remaining = IDLE_SECONDS
            expires = datetime.fromtimestamp(self.last_use_epoch + IDLE_SECONDS).astimezone()
            return {"idle_timeout_minutes": 60, "remaining_seconds": max(0, int(remaining)), "expires_at": expires.isoformat(timespec="seconds"),
                    "expires_at_display": expires.strftime("%Y-%m-%d %H:%M:%S %Z")}

    def close_later(self):
        threading.Thread(target=self.shutdown, daemon=True).start()

    def inactivity_watch(self):
        while not self.closed.wait(15):
            if time.monotonic() - self.last_use > IDLE_SECONDS:
                logging.info("idle_timeout instance=%s", self.instance)
                self.shutdown()
                return


class Handler(BaseHTTPRequestHandler):
    server_version = "SetupAIhub"

    def log_message(self, *_):
        pass  # No request URLs, bodies, cookies or keys in access logs.

    def send(self, code, data, content_type="application/json; charset=utf-8", cookie=None):
        raw = json.dumps(data, ensure_ascii=False).encode() if isinstance(data, dict) else data
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Security-Policy", "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()
        self.wfile.write(raw)

    def host_ok(self):
        return self.headers.get("Host") == self.server.origin.removeprefix("http://")

    def authenticated(self):
        cookie = SimpleCookie()
        try:
            cookie.load(self.headers.get("Cookie", ""))
            name = self.server.cookie_name
            value = cookie[name].value if name in cookie else ""
        except Exception:
            return False
        return hmac.compare_digest(value, self.server.cookie_token)

    def do_GET(self):
        try:
            if not self.host_ok():
                return self.send(403, {"error": "invalid_host", "message": "请使用 Agent 提供的本机链接。"})
            path = urlsplit(self.path).path
            if path == "/health":
                return self.send(200, {"app": "setup-aihub", "instance": self.server.instance, "lifetime": self.server.lifetime()})
            if path == "/api/state":
                if not self.authenticated():
                    return self.send(401, {"error": "session_required", "message": "请从 Agent 提供的链接打开配置页。"})
                with self.server.model.lock:
                    state = self.server.model.public()
                    identity = state.get("identity")
                    if identity:
                        from .consumers import fingerprint
                        state["identity_id"] = fingerprint(identity)
                    return self.send(200, {"state": state, "csrf": self.server.csrf, "lifetime": self.server.lifetime()})
            routes = {"/": ("index.html", "text/html; charset=utf-8"), "/app.js": ("app.js", "text/javascript; charset=utf-8"), "/style.css": ("style.css", "text/css; charset=utf-8")}
            if path not in routes:
                return self.send(404, {"error": "not_found", "message": "页面不存在。"})
            filename, mime = routes[path]
            self.send(200, (ASSETS / filename).read_bytes(), mime)
        except SetupError as error:
            self.send(410, public_error(error))
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as error:
            logging.error("get_failed type=%s", type(error).__name__)
            self.send(500, public_error(error))

    def do_POST(self):
        try:
            if not self.host_ok() or self.headers.get("Origin") != self.server.origin:
                return self.send(403, {"error": "invalid_origin", "message": "请求来源不匹配，请从本机配置页操作。"})
            if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                return self.send(415, {"error": "json_required", "message": "请求格式不正确。"})
            try:
                size = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                size = -1
            if not 0 < size <= 32768:
                return self.send(413, {"error": "invalid_size", "message": "输入内容过长或为空。"})
            self.connection.settimeout(10)
            try:
                data = json.loads(self.rfile.read(size))
                if not isinstance(data, dict):
                    raise ValueError()
            except (ValueError, UnicodeError):
                return self.send(400, {"error": "invalid_json", "message": "请求内容无法识别。"})
            path = urlsplit(self.path).path
            if path == "/api/session":
                token = data.get("token", "")
                if not isinstance(token, str) or not hmac.compare_digest(token, self.server.launch_token):
                    return self.send(401, {"error": "invalid_token", "message": "链接已失效，请让 Agent 重新打开配置页。"})
                return self.send(200, {"csrf": self.server.csrf, "lifetime": self.server.lifetime(renew=True)},
                                 cookie=f"{self.server.cookie_name}={self.server.cookie_token}; HttpOnly; SameSite=Strict; Path=/")
            if not self.authenticated() or not hmac.compare_digest(self.headers.get("X-Setup-CSRF", ""), self.server.csrf):
                return self.send(403, {"error": "unauthorized", "message": "会话失效，请重新打开配置页。"})
            self.server.lifetime(renew=True)
            if path == "/api/stop":
                self.send(200, {"stopped": True})
                self.server.close_later()
                return
            if not path.startswith("/api/action/"):
                return self.send(404, {"error": "not_found", "message": "操作不存在。"})
            action = path.removeprefix("/api/action/")
            result = self.server.model.action(action, data)
            if result.get("identity"):
                from .consumers import fingerprint
                result["identity_id"] = fingerprint(result["identity"])
            # Action is user input; log only the resulting known state and task.
            logging.info("operation_complete phase=%s task=%s", result["phase"], result.get("task_id"))
            self.send(200, {"state": result, "lifetime": self.server.lifetime()})
        except SetupError as error:
            logging.warning("operation_rejected reason=%s", error.reason)
            self.send(409, public_error(error))
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as error:
            logging.error("operation_failed type=%s", type(error).__name__)
            self.send(500, public_error(error))


def run(directory, options):
    with instance_lock(directory):
        logging.basicConfig(handlers=[RotatingFileHandler(Path(directory) / "server.log", maxBytes=512000, backupCount=2, encoding="utf-8")],
                            level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
        with Server(directory, options) as server:
            write_json(Path(directory) / "server.json", {"schema": 1, "pid": os.getpid(), "instance": server.instance,
                "origin": server.origin, "token": server.launch_token, "context": options})
            logging.info("started instance=%s port=%s", server.instance, server.server_port)
            threading.Thread(target=server.inactivity_watch, daemon=True).start()
            try:
                server.serve_forever(poll_interval=0.25)
            finally:
                server.closed.set()
                server.model.discard()
                server.model.book.login = None
                logging.info("stopped instance=%s", server.instance)
