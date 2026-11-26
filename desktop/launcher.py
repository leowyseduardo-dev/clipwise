from __future__ import annotations

import ctypes
import json
import logging
import multiprocessing
import os
import re
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from email.message import Message
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

APP_NAME = "Clipwise"
APP_ID = "Clipwise.Desktop"
MUTEX_NAME = r"Local\Clipwise.Desktop.SingleInstance"
WINDOW_TITLE = "Clipwise"
# Kept as ClipForge so existing local libraries and settings survive the rebrand.
DATA_DIR_NAME = "ClipForge"

_mutex_handle: int | None = None
_user_closed = False
_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

_DOWNLOAD_PATH_RE = re.compile(r"^/api/(?:clips|jobs|live)/")
_INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED_FILENAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}

def _downloads_dir() -> Path:
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders",
        ) as key:
            value, _ = winreg.QueryValueEx(
                key, "{374DE290-123F-4565-9164-39C4925E467B}"
            )
        path = Path(value)
        if path.is_dir():
            return path
    except Exception:
        pass
    return Path.home() / "Downloads"


def _safe_filename(name: str, fallback: str) -> str:
    candidate = Path(name).name.strip()
    candidate = _INVALID_FILENAME_CHARS.sub("_", candidate).strip(" .")
    if not candidate:
        candidate = fallback
    stem = candidate.split(".", 1)[0].upper()
    if stem in _RESERVED_FILENAMES:
        candidate = f"_{candidate}"
    if len(candidate) > 180:
        suffix = Path(candidate).suffix[:20]
        candidate = f"{Path(candidate).stem[: max(1, 180 - len(suffix))]}{suffix}"
    return candidate or fallback


def _filename_from_disposition(value: str | None) -> str | None:
    if not value:
        return None
    message = Message()
    message["content-disposition"] = value
    filename = message.get_filename()
    if not filename:
        return None
    try:
        filename = filename.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        pass
    return filename


class DesktopDownloadApi:
    """Native save-dialog downloads for the desktop shell.

    Browser downloads still use the normal ``<a download>`` links. In the
    desktop app a capture-phase click handler calls this API instead, which
    keeps the filename and extension intact and avoids WebView2's multiple
    automatic-download permission prompt.
    """

    def __init__(self, port: int) -> None:
        self._port = port
        self._base = f"http://127.0.0.1:{port}"
        self.window: Any = None

    def _resolve(self, url: str) -> str:
        parsed = urllib.parse.urlsplit(url)
        if not parsed.scheme:
            url = urllib.parse.urljoin(self._base + "/", url)
            parsed = urllib.parse.urlsplit(url)
        if (
            parsed.scheme != "http"
            or parsed.hostname not in {"127.0.0.1", "localhost"}
            or parsed.port != self._port
            or parsed.username
            or parsed.password
        ):
            raise ValueError("URL de descarga no permitida")
        if not _DOWNLOAD_PATH_RE.match(parsed.path):
            raise ValueError("Ruta de descarga no permitida")
        return url

    def save_download(self, url: str, preferred_name: str = "") -> dict[str, Any]:
        try:
            resolved = self._resolve(url)
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
        if self.window is None:
            return {"ok": False, "error": "La ventana no esta disponible"}

        try:
            request = urllib.request.Request(
                resolved,
                headers={"User-Agent": "Clipwise/1.0 (+desktop)"},
            )
            with _opener.open(request, timeout=120) as response:
                header_name = _filename_from_disposition(
                    response.headers.get("Content-Disposition")
                )
                url_path = urllib.parse.unquote(
                    urllib.parse.urlsplit(resolved).path
                )
                url_name = Path(url_path).name
                fallback = header_name or url_name or "clipwise-download.bin"
                preferred = (
                    _safe_filename(preferred_name, "") if preferred_name else ""
                )
                fallback_suffix = Path(fallback).suffix
                if preferred and not Path(preferred).suffix and fallback_suffix:
                    preferred = f"{preferred}{fallback_suffix}"
                filename = _safe_filename(
                    preferred or fallback, "clipwise-download.bin"
                )
                suffix = Path(filename).suffix.lower()
                file_types = (
                    (f"{suffix[1:].upper()} (*{suffix})", "All files (*.*)")
                    if suffix
                    else ("All files (*.*)",)
                )

                import webview

                selection = self.window.create_file_dialog(
                    webview.SAVE_DIALOG,
                    directory=str(_downloads_dir()),
                    save_filename=filename,
                    file_types=file_types,
                )
                if isinstance(selection, (list, tuple)):
                    if not selection:
                        return {"ok": False, "cancelled": True}
                    destination = selection[0]
                else:
                    destination = selection
                if not destination:
                    return {"ok": False, "cancelled": True}
                destination = str(destination)
                if suffix and not Path(destination).suffix:
                    destination += suffix

                part = f"{destination}.part"
                total = 0
                try:
                    with open(part, "wb") as output:
                        while True:
                            chunk = response.read(1024 * 1024)
                            if not chunk:
                                break
                            output.write(chunk)
                            total += len(chunk)
                    os.replace(part, destination)
                except Exception:
                    try:
                        os.unlink(part)
                    except OSError:
                        pass
                    raise
                return {"ok": True, "path": destination, "size": total}
        except Exception as exc:
            logging.getLogger("clipforge.desktop").exception(
                "Descarga fallida: %s", resolved
            )
            return {"ok": False, "error": str(exc)}


def _resource_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    return Path(__file__).resolve().parent.parent


def _user_data_dir() -> Path:
    root = os.getenv("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(root) / DATA_DIR_NAME


def _load_env(data_dir: Path) -> None:
    try:
        from dotenv import load_dotenv
    except Exception:
        return
    for candidate in (data_dir / ".env", _resource_root() / ".env"):
        if candidate.exists():
            load_dotenv(candidate, override=False)


def _configure_environment(data_dir: Path) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    if not getattr(sys, "frozen", False):
        engine = _resource_root() / "engine"
        if str(engine) not in sys.path:
            sys.path.insert(0, str(engine))
    _load_env(data_dir)
    os.environ.setdefault("DATA_DIR", str(data_dir))
    os.environ.setdefault("WEB_DIST", str(_resource_root() / "web" / "dist"))

    bundled_ffmpeg = _resource_root() / "bin" / "ffmpeg.exe"
    bundled_ffprobe = _resource_root() / "bin" / "ffprobe.exe"
    if bundled_ffmpeg.exists():
        os.environ.setdefault("FFMPEG_BIN", str(bundled_ffmpeg))
    if bundled_ffprobe.exists():
        os.environ.setdefault("FFPROBE_BIN", str(bundled_ffprobe))

    bundled_model = _resource_root() / "models" / "tiny"
    if bundled_model.exists():
        os.environ.setdefault("WHISPER_MODEL", str(bundled_model))
    os.environ.setdefault("HF_HOME", str(data_dir / "models" / "hf"))
    os.environ.setdefault("PYTHONUTF8", "1")
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")


def _set_up_logging(data_dir: Path) -> Path:
    log_dir = data_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "clipforge.log"
    handlers: list[logging.Handler] = [
        RotatingFileHandler(
            log_path,
            maxBytes=4 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8",
        )
    ]
    if sys.stderr is not None:
        handlers.append(logging.StreamHandler(sys.stderr))
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=handlers,
        force=True,
    )
    return log_path


def _message(title: str, text: str, flags: int = 0x10) -> int:
    try:
        return int(ctypes.windll.user32.MessageBoxW(None, text, title, flags))
    except Exception:
        return 0


def _acquire_single_instance() -> bool:
    global _mutex_handle
    kernel32 = ctypes.windll.kernel32
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = kernel32.CreateMutexW(None, False, MUTEX_NAME)
    if not handle:
        return True
    if kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        kernel32.CloseHandle(handle)
        return False
    _mutex_handle = handle
    return True


def _focus_existing_window() -> bool:
    user32 = ctypes.windll.user32
    user32.FindWindowW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p]
    user32.FindWindowW.restype = ctypes.c_void_p
    hwnd = user32.FindWindowW(None, WINDOW_TITLE)
    if not hwnd:
        return False
    user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    user32.SetForegroundWindow(hwnd)
    return True


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_port(port: int, timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                return
        except OSError as exc:
            last_error = exc
        time.sleep(0.1)
    raise RuntimeError(f"El servidor local no acepto conexiones a tiempo: {last_error}")


def _wait_for_server(port: int, timeout: float = 60.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    url = f"http://127.0.0.1:{port}/api/health"
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with _opener.open(url, timeout=2) as response:
                if response.status == 200:
                    return json.loads(response.read().decode("utf-8"))
        except (OSError, urllib.error.URLError, ValueError) as exc:
            last_error = exc
        time.sleep(0.25)
    raise RuntimeError(f"El servidor local no arranco a tiempo: {last_error}")


def _start_server(port: int) -> tuple[Any, threading.Thread]:
    import uvicorn

    from app.main import app

    config = uvicorn.Config(
        app=app,
        host="127.0.0.1",
        port=port,
        log_level="info",
        access_log=False,
        log_config=None,
        loop="asyncio",
        http="h11",
        ws="none",
    )
    server = uvicorn.Server(config)
    server.install_signal_handlers = lambda: None  # type: ignore[method-assign]
    thread = threading.Thread(
        target=server.run,
        name="clipforge-api",
        daemon=True,
    )
    thread.start()
    return server, thread


def _write_runtime(data_dir: Path, port: int) -> Path:
    path = data_dir / "runtime.json"
    temp = data_dir / "runtime.json.tmp"
    payload = {
        "pid": os.getpid(),
        "port": port,
        "url": f"http://127.0.0.1:{port}",
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp, path)
    return path


def _remove_runtime(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def _api_json(port: int, path: str) -> Any:
    with _opener.open(f"http://127.0.0.1:{port}{path}", timeout=2) as response:
        return json.loads(response.read().decode("utf-8"))


def _active_jobs(port: int) -> list[dict[str, Any]]:
    try:
        jobs = _api_json(port, "/api/jobs")
    except Exception:
        return []
    if not isinstance(jobs, list):
        return []
    return [
        job
        for job in jobs
        if isinstance(job, dict) and job.get("status") in {"queued", "processing"}
    ]


def _confirm_close(port: int) -> bool:
    active = _active_jobs(port)
    if not active:
        return True
    message = (
        "Hay un trabajo en curso. Si cierras ahora, se interrumpira.\n\n"
        "¿Cerrar de todos modos?"
    )
    return _message(APP_NAME, message, 0x04 | 0x30) == 6  # MB_YESNO | MB_ICONWARNING


def _run_self_test(port: int, server: Any, thread: threading.Thread, data_dir: Path) -> int:
    result: dict[str, Any] = {"ok": False}
    try:
        health = _wait_for_server(port)
        with _opener.open(f"http://127.0.0.1:{port}/", timeout=5) as response:
            index = response.read(8192).decode("utf-8", "replace")
        import curl_cffi
        from app.ingest import validate_source_url
        from yt_dlp.networking._curlcffi import CurlCFFIRH
        source_links = [
            "https://www.twitch.tv/videos/6528877",
            "https://kick.com/spreen/clips/clip_01J8RGZRKHXHXXKJEHGRM932A5",
        ]
        sources_ok = all(validate_source_url(url) == url for url in source_links)
        result = {
            "ok": bool(health.get("ffmpeg", {}).get("available"))
            and '<div id="root">' in index and sources_ok,
            "health": health,
            "index_has_root": '<div id="root">' in index,
            "data_dir": str(data_dir),
            "source_extractors": sources_ok,
            "curl_cffi": curl_cffi.__version__,
            "curl_handler": CurlCFFIRH.__name__,
        }
    except Exception as exc:
        logging.getLogger("clipforge.desktop").exception("Self-test fallo")
        result = {"ok": False, "error": str(exc)}
    finally:
        server.should_exit = True
        thread.join(timeout=10)
    path = data_dir / "logs" / "selftest.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    if sys.stdout is not None:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


def _run_server_only(
    port: int,
    server: Any,
    thread: threading.Thread,
    runtime_path: Path,
) -> int:
    logging.getLogger("clipforge.desktop").info("Servidor de prueba en http://127.0.0.1:%s", port)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        _remove_runtime(runtime_path)
    return 0


def _open_window(port: int, data_dir: Path) -> None:
    import webview

    webview.settings["ALLOW_DOWNLOADS"] = True
    api = DesktopDownloadApi(port)
    window = webview.create_window(
        WINDOW_TITLE,
        f"http://127.0.0.1:{port}",
        width=1440,
        height=920,
        min_size=(1100, 700),
        background_color="#09090b",
        js_api=api,
    )
    api.window = window

    def _on_closing(*_: Any) -> bool:
        global _user_closed
        if _confirm_close(port):
            _user_closed = True
            return True
        return False

    window.events.closing += _on_closing
    webview.start(
        debug=os.getenv("CLIPFORGE_DEBUG") == "1",
        private_mode=False,
        storage_path=str(data_dir / "webview"),
    )


def _run_window_child(port: int, data_dir: Path) -> int:
    """Runs inside the window child process: open the webview, block.

    The webview layer is fragile (WebView2 dies or freezes under memory
    pressure). Isolating it here keeps its GIL and .NET mess away from the
    engine process, so renders and the API survive any window death.
    """
    _configure_environment(data_dir)
    _set_up_logging(data_dir)
    logger = logging.getLogger("clipforge.desktop")
    logger.info("Ventana (proceso hijo) abriendo en el puerto %s", port)

    heartbeat = data_dir / "logs" / "window.heartbeat"

    def _beat() -> None:
        while True:
            try:
                heartbeat.write_text(str(time.time()), encoding="utf-8")
            except OSError:
                pass
            time.sleep(5)

    threading.Thread(target=_beat, name="window-heartbeat", daemon=True).start()
    _open_window(port, data_dir)
    logger.info("Ventana cerrada (usuario: %s).", _user_closed)
    return 42 if _user_closed else 0


def _run_window_supervisor(port: int, data_dir: Path) -> None:
    """Keep a live window process running; the engine outlives any crash.

    A child that exits nonzero (window crash) or freezes (no heartbeat for
    30 s) gets replaced. Five fast deaths in a row means the machine cannot
    sustain a window right now: keep the headless server running and stop
    respawning so renders finish.
    """
    logger = logging.getLogger("clipforge.desktop")
    heartbeat = data_dir / "logs" / "window.heartbeat"
    fast_deaths = 0
    while True:
        heartbeat.parent.mkdir(parents=True, exist_ok=True)
        heartbeat.write_text(str(time.time()), encoding="utf-8")
        started = time.monotonic()
        try:
            proc = subprocess.Popen(
                [sys.executable, "--window-child", "--port", str(port)],
                cwd=str(_resource_root()),
                # Separate process group: a WebView2 crash raising a console
                # control event must not take the engine process down with it.
                creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                | getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except OSError:
            logger.exception("No se pudo lanzar la ventana; el servidor sigue vivo.")
            fast_deaths += 1
            if fast_deaths >= 5:
                logger.error("Cinco intentos fallidos de abrir la ventana; modo sin ventana.")
                return
            time.sleep(5)
            continue
        while True:
            try:
                code = proc.wait(timeout=10)
                logger.warning(
                    "La ventana se cerro (codigo %s, %.0f s de vida).",
                    code,
                    time.monotonic() - started,
                )
                if code == 42:
                    return  # Cierre normal del usuario: apagar el servidor.
                break
            except subprocess.TimeoutExpired:
                try:
                    last = float(heartbeat.read_text(encoding="utf-8").strip())
                except (OSError, ValueError):
                    last = time.time()
                if time.time() - last > 30:
                    logger.warning(
                        "La ventana se congelo (sin latido %.0f s); se reinicia.",
                        time.time() - last,
                    )
                    proc.kill()
                    proc.wait(timeout=10)
                    break

        lived = time.monotonic() - started
        fast_deaths = 0 if lived > 60 else fast_deaths + 1
        if fast_deaths >= 5:
            logger.error(
                "La ventana murio %d veces seguidas; el servidor sigue vivo sin ventana.",
                fast_deaths,
            )
            return
        time.sleep(3)


def main() -> int:
    multiprocessing.freeze_support()
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
    except Exception:
        pass
    # A crashing WebView2 child can broadcast a console control event; the
    # engine process must ignore it and keep serving.
    try:
        import signal

        signal.signal(signal.SIGBREAK, signal.SIG_IGN)
        signal.signal(signal.SIGINT, signal.SIG_IGN)
    except (AttributeError, ValueError, OSError):
        pass

    data_dir = _user_data_dir()
    args = sys.argv[1:]
    if "--window-child" in args:
        # Ventana en proceso hijo: no toca el mutex ni el runtime del padre.
        try:
            port = int(args[args.index("--port") + 1])
        except (ValueError, IndexError):
            return 2
        return _run_window_child(port, data_dir)

    _configure_environment(data_dir)
    log_path = _set_up_logging(data_dir)
    logger = logging.getLogger("clipforge.desktop")
    logger.info("Iniciando %s desde %s", APP_NAME, _resource_root())

    if not _acquire_single_instance():
        if not _focus_existing_window():
            _message(
                APP_NAME,
                "Clipwise ya esta en ejecucion. Busca su ventana en la barra de tareas.",
                0x40,
            )
        return 0

    args = sys.argv[1:]
    self_test = "--self-test" in args
    server_only = "--server-only" in args
    if self_test or server_only:
        os.environ.pop("CLIPFORGE_FAST_HEALTH", None)
    else:
        os.environ.setdefault("CLIPFORGE_FAST_HEALTH", "1")
    try:
        port = int(os.getenv("CLIPFORGE_PORT", "0")) or _free_port()
        if "--port" in args:
            port = int(args[args.index("--port") + 1])
    except (ValueError, IndexError):
        port = _free_port()

    runtime_path = data_dir / "runtime.json"
    server: Any = None
    thread: threading.Thread | None = None
    try:
        server, thread = _start_server(port)
        if self_test or server_only:
            health = _wait_for_server(port)
            logger.info("Servidor listo en http://127.0.0.1:%s", port)
            logger.info(
                "ffmpeg=%s whisper=%s",
                health.get("ffmpeg", {}).get("available"),
                health.get("whisper_model"),
            )
        else:
            # The UI owns the loading state; do not block the window on binary probes.
            _wait_for_port(port)
            logger.info("Servidor aceptando conexiones en http://127.0.0.1:%s", port)
        _write_runtime(data_dir, port)
        if self_test:
            return _run_self_test(port, server, thread, data_dir)
        if server_only:
            return _run_server_only(port, server, thread, runtime_path)
        # La ventana vive en un proceso hijo vigilado: si muere o se congela,
        # se relanza sola y el motor (y los renders) nunca se enteran.
        _run_window_supervisor(port, data_dir)
        return 0
    except Exception as exc:
        logger.exception("No se pudo iniciar Clipwise")
        if not self_test:
            _message(
                APP_NAME,
                "No se pudo iniciar Clipwise.\n\n"
                f"{exc}\n\nRevisa el registro:\n{log_path}",
                0x10,
            )
        return 1
    finally:
        if server is not None:
            server.should_exit = True
        if thread is not None:
            thread.join(timeout=10)
        _remove_runtime(runtime_path)


if __name__ == "__main__":
    raise SystemExit(main())
