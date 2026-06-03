from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import deque
from dataclasses import dataclass
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


DEFAULT_LISTEN_HOST = "127.0.0.1"
DEFAULT_LISTEN_PORT = 18181
DEFAULT_UPSTREAM_BASE_URL = "https://api.deepseek.com/v1"
DEFAULT_RETAINPDF_MODEL = "deepseek-v4-flash"
DEFAULT_MAX_CONCURRENT = 5
DEFAULT_MAX_REQUESTS_PER_MINUTE = 0
DEFAULT_ACQUIRE_TIMEOUT_SECONDS = 3600.0
DEFAULT_UPSTREAM_TIMEOUT_SECONDS = 180.0
DEFAULT_MOCK_BALANCE_TOTAL = "999.00"
DEFAULT_UPSTREAM_TRANSPORT = "auto"
DEFAULT_UPSTREAM_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)
GUI_START_REQUESTED = 70
WINDOWS_HIDDEN_WINDOW = 0
LOG_FILE_NAME = "retainpdf-relay-proxy.log"
ASSETS_DIR_NAME = "assets"
APP_ICON_PNG_NAME = "retainpdf-relay-proxy.png"

ENV_PREFIX = "RETAINPDF_PROXY_"
HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}


def application_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    source_dir = Path(__file__).resolve().parent
    if source_dir.name == "src":
        return source_dir.parent
    return source_dir


def resource_base_dir() -> Path:
    bundle_dir = getattr(sys, "_MEIPASS", "")
    if getattr(sys, "frozen", False) and bundle_dir:
        return Path(str(bundle_dir)).resolve()
    return application_dir()


def resource_path(*parts: str) -> Path:
    return resource_base_dir().joinpath(*parts)


def default_log_path() -> Path:
    return application_dir() / LOG_FILE_NAME


def ensure_background_stdio() -> None:
    if sys.stdout is not None and sys.stderr is not None:
        return
    log_path = default_log_path()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_file = log_path.open("a", encoding="utf-8", buffering=1)
    if sys.stdout is None:
        sys.stdout = log_file  # type: ignore[assignment]
    if sys.stderr is None:
        sys.stderr = log_file  # type: ignore[assignment]
    print(f"\n--- RetainPDF relay proxy log {time.strftime('%Y-%m-%d %H:%M:%S')} ---", flush=True)


def hidden_subprocess_kwargs() -> dict[str, Any]:
    if os.name != "nt":
        return {}
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = WINDOWS_HIDDEN_WINDOW
    return {
        "startupinfo": startupinfo,
        "creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0),
    }


def enable_windows_dpi_awareness() -> None:
    if os.name != "nt":
        return
    try:
        import ctypes

        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


def configure_tk_font_rendering(root: Any) -> None:
    try:
        pixels_per_inch = float(root.winfo_fpixels("1i"))
        root.tk.call("tk", "scaling", max(1.0, pixels_per_inch / 72.0))
    except Exception:
        pass


def apply_tk_window_icon(root: Any) -> None:
    icon_path = resource_path(ASSETS_DIR_NAME, APP_ICON_PNG_NAME)
    if not icon_path.exists():
        return
    try:
        import tkinter as tk

        icon = tk.PhotoImage(file=str(icon_path))
        root.iconphoto(True, icon)
        root._retainpdf_relay_icon = icon
    except Exception:
        pass

    try:
        import tkinter.font as tkfont

        font_family = "Microsoft YaHei UI"
        font_specs = {
            "TkDefaultFont": {"family": font_family, "size": 10},
            "TkTextFont": {"family": font_family, "size": 10},
            "TkMenuFont": {"family": font_family, "size": 10},
            "TkCaptionFont": {"family": font_family, "size": 10},
            "TkHeadingFont": {"family": font_family, "size": 10, "weight": "bold"},
            "TkFixedFont": {"family": "Cascadia Mono", "size": 10},
        }
        for font_name, options in font_specs.items():
            try:
                tkfont.nametofont(font_name).configure(**options)
            except Exception:
                continue
        root.option_add("*Font", "TkDefaultFont")
        root.option_add("*Menu.font", "TkMenuFont")
    except Exception:
        pass


def background_python_executable() -> str:
    executable = Path(sys.executable).resolve()
    if os.name == "nt":
        sibling = executable.with_name("pythonw.exe")
        if sibling.exists():
            return str(sibling)
        discovered = shutil.which("pythonw.exe")
        if discovered:
            return discovered
    return str(executable)


def launch_background_process(
    command: list[str],
    *,
    cwd: str,
    env: dict[str, str] | None = None,
) -> subprocess.Popen[Any]:
    log_path = default_log_path()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_file = log_path.open("a", encoding="utf-8", buffering=1)
    try:
        process = subprocess.Popen(
            command,
            cwd=cwd,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            **hidden_subprocess_kwargs(),
        )
    except Exception:
        log_file.close()
        raise
    log_file.close()
    return process


@dataclass(frozen=True)
class ProxyConfig:
    listen_host: str = DEFAULT_LISTEN_HOST
    listen_port: int = DEFAULT_LISTEN_PORT
    upstream_base_url: str = DEFAULT_UPSTREAM_BASE_URL
    upstream_api_key: str = ""
    upstream_model: str = ""
    retainpdf_exe_path: str = ""
    max_concurrent: int = DEFAULT_MAX_CONCURRENT
    max_requests_per_minute: int = DEFAULT_MAX_REQUESTS_PER_MINUTE
    acquire_timeout_seconds: float = DEFAULT_ACQUIRE_TIMEOUT_SECONDS
    upstream_timeout_seconds: float = DEFAULT_UPSTREAM_TIMEOUT_SECONDS
    upstream_transport: str = DEFAULT_UPSTREAM_TRANSPORT
    upstream_user_agent: str = DEFAULT_UPSTREAM_USER_AGENT
    forward_authorization: bool = True
    log_requests: bool = True
    patch_desktop_config: bool = False
    desktop_config_path: str = ""
    retainpdf_api_key: str = ""
    mock_balance: bool = True
    mock_balance_total: str = DEFAULT_MOCK_BALANCE_TOTAL


class RelayState:
    def __init__(self, config: ProxyConfig) -> None:
        self.config = config
        self.semaphore = threading.BoundedSemaphore(config.max_concurrent)
        self.lock = threading.Lock()
        self.rate_condition = threading.Condition(threading.Lock())
        self.rate_timestamps: deque[float] = deque()
        self.active = 0
        self.total = 0

    def acquire(self) -> bool:
        return self.semaphore.acquire(timeout=max(0.0, self.config.acquire_timeout_seconds))

    def acquire_rate_slot(self) -> tuple[bool, float]:
        limit = self.config.max_requests_per_minute
        if limit <= 0:
            return True, 0.0

        started = time.monotonic()
        deadline = started + max(0.0, self.config.acquire_timeout_seconds)
        with self.rate_condition:
            while True:
                now = time.monotonic()
                while self.rate_timestamps and now - self.rate_timestamps[0] >= 60.0:
                    self.rate_timestamps.popleft()

                if len(self.rate_timestamps) < limit:
                    self.rate_timestamps.append(now)
                    return True, now - started

                wait_seconds = max(0.05, 60.0 - (now - self.rate_timestamps[0]))
                remaining = deadline - now
                if remaining <= 0:
                    return False, time.monotonic() - started
                self.rate_condition.wait(timeout=min(wait_seconds, remaining))

    def mark_started(self) -> tuple[int, int]:
        with self.lock:
            self.active += 1
            self.total += 1
            return self.total, self.active

    def mark_finished(self) -> int:
        with self.lock:
            self.active = max(0, self.active - 1)
            return self.active

    def release(self) -> None:
        self.semaphore.release()


def parse_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if not text:
        return default
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


def parse_int(value: Any, default: int, *, minimum: int = 1, maximum: int | None = None) -> int:
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        parsed = default
    parsed = max(minimum, parsed)
    if maximum is not None:
        parsed = min(maximum, parsed)
    return parsed


def parse_float(value: Any, default: float, *, minimum: float = 0.0) -> float:
    try:
        parsed = float(str(value).strip())
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, parsed)


def normalize_upstream_transport(value: Any) -> str:
    text = str(value or DEFAULT_UPSTREAM_TRANSPORT).strip().lower()
    if text in {"auto", "curl", "urllib"}:
        return text
    return DEFAULT_UPSTREAM_TRANSPORT


def normalize_base_url(base_url: str) -> str:
    normalized = (base_url or DEFAULT_UPSTREAM_BASE_URL).strip().rstrip("/")
    if normalized.endswith("/chat/completions"):
        normalized = normalized[: -len("/chat/completions")]
    return normalized


def chat_completions_url(base_url: str) -> str:
    return f"{normalize_base_url(base_url)}/chat/completions"


def load_json_config(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as file:
        payload = json.load(file)
    if not isinstance(payload, dict):
        raise ValueError(f"Config must be a JSON object: {path}")
    return payload


def default_config_path() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().with_name("retainpdf-relay-proxy.json")
    return application_dir() / "retainpdf-relay-proxy.json"


def resolved_config_path(raw_path: str = "") -> Path:
    if raw_path.strip():
        return Path(raw_path).expanduser().resolve()
    return default_config_path()


def save_json_config(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)
        file.write("\n")


def env_value(name: str, default: Any) -> Any:
    return os.environ.get(f"{ENV_PREFIX}{name.upper()}", default)


def build_config(config_path: Path | None) -> ProxyConfig:
    file_config = load_json_config(config_path)

    def value(name: str, default: Any) -> Any:
        return env_value(name, file_config.get(name, default))

    return ProxyConfig(
        listen_host=str(value("listen_host", DEFAULT_LISTEN_HOST)).strip() or DEFAULT_LISTEN_HOST,
        listen_port=parse_int(value("listen_port", DEFAULT_LISTEN_PORT), DEFAULT_LISTEN_PORT, minimum=1, maximum=65535),
        upstream_base_url=normalize_base_url(str(value("upstream_base_url", DEFAULT_UPSTREAM_BASE_URL))),
        upstream_api_key=str(value("upstream_api_key", "") or "").strip(),
        upstream_model=str(value("upstream_model", "") or "").strip(),
        retainpdf_exe_path=str(value("retainpdf_exe_path", "") or "").strip(),
        max_concurrent=parse_int(value("max_concurrent", DEFAULT_MAX_CONCURRENT), DEFAULT_MAX_CONCURRENT, minimum=1),
        max_requests_per_minute=parse_int(
            value("max_requests_per_minute", DEFAULT_MAX_REQUESTS_PER_MINUTE),
            DEFAULT_MAX_REQUESTS_PER_MINUTE,
            minimum=0,
        ),
        acquire_timeout_seconds=parse_float(
            value("acquire_timeout_seconds", DEFAULT_ACQUIRE_TIMEOUT_SECONDS),
            DEFAULT_ACQUIRE_TIMEOUT_SECONDS,
            minimum=0.0,
        ),
        upstream_timeout_seconds=parse_float(
            value("upstream_timeout_seconds", DEFAULT_UPSTREAM_TIMEOUT_SECONDS),
            DEFAULT_UPSTREAM_TIMEOUT_SECONDS,
            minimum=1.0,
        ),
        upstream_transport=normalize_upstream_transport(value("upstream_transport", DEFAULT_UPSTREAM_TRANSPORT)),
        upstream_user_agent=str(value("upstream_user_agent", DEFAULT_UPSTREAM_USER_AGENT) or "").strip()
        or DEFAULT_UPSTREAM_USER_AGENT,
        forward_authorization=parse_bool(value("forward_authorization", True), True),
        log_requests=parse_bool(value("log_requests", True), True),
        patch_desktop_config=parse_bool(value("patch_desktop_config", False), False),
        desktop_config_path=str(value("desktop_config_path", "") or "").strip(),
        retainpdf_api_key=str(value("retainpdf_api_key", "") or "").strip(),
        mock_balance=parse_bool(value("mock_balance", True), True),
        mock_balance_total=str(value("mock_balance_total", DEFAULT_MOCK_BALANCE_TOTAL) or "").strip()
        or DEFAULT_MOCK_BALANCE_TOTAL,
    )


def redact_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    if not parsed.netloc:
        return url
    return urllib.parse.urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))


def response_json(handler: BaseHTTPRequestHandler, status: int, payload: dict[str, Any]) -> None:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(data)))
    add_cors_headers(handler)
    handler.end_headers()
    handler.wfile.write(data)


def add_cors_headers(handler: BaseHTTPRequestHandler) -> None:
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
    handler.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")


def request_path(path: str) -> str:
    return urllib.parse.urlparse(path).path.rstrip("/")


def is_chat_completions_path(path: str) -> bool:
    normalized = request_path(path)
    return normalized in {"/v1/chat/completions", "/chat/completions"} or normalized.endswith(
        "/chat/completions"
    )


def is_models_path(path: str) -> bool:
    normalized = request_path(path)
    return normalized in {"/v1/models", "/models"} or normalized.endswith("/models")


def is_balance_path(path: str) -> bool:
    normalized = request_path(path)
    return normalized in {"/user/balance", "/v1/user/balance"} or normalized.endswith("/user/balance")


def is_health_path(path: str) -> bool:
    return request_path(path) in {"", "/", "/health", "/v1/health"}


def read_request_body(handler: BaseHTTPRequestHandler) -> bytes:
    raw_length = handler.headers.get("Content-Length", "0")
    try:
        length = max(0, int(raw_length))
    except ValueError:
        length = 0
    return handler.rfile.read(length)


def build_upstream_headers(
    handler: BaseHTTPRequestHandler,
    *,
    config: ProxyConfig,
    body: dict[str, Any],
) -> dict[str, str]:
    headers = {
        "Content-Type": "application/json",
        "Accept": "text/event-stream" if body.get("stream") is True else "application/json",
        "User-Agent": config.upstream_user_agent,
    }
    if config.upstream_api_key:
        headers["Authorization"] = f"Bearer {config.upstream_api_key}"
    elif config.forward_authorization:
        authorization = handler.headers.get("Authorization", "").strip()
        if authorization:
            headers["Authorization"] = authorization
    return headers


def copy_response_headers(handler: BaseHTTPRequestHandler, headers: Any, *, include_length: bool) -> None:
    for name, value in headers.items():
        lower_name = str(name).lower()
        if lower_name in HOP_BY_HOP_HEADERS:
            continue
        if not include_length and lower_name == "content-length":
            continue
        handler.send_header(str(name), str(value))
    add_cors_headers(handler)


def write_upstream_http_error(handler: BaseHTTPRequestHandler, exc: urllib.error.HTTPError) -> None:
    body = exc.read()
    handler.send_response(exc.code)
    copy_response_headers(handler, exc.headers, include_length=False)
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    if body:
        handler.wfile.write(body)


CURL_STATUS_MARKER = b"\n__RETAINPDF_CURL_STATUS__:"


def curl_path() -> str | None:
    return shutil.which("curl.exe") or shutil.which("curl")


def should_use_curl_transport(config: ProxyConfig) -> bool:
    if config.upstream_transport == "urllib":
        return False
    if config.upstream_transport == "curl":
        return True
    return curl_path() is not None


def post_upstream_with_curl(
    *,
    url: str,
    body: bytes,
    headers: dict[str, str],
    timeout_seconds: float,
) -> tuple[int, str, bytes]:
    executable = curl_path()
    if not executable:
        raise FileNotFoundError("curl executable was not found")

    timeout = str(max(1, int(timeout_seconds)))
    command = [
        executable,
        "-sS",
        "-L",
        "--compressed",
        "--connect-timeout",
        "20",
        "--max-time",
        timeout,
        "-X",
        "POST",
        url,
    ]
    for name, value in headers.items():
        command.extend(["-H", f"{name}: {value}"])
    command.extend(
        [
            "--data-binary",
            "@-",
            "-w",
            "\n__RETAINPDF_CURL_STATUS__:%{http_code}:%{content_type}",
        ]
    )

    result = subprocess.run(
        command,
        input=body,
        capture_output=True,
        timeout=max(2.0, timeout_seconds + 5.0),
        check=False,
        **hidden_subprocess_kwargs(),
    )
    stdout = result.stdout or b""
    stderr_text = (result.stderr or b"").decode("utf-8", errors="replace").strip()
    marker_index = stdout.rfind(CURL_STATUS_MARKER)
    if result.returncode != 0:
        raise RuntimeError(f"curl exited with {result.returncode}: {stderr_text}")
    if marker_index < 0:
        raise RuntimeError(f"curl response marker missing: {stderr_text or stdout[:200]!r}")

    response_body = stdout[:marker_index]
    meta = stdout[marker_index + len(CURL_STATUS_MARKER) :].decode("utf-8", errors="replace").strip()
    status_text, _, content_type = meta.partition(":")
    try:
        status = int(status_text)
    except ValueError as exc:
        raise RuntimeError(f"curl returned invalid status marker: {meta!r}") from exc
    return status, content_type or "application/json", response_body


def read_local_url(url: str, *, timeout_seconds: float = 5.0) -> tuple[int, str]:
    request = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        status = int(getattr(response, "status", 200) or 200)
        body = response.read().decode("utf-8", errors="replace")
        return status, body


def wait_for_local_proxy_ready(local_origin: str, retainpdf_base_url: str, *, mock_balance: bool) -> bool:
    checks = [
        ("health", f"{local_origin}/health"),
        ("models", f"{retainpdf_base_url}/models"),
    ]
    if mock_balance:
        checks.append(("balance", f"{local_origin}/user/balance"))

    deadline = time.monotonic() + 8.0
    last_error = ""
    while time.monotonic() < deadline:
        try:
            for label, url in checks:
                status, body = read_local_url(url, timeout_seconds=2.0)
                if status < 200 or status >= 300:
                    raise RuntimeError(f"{label} returned HTTP {status}: {body[:160]}")
            print("Relay HTTP self-check passed.", flush=True)
            for label, url in checks:
                print(f"  {label}: {url}", flush=True)
            return True
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            time.sleep(0.25)

    print(f"Relay HTTP self-check failed: {last_error}", file=sys.stderr, flush=True)
    return False


def proxy_launch_command(config_path: Path, retainpdf_exe: str = "") -> list[str]:
    if getattr(sys, "frozen", False):
        command = [str(Path(sys.executable).resolve())]
    else:
        command = [background_python_executable(), str(Path(__file__).resolve())]
    command.extend(["--config", str(config_path)])
    if retainpdf_exe.strip():
        command.extend(["--launch", retainpdf_exe.strip()])
    return command


def is_retainpdf_process_running() -> bool:
    if os.name != "nt":
        return False
    try:
        result = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq RetainPDF.exe"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
            **hidden_subprocess_kwargs(),
        )
    except Exception:
        return False
    return "RetainPDF.exe" in result.stdout


def config_payload_from_gui_values(
    *,
    existing: dict[str, Any],
    upstream_base_url: str,
    upstream_api_key: str,
    upstream_model: str,
    retainpdf_exe_path: str,
    max_concurrent: str,
    max_requests_per_minute: str,
    patch_desktop_config: bool,
    mock_balance: bool,
) -> dict[str, Any]:
    payload = dict(existing)
    payload["listen_host"] = str(payload.get("listen_host") or DEFAULT_LISTEN_HOST)
    payload["listen_port"] = parse_int(payload.get("listen_port", DEFAULT_LISTEN_PORT), DEFAULT_LISTEN_PORT, minimum=1, maximum=65535)
    payload["upstream_base_url"] = normalize_base_url(upstream_base_url)
    payload["upstream_api_key"] = upstream_api_key.strip()
    payload["upstream_model"] = upstream_model.strip()
    payload["retainpdf_exe_path"] = retainpdf_exe_path.strip()
    payload["max_concurrent"] = parse_int(max_concurrent, DEFAULT_MAX_CONCURRENT, minimum=1)
    payload["max_requests_per_minute"] = parse_int(
        max_requests_per_minute,
        DEFAULT_MAX_REQUESTS_PER_MINUTE,
        minimum=0,
    )
    payload["acquire_timeout_seconds"] = parse_float(
        payload.get("acquire_timeout_seconds", DEFAULT_ACQUIRE_TIMEOUT_SECONDS),
        DEFAULT_ACQUIRE_TIMEOUT_SECONDS,
        minimum=0.0,
    )
    payload["upstream_timeout_seconds"] = parse_float(
        payload.get("upstream_timeout_seconds", DEFAULT_UPSTREAM_TIMEOUT_SECONDS),
        DEFAULT_UPSTREAM_TIMEOUT_SECONDS,
        minimum=1.0,
    )
    payload["upstream_transport"] = normalize_upstream_transport(
        payload.get("upstream_transport", DEFAULT_UPSTREAM_TRANSPORT)
    )
    payload["upstream_user_agent"] = str(
        payload.get("upstream_user_agent", DEFAULT_UPSTREAM_USER_AGENT) or DEFAULT_UPSTREAM_USER_AGENT
    )
    payload["forward_authorization"] = parse_bool(payload.get("forward_authorization", True), True)
    payload["log_requests"] = parse_bool(payload.get("log_requests", True), True)
    payload["patch_desktop_config"] = bool(patch_desktop_config)
    payload["desktop_config_path"] = str(payload.get("desktop_config_path", "") or "")
    payload["retainpdf_api_key"] = str(payload.get("retainpdf_api_key", "") or "")
    payload["mock_balance"] = bool(mock_balance)
    payload["mock_balance_total"] = str(payload.get("mock_balance_total", DEFAULT_MOCK_BALANCE_TOTAL) or DEFAULT_MOCK_BALANCE_TOTAL)
    return payload


def run_main_config_gui(config_path: Path, *, start_in_current_process: bool = False) -> int:
    try:
        import tkinter as tk
        from tkinter import filedialog
        from tkinter import messagebox
        from tkinter import ttk
    except Exception as exc:
        print(f"GUI is not available: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 4

    try:
        existing = load_json_config(config_path)
    except Exception as exc:
        existing = {}
        load_error = f"Failed to load config: {type(exc).__name__}: {exc}"
    else:
        load_error = ""

    initial = build_config(config_path if config_path.exists() and not load_error else None)
    start_requested = False

    enable_windows_dpi_awareness()
    root = tk.Tk()
    apply_tk_window_icon(root)
    configure_tk_font_rendering(root)
    root.title("RetainPDF 中转站助手")
    root.geometry("960x680")
    root.minsize(880, 630)

    palette = {
        "app_bg": "#f6f7fb",
        "card_bg": "#ffffff",
        "card_border": "#d9dee8",
        "sidebar_bg": "#111827",
        "sidebar_muted": "#9ca3af",
        "sidebar_text": "#f9fafb",
        "text": "#111827",
        "muted": "#667085",
        "field": "#344054",
        "primary": "#2563eb",
        "primary_hover": "#1d4ed8",
        "primary_pressed": "#1e40af",
        "secondary_hover": "#f2f4f7",
        "accent": "#14b8a6",
        "success_bg": "#dcfce7",
        "success_text": "#166534",
    }
    root.configure(bg=palette["app_bg"])

    try:
        style = ttk.Style(root)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        default_font = ("Microsoft YaHei UI", 10)
        style.configure(".", font=default_font)
        style.configure("App.TFrame", background=palette["app_bg"])
        style.configure("Card.TFrame", background=palette["card_bg"])
        style.configure("Sidebar.TFrame", background=palette["sidebar_bg"])
        style.configure(
            "TEntry",
            padding=9,
            fieldbackground=palette["card_bg"],
            bordercolor=palette["card_border"],
            lightcolor=palette["card_border"],
            darkcolor=palette["card_border"],
        )
        style.configure(
            "TSpinbox",
            padding=7,
            fieldbackground=palette["card_bg"],
            bordercolor=palette["card_border"],
            lightcolor=palette["card_border"],
            darkcolor=palette["card_border"],
        )
        style.configure("TCheckbutton", background=palette["card_bg"], foreground=palette["field"])
        style.configure("TButton", padding=(16, 9), borderwidth=0, focusthickness=0)
        style.configure(
            "Secondary.TButton",
            background=palette["card_bg"],
            foreground=palette["field"],
            bordercolor=palette["card_border"],
        )
        style.configure(
            "Primary.TButton",
            background=palette["primary"],
            foreground="#ffffff",
            padding=(20, 10),
            borderwidth=0,
        )
        style.map(
            "Secondary.TButton",
            background=[("active", palette["secondary_hover"]), ("pressed", "#e5e7eb")],
            foreground=[("disabled", "#98a2b3")],
        )
        style.map(
            "Primary.TButton",
            background=[
                ("active", palette["primary_hover"]),
                ("pressed", palette["primary_pressed"]),
                ("disabled", "#93c5fd"),
            ],
            foreground=[("disabled", "#eff6ff")],
        )
    except Exception:
        pass

    upstream_base_url_var = tk.StringVar(value=initial.upstream_base_url)
    upstream_api_key_var = tk.StringVar(value=initial.upstream_api_key)
    upstream_model_var = tk.StringVar(value=initial.upstream_model)
    max_concurrent_var = tk.StringVar(value=str(initial.max_concurrent))
    max_requests_per_minute_var = tk.StringVar(value=str(initial.max_requests_per_minute))
    retainpdf_exe_var = tk.StringVar(value=initial.retainpdf_exe_path)
    patch_desktop_config_var = tk.BooleanVar(value=initial.patch_desktop_config)
    mock_balance_var = tk.BooleanVar(value=initial.mock_balance)
    show_key_var = tk.BooleanVar(value=False)
    status_var = tk.StringVar(value=load_error or "准备就绪，填写配置后可保存或直接启动。")
    status_badge_var = tk.StringVar(value="未启动")
    config_path_var = tk.StringVar(value=str(config_path))
    log_path_var = tk.StringVar(value=str(default_log_path()))

    root.rowconfigure(0, weight=1)
    root.columnconfigure(0, weight=1)

    shell = ttk.Frame(root, style="App.TFrame", padding=20)
    shell.grid(row=0, column=0, sticky="nsew")
    shell.columnconfigure(1, weight=1)
    shell.rowconfigure(0, weight=1)

    sidebar = tk.Frame(shell, bg=palette["sidebar_bg"], width=252, highlightthickness=0)
    sidebar.grid(row=0, column=0, sticky="nsew", padx=(0, 18))
    sidebar.grid_propagate(False)
    sidebar.columnconfigure(0, weight=1)

    tk.Frame(sidebar, bg=palette["accent"], height=4).grid(row=0, column=0, sticky="new")
    tk.Label(
        sidebar,
        text="RetainPDF",
        bg=palette["sidebar_bg"],
        fg=palette["sidebar_text"],
        font=("Microsoft YaHei UI", 20, "bold"),
        anchor="w",
    ).grid(row=1, column=0, sticky="ew", padx=24, pady=(28, 0))
    tk.Label(
        sidebar,
        text="Relay Proxy",
        bg=palette["sidebar_bg"],
        fg=palette["sidebar_muted"],
        font=("Microsoft YaHei UI", 11),
        anchor="w",
    ).grid(row=2, column=0, sticky="ew", padx=24, pady=(2, 24))
    tk.Label(
        sidebar,
        textvariable=status_badge_var,
        bg=palette["success_bg"],
        fg=palette["success_text"],
        font=("Microsoft YaHei UI", 10, "bold"),
        padx=12,
        pady=6,
    ).grid(row=3, column=0, sticky="w", padx=24, pady=(0, 22))

    def sidebar_item(row: int, title: str, value: str) -> None:
        tk.Label(
            sidebar,
            text=title,
            bg=palette["sidebar_bg"],
            fg=palette["sidebar_muted"],
            font=("Microsoft YaHei UI", 8),
            anchor="w",
        ).grid(row=row, column=0, sticky="ew", padx=24, pady=(12, 0))
        tk.Label(
            sidebar,
            text=value,
            bg=palette["sidebar_bg"],
            fg=palette["sidebar_text"],
            font=("Microsoft YaHei UI", 9),
            anchor="w",
            wraplength=204,
            justify="left",
        ).grid(row=row + 1, column=0, sticky="ew", padx=24, pady=(2, 0))

    sidebar_item(4, "本地接口", f"http://{initial.listen_host}:{initial.listen_port}/v1")
    sidebar_item(6, "RetainPDF 接口", f"http://{initial.listen_host}:{initial.listen_port}/api.deepseek.com/v1")
    sidebar_item(8, "日志文件", str(default_log_path()))
    sidebar.rowconfigure(10, weight=1)
    tk.Label(
        sidebar,
        text="后台模式不会保留命令行窗口。",
        bg=palette["sidebar_bg"],
        fg="#d0d5dd",
        font=("Microsoft YaHei UI", 9),
        anchor="w",
        wraplength=204,
        justify="left",
    ).grid(row=11, column=0, sticky="ew", padx=24, pady=(18, 26))

    main = ttk.Frame(shell, style="App.TFrame")
    main.grid(row=0, column=1, sticky="nsew")
    main.columnconfigure(0, weight=1)
    main.rowconfigure(1, weight=1)

    header = ttk.Frame(main, style="App.TFrame")
    header.grid(row=0, column=0, sticky="ew", pady=(2, 14))
    header.columnconfigure(0, weight=1)
    tk.Label(
        header,
        text="中转站助手",
        bg=palette["app_bg"],
        fg=palette["text"],
        font=("Microsoft YaHei UI", 18, "bold"),
        anchor="w",
    ).grid(row=0, column=0, sticky="w")
    tk.Label(
        header,
        text="配置接口、限速和 RetainPDF 启动参数。",
        bg=palette["app_bg"],
        fg=palette["muted"],
        font=("Microsoft YaHei UI", 10),
        anchor="w",
    ).grid(row=1, column=0, sticky="w", pady=(4, 0))

    content = ttk.Frame(main, style="App.TFrame")
    content.grid(row=1, column=0, sticky="nsew")
    content.columnconfigure(0, weight=3)
    content.columnconfigure(1, weight=2)
    content.rowconfigure(1, weight=1)

    def make_card(parent: Any, title: str, subtitle: str = "") -> tk.Frame:
        card = tk.Frame(
            parent,
            bg=palette["card_bg"],
            highlightbackground=palette["card_border"],
            highlightthickness=1,
            bd=0,
        )
        card.columnconfigure(0, weight=1)
        tk.Frame(card, bg=palette["accent"], height=3).place(relx=0, rely=0, relwidth=1)
        tk.Label(
            card,
            text=title,
            bg=palette["card_bg"],
            fg=palette["text"],
            font=("Microsoft YaHei UI", 12, "bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="ew", padx=20, pady=(18, 0))
        if subtitle:
            tk.Label(
                card,
                text=subtitle,
                bg=palette["card_bg"],
                fg=palette["muted"],
                font=("Microsoft YaHei UI", 9),
                anchor="w",
                wraplength=470,
                justify="left",
            ).grid(row=1, column=0, sticky="ew", padx=20, pady=(4, 12))
        else:
            ttk.Frame(card, style="Card.TFrame").grid(row=1, column=0, sticky="ew", pady=(0, 10))
        return card

    def field_label(parent: Any, row: int, text: str) -> None:
        tk.Label(
            parent,
            text=text,
            bg=palette["card_bg"],
            fg=palette["field"],
            font=("Microsoft YaHei UI", 9, "bold"),
            anchor="w",
        ).grid(row=row, column=0, sticky="w", padx=20, pady=(9, 5))

    def hint_label(parent: Any, row: int, text: str, *, columnspan: int = 1, wraplength: int = 460) -> None:
        tk.Label(
            parent,
            text=text,
            bg=palette["card_bg"],
            fg=palette["muted"],
            font=("Microsoft YaHei UI", 8),
            anchor="w",
            justify="left",
            wraplength=wraplength,
        ).grid(row=row, column=0, columnspan=columnspan, sticky="ew", padx=20, pady=(5, 8))

    interface_box = make_card(content, "中转站接口", "支持 OpenAI 兼容接口，保存时会自动规范化 Base URL。")
    interface_box.grid(row=0, column=0, sticky="nsew", padx=(0, 14), pady=(0, 14))
    interface_box.columnconfigure(0, weight=1)

    field_label(interface_box, 2, "中转站网址")
    ttk.Entry(interface_box, textvariable=upstream_base_url_var).grid(row=3, column=0, sticky="ew", padx=20)
    hint_label(interface_box, 4, "例如 https://your-relay.example.com/v1")

    key_row = ttk.Frame(interface_box, style="Card.TFrame")
    key_row.columnconfigure(0, weight=1)
    field_label(interface_box, 5, "API Key")
    key_row.grid(row=6, column=0, sticky="ew", padx=20)
    api_key_entry = ttk.Entry(key_row, textvariable=upstream_api_key_var, show="*")
    api_key_entry.grid(row=0, column=0, sticky="ew")

    def toggle_key_visibility() -> None:
        api_key_entry.configure(show="" if show_key_var.get() else "*")

    ttk.Checkbutton(key_row, text="显示", variable=show_key_var, command=toggle_key_visibility).grid(
        row=0,
        column=1,
        sticky="e",
        padx=(10, 0),
    )

    field_label(interface_box, 7, "模型名")
    ttk.Entry(interface_box, textvariable=upstream_model_var).grid(row=8, column=0, sticky="ew", padx=20)
    hint_label(interface_box, 9, "可选；为空时沿用 RetainPDF 请求中的模型。")

    retainpdf_box = make_card(content, "RetainPDF", "需要写入隐藏配置或自动打开 RetainPDF 时填写程序路径。")
    retainpdf_box.grid(row=1, column=0, sticky="nsew", padx=(0, 14), pady=(0, 14))
    retainpdf_box.columnconfigure(0, weight=1)

    path_row = ttk.Frame(retainpdf_box, style="Card.TFrame")
    path_row.columnconfigure(0, weight=1)
    field_label(retainpdf_box, 2, "程序路径")
    path_row.grid(row=3, column=0, sticky="ew", padx=20)
    ttk.Entry(path_row, textvariable=retainpdf_exe_var).grid(row=0, column=0, sticky="ew")

    def browse_retainpdf() -> None:
        selected = filedialog.askopenfilename(
            title="选择 RetainPDF.exe",
            filetypes=[("RetainPDF.exe", "RetainPDF.exe"), ("Executable", "*.exe"), ("All files", "*.*")],
        )
        if selected:
            retainpdf_exe_var.set(selected)

    ttk.Button(path_row, text="选择", style="Secondary.TButton", command=browse_retainpdf).grid(
        row=0,
        column=1,
        sticky="e",
        padx=(10, 0),
    )
    hint_label(retainpdf_box, 4, "保存并启动时会先写入隐藏配置，再打开 RetainPDF。")
    ttk.Checkbutton(
        retainpdf_box,
        text="写入 RetainPDF 隐藏接口配置",
        variable=patch_desktop_config_var,
    ).grid(row=5, column=0, sticky="w", padx=20, pady=(8, 4))
    ttk.Checkbutton(
        retainpdf_box,
        text="本地模拟 DeepSeek 余额检测",
        variable=mock_balance_var,
    ).grid(row=6, column=0, sticky="w", padx=20, pady=(4, 20))

    limits_box = make_card(content, "运行策略", "代理会在本地排队，避免中转站超出并发或 RPM。")
    limits_box.grid(row=0, column=1, sticky="nsew", pady=(0, 14))
    limits_box.columnconfigure(0, weight=1)

    spin_row = ttk.Frame(limits_box, style="Card.TFrame")
    spin_row.columnconfigure(0, weight=1)
    spin_row.columnconfigure(1, weight=1)
    spin_row.grid(row=2, column=0, sticky="ew", padx=20, pady=(8, 0))

    tk.Label(
        spin_row,
        text="并发上限",
        bg=palette["card_bg"],
        fg=palette["field"],
        font=("Microsoft YaHei UI", 9, "bold"),
        anchor="w",
    ).grid(row=0, column=0, sticky="w", pady=(0, 4))
    tk.Label(
        spin_row,
        text="RPM 限制",
        bg=palette["card_bg"],
        fg=palette["field"],
        font=("Microsoft YaHei UI", 9, "bold"),
        anchor="w",
    ).grid(row=0, column=1, sticky="w", padx=(12, 0), pady=(0, 4))
    ttk.Spinbox(spin_row, from_=1, to=999, textvariable=max_concurrent_var, width=8).grid(
        row=1,
        column=0,
        sticky="ew",
        pady=(0, 6),
    )
    ttk.Spinbox(spin_row, from_=0, to=9999, textvariable=max_requests_per_minute_var, width=8).grid(
        row=1,
        column=1,
        sticky="ew",
        padx=(12, 0),
        pady=(0, 6),
    )
    hint_label(limits_box, 3, "RPM 为 0 时不限制；并发至少为 1。", wraplength=260)

    status_box = make_card(content, "启动状态")
    status_box.grid(row=1, column=1, sticky="nsew", pady=(0, 14))
    status_box.columnconfigure(0, weight=1)
    tk.Label(
        status_box,
        textvariable=status_var,
        bg=palette["card_bg"],
        fg=palette["field"],
        font=("Microsoft YaHei UI", 9),
        anchor="w",
        justify="left",
        wraplength=260,
    ).grid(row=2, column=0, sticky="ew", padx=20, pady=(8, 12))
    tk.Label(
        status_box,
        text="配置文件",
        bg=palette["card_bg"],
        fg=palette["muted"],
        font=("Microsoft YaHei UI", 8),
        anchor="w",
    ).grid(row=3, column=0, sticky="ew", padx=20, pady=(4, 0))
    tk.Label(
        status_box,
        textvariable=config_path_var,
        bg=palette["card_bg"],
        fg=palette["field"],
        font=("Microsoft YaHei UI", 8),
        anchor="w",
        justify="left",
        wraplength=260,
    ).grid(row=4, column=0, sticky="ew", padx=20, pady=(2, 10))
    tk.Label(
        status_box,
        text="日志文件",
        bg=palette["card_bg"],
        fg=palette["muted"],
        font=("Microsoft YaHei UI", 8),
        anchor="w",
    ).grid(row=5, column=0, sticky="ew", padx=20, pady=(4, 0))
    tk.Label(
        status_box,
        textvariable=log_path_var,
        bg=palette["card_bg"],
        fg=palette["field"],
        font=("Microsoft YaHei UI", 8),
        anchor="w",
        justify="left",
        wraplength=260,
    ).grid(row=6, column=0, sticky="ew", padx=20, pady=(2, 18))

    buttons = ttk.Frame(main, style="App.TFrame")
    buttons.grid(row=2, column=0, sticky="e", pady=(4, 0))

    def current_payload() -> dict[str, Any] | None:
        if not upstream_base_url_var.get().strip():
            messagebox.showerror("配置错误", "请填写中转站网址。")
            return None
        normalized_base_url = normalize_base_url(upstream_base_url_var.get())
        parsed_base_url = urllib.parse.urlparse(normalized_base_url)
        if parsed_base_url.scheme not in {"http", "https"} or not parsed_base_url.netloc:
            messagebox.showerror("配置错误", "中转站网址必须是有效的 http 或 https 地址。")
            return None
        return config_payload_from_gui_values(
            existing=existing,
            upstream_base_url=normalized_base_url,
            upstream_api_key=upstream_api_key_var.get(),
            upstream_model=upstream_model_var.get(),
            retainpdf_exe_path=retainpdf_exe_var.get(),
            max_concurrent=max_concurrent_var.get(),
            max_requests_per_minute=max_requests_per_minute_var.get(),
            patch_desktop_config=patch_desktop_config_var.get(),
            mock_balance=mock_balance_var.get(),
        )

    def save_config() -> bool:
        payload = current_payload()
        if payload is None:
            return False
        try:
            save_json_config(config_path, payload)
        except Exception as exc:
            messagebox.showerror("保存失败", f"{type(exc).__name__}: {exc}")
            return False
        existing.clear()
        existing.update(payload)
        status_var.set("配置已保存。")
        status_badge_var.set("已保存")
        return True

    def save_and_start() -> None:
        nonlocal start_requested
        if not save_config():
            return
        if is_retainpdf_process_running():
            messagebox.showwarning(
                "RetainPDF 正在运行",
                "请先从托盘完全退出 RetainPDF，然后再点击“保存并启动”。",
            )
            return
        if start_in_current_process:
            start_requested = True
            status_badge_var.set("正在启动")
            root.destroy()
            return
        try:
            command = proxy_launch_command(config_path, retainpdf_exe_var.get())
            launch_background_process(command, cwd=str(config_path.parent))
        except Exception as exc:
            messagebox.showerror("启动失败", f"{type(exc).__name__}: {exc}")
            return
        status_var.set(f"代理已在后台启动。日志: {default_log_path()}")
        status_badge_var.set("后台运行")
        root.after(600, root.destroy)

    ttk.Button(buttons, text="保存配置", style="Secondary.TButton", command=save_config).grid(row=0, column=0, padx=(0, 8))
    ttk.Button(buttons, text="保存并启动", style="Primary.TButton", command=save_and_start).grid(
        row=0,
        column=1,
        padx=(0, 8),
    )
    ttk.Button(buttons, text="关闭", style="Secondary.TButton", command=root.destroy).grid(row=0, column=2)

    root.mainloop()
    return GUI_START_REQUESTED if start_requested else 0


def default_desktop_config_path() -> Path:
    appdata = os.environ.get("APPDATA", "").strip()
    if appdata:
        appdata_root = Path(appdata)
    else:
        appdata_root = Path.home() / "AppData" / "Roaming"
    candidate_dirs = [
        appdata_root / "retain-pdf-desktop",
        appdata_root / "RetainPDF",
    ]
    for directory in candidate_dirs:
        candidate = directory / "desktop-config.json"
        if candidate.exists():
            return candidate
    for directory in candidate_dirs:
        if directory.exists():
            return directory / "desktop-config.json"
    return candidate_dirs[0] / "desktop-config.json"


def load_desktop_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as file:
        payload = json.load(file)
    if not isinstance(payload, dict):
        raise ValueError(f"RetainPDF desktop config must be a JSON object: {path}")
    return payload


def patch_retainpdf_desktop_config(config: ProxyConfig, local_base_url: str) -> Path:
    config_path = (
        Path(config.desktop_config_path).expanduser().resolve()
        if config.desktop_config_path
        else default_desktop_config_path()
    )
    payload = load_desktop_config(config_path)
    developer_config = payload.get("developerConfig")
    if not isinstance(developer_config, dict):
        developer_config = {}

    model = str(developer_config.get("model") or payload.get("model") or DEFAULT_RETAINPDF_MODEL).strip()
    if config.upstream_model:
        model = config.upstream_model

    developer_config["baseUrl"] = local_base_url
    developer_config["model"] = model or DEFAULT_RETAINPDF_MODEL
    payload["developerConfig"] = developer_config
    payload["baseUrl"] = local_base_url
    payload["model"] = developer_config["model"]

    if config.retainpdf_api_key:
        payload["modelApiKey"] = config.retainpdf_api_key
    elif config.upstream_api_key:
        payload["modelApiKey"] = payload.get("modelApiKey") or "retainpdf-relay"

    config_path.parent.mkdir(parents=True, exist_ok=True)
    with config_path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)
        file.write("\n")
    return config_path


class RetainPdfRelayHandler(BaseHTTPRequestHandler):
    state: RelayState

    def log_message(self, format_string: str, *args: Any) -> None:
        if self.state.config.log_requests:
            super().log_message(format_string, *args)

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        add_cors_headers(self)
        self.end_headers()

    def do_GET(self) -> None:
        if is_models_path(self.path):
            model = self.state.config.upstream_model or DEFAULT_RETAINPDF_MODEL
            response_json(
                self,
                200,
                {
                    "object": "list",
                    "data": [
                        {
                            "id": model,
                            "object": "model",
                            "owned_by": "retainpdf-relay",
                        }
                    ],
                },
            )
            return
        if is_balance_path(self.path):
            if not self.state.config.mock_balance:
                response_json(self, 404, {"error": "balance_check_not_configured"})
                return
            response_json(
                self,
                200,
                {
                    "is_available": True,
                    "balance_infos": [
                        {
                            "currency": "CNY",
                            "total_balance": self.state.config.mock_balance_total,
                            "granted_balance": "0.00",
                            "topped_up_balance": self.state.config.mock_balance_total,
                        }
                    ],
                },
            )
            return
        if not is_health_path(self.path):
            response_json(self, 404, {"error": "not_found"})
            return
        with self.state.lock:
            active = self.state.active
            total = self.state.total
        response_json(
            self,
            200,
            {
                "status": "ok",
                "active": active,
                "total": total,
                "max_concurrent": self.state.config.max_concurrent,
                "max_requests_per_minute": self.state.config.max_requests_per_minute,
                "upstream_base_url": redact_url(self.state.config.upstream_base_url),
            },
        )

    def do_POST(self) -> None:
        if not is_chat_completions_path(self.path):
            response_json(self, 404, {"error": "only /v1/chat/completions is supported"})
            return

        try:
            request_body = read_request_body(self)
            payload = json.loads(request_body.decode("utf-8"))
        except Exception as exc:
            response_json(self, 400, {"error": "invalid_json", "detail": str(exc)})
            return
        if not isinstance(payload, dict):
            response_json(self, 400, {"error": "request body must be a JSON object"})
            return

        config = self.state.config
        if config.upstream_model:
            payload["model"] = config.upstream_model

        rate_acquired, rate_waited = self.state.acquire_rate_slot()
        if not rate_acquired:
            response_json(
                self,
                429,
                {
                    "error": "relay_rate_limit_timeout",
                    "max_requests_per_minute": config.max_requests_per_minute,
                    "waited_seconds": config.acquire_timeout_seconds,
                },
            )
            return
        if rate_waited >= 0.5 and config.log_requests:
            print(
                f"rate limit waited {rate_waited:.2f}s "
                f"rpm={config.max_requests_per_minute}",
                flush=True,
            )

        acquired = self.state.acquire()
        if not acquired:
            response_json(
                self,
                429,
                {
                    "error": "relay_concurrency_limit",
                    "max_concurrent": config.max_concurrent,
                    "waited_seconds": config.acquire_timeout_seconds,
                },
            )
            return

        request_id, active = self.state.mark_started()
        started = time.perf_counter()
        if config.log_requests:
            print(
                f"[{request_id}] forward start active={active}/{config.max_concurrent} "
                f"stream={payload.get('stream') is True} model={payload.get('model', '')}",
                flush=True,
            )

        try:
            self.forward_to_upstream(payload)
        finally:
            active_after = self.state.mark_finished()
            self.state.release()
            if config.log_requests:
                elapsed = time.perf_counter() - started
                print(f"[{request_id}] forward end active={active_after} elapsed={elapsed:.2f}s", flush=True)

    def forward_to_upstream(self, payload: dict[str, Any]) -> None:
        config = self.state.config
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = build_upstream_headers(self, config=config, body=payload)
        upstream_url = chat_completions_url(config.upstream_base_url)
        if should_use_curl_transport(config):
            try:
                status, content_type, upstream_body = post_upstream_with_curl(
                    url=upstream_url,
                    body=body,
                    headers=headers,
                    timeout_seconds=config.upstream_timeout_seconds,
                )
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(upstream_body)))
                add_cors_headers(self)
                self.end_headers()
                if upstream_body:
                    self.wfile.write(upstream_body)
                return
            except Exception as exc:
                if config.upstream_transport == "curl":
                    response_json(
                        self,
                        502,
                        {
                            "error": "upstream_curl_failed",
                            "detail": f"{type(exc).__name__}: {exc}",
                            "upstream_base_url": redact_url(config.upstream_base_url),
                        },
                    )
                    return
                if config.log_requests:
                    print(f"curl transport failed, falling back to urllib: {type(exc).__name__}: {exc}", flush=True)

        request = urllib.request.Request(
            upstream_url,
            data=body,
            headers=headers,
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=config.upstream_timeout_seconds) as upstream:
                status = int(getattr(upstream, "status", 200) or 200)
                if payload.get("stream") is True:
                    self.send_response(status)
                    copy_response_headers(self, upstream.headers, include_length=False)
                    self.end_headers()
                    while True:
                        chunk = upstream.read(8192)
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                        self.wfile.flush()
                    return

                upstream_body = upstream.read()
                self.send_response(status)
                copy_response_headers(self, upstream.headers, include_length=False)
                self.send_header("Content-Length", str(len(upstream_body)))
                self.end_headers()
                if upstream_body:
                    self.wfile.write(upstream_body)
        except urllib.error.HTTPError as exc:
            write_upstream_http_error(self, exc)
        except Exception as exc:
            response_json(
                self,
                502,
                {
                    "error": "upstream_request_failed",
                    "detail": f"{type(exc).__name__}: {exc}",
                    "upstream_base_url": redact_url(config.upstream_base_url),
                },
            )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Local OpenAI-compatible relay proxy for RetainPDF translation requests.",
    )
    parser.add_argument(
        "--config",
        type=str,
        default="",
        help="Path to retainpdf-relay-proxy.json. Env vars with RETAINPDF_PROXY_ prefix override it.",
    )
    parser.add_argument(
        "--gui",
        action="store_true",
        help="Open a configuration window for upstream relay URL and API key.",
    )
    parser.add_argument(
        "--configure-and-run",
        action="store_true",
        help="Open the configuration window, then keep this process running as the proxy after Save and Start.",
    )
    parser.add_argument(
        "--launch",
        type=str,
        default="",
        help="Optional RetainPDF.exe path to launch after the proxy starts.",
    )
    parser.add_argument(
        "--patch-desktop-config",
        action="store_true",
        help="Patch RetainPDF desktop-config.json so hidden developer Base URL points at this local proxy.",
    )
    parser.add_argument(
        "--desktop-config",
        type=str,
        default="",
        help="Optional explicit path to RetainPDF desktop-config.json.",
    )
    parser.add_argument(
        "--retainpdf-api-key",
        type=str,
        default="",
        help="Optional API key value to store in RetainPDF. Defaults to a local placeholder when upstream_api_key is configured.",
    )
    return parser.parse_args()


def maybe_launch_app(path: str, *, env_overrides: dict[str, str] | None = None) -> None:
    app_path = path.strip().strip('"')
    if not app_path:
        return
    resolved = Path(app_path).expanduser().resolve()
    if not resolved.exists():
        raise FileNotFoundError(f"RetainPDF executable not found: {resolved}")
    env = os.environ.copy()
    if env_overrides:
        env.update(env_overrides)
    launch_background_process([str(resolved)], cwd=str(resolved.parent), env=env)
    print(f"Launched: {resolved}", flush=True)


def run() -> int:
    ensure_background_stdio()
    args = parse_args()
    if getattr(sys, "frozen", False) and len(sys.argv) == 1:
        args.configure_and_run = True
    if args.gui or args.configure_and_run:
        gui_config_path = resolved_config_path(args.config)
        gui_result = run_main_config_gui(
            gui_config_path,
            start_in_current_process=args.configure_and_run,
        )
        if not args.configure_and_run or gui_result != GUI_START_REQUESTED:
            return gui_result
        config_path = gui_config_path
    else:
        config_path = Path(args.config).expanduser().resolve() if args.config.strip() else None
    try:
        config = build_config(config_path)
    except Exception as exc:
        print(f"Failed to load config: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    if args.patch_desktop_config:
        config = replace(
            config,
            patch_desktop_config=True,
            desktop_config_path=args.desktop_config.strip() or config.desktop_config_path,
            retainpdf_api_key=args.retainpdf_api_key.strip() or config.retainpdf_api_key,
        )

    RetainPdfRelayHandler.state = RelayState(config)
    try:
        server = ThreadingHTTPServer((config.listen_host, config.listen_port), RetainPdfRelayHandler)
    except OSError as exc:
        print(
            f"Failed to bind relay proxy on {config.listen_host}:{config.listen_port}: {exc}",
            file=sys.stderr,
        )
        return 5

    local_origin = f"http://{config.listen_host}:{config.listen_port}"
    local_base_url = f"{local_origin}/v1"
    retainpdf_base_url = f"{local_origin}/api.deepseek.com/v1"
    if config.patch_desktop_config:
        try:
            patched_path = patch_retainpdf_desktop_config(config, retainpdf_base_url)
        except Exception as exc:
            print(f"Failed to patch RetainPDF desktop config: {type(exc).__name__}: {exc}", file=sys.stderr)
            server.server_close()
            return 3
        print(f"Patched RetainPDF desktop config: {patched_path}", flush=True)

    print("RetainPDF relay proxy started", flush=True)
    print(f"  local base_url: {local_base_url}", flush=True)
    print(f"  retainpdf base_url: {retainpdf_base_url}", flush=True)
    print(f"  upstream: {redact_url(config.upstream_base_url)}", flush=True)
    print(f"  upstream_transport: {config.upstream_transport}", flush=True)
    print(f"  max_concurrent: {config.max_concurrent}", flush=True)
    print(f"  max_requests_per_minute: {config.max_requests_per_minute or 'unlimited'}", flush=True)
    print("Set RetainPDF developer Base URL to the retainpdf base_url above.", flush=True)

    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    try:
        server_thread.start()
        print("Relay HTTP server is ready.", flush=True)
        if not wait_for_local_proxy_ready(
            local_origin,
            retainpdf_base_url,
            mock_balance=config.mock_balance,
        ):
            return 6

        launch_env = {
            "RUST_API_DEEPSEEK_BASE_URL": retainpdf_base_url,
        }
        if config.mock_balance:
            launch_env["RUST_API_DEEPSEEK_BALANCE_URL"] = f"{local_origin}/user/balance"
        launch_path = args.launch.strip() or config.retainpdf_exe_path
        if launch_path and is_retainpdf_process_running():
            print(
                "RetainPDF.exe is already running. Fully exit it from the tray, then start this helper again.",
                file=sys.stderr,
                flush=True,
            )
            return 7
        if config.mock_balance and not launch_path:
            print(
                "Warning: mock_balance is enabled, but no RetainPDF executable was provided. "
                "Start RetainPDF through this helper so RUST_API_DEEPSEEK_BALANCE_URL is applied.",
                flush=True,
            )
        maybe_launch_app(launch_path, env_overrides=launch_env)
        while server_thread.is_alive():
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nStopping proxy...", flush=True)
    finally:
        server.shutdown()
        server.server_close()
        if server_thread.is_alive():
            server_thread.join(timeout=3)
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
