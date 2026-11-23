"""One private loopback engine per active workspace, backed by its own volume."""

import asyncio
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
import httpx
from fastapi import HTTPException
from .accounts import home


class Engines:
    def __init__(self):
        self.lock = asyncio.Lock()
        self.live = {}

    async def get(self, team):
        async with self.lock:
            now = time.monotonic()
            for key, (proc, port, used) in list(self.live.items()):
                if proc.poll() is not None:
                    del self.live[key]
                elif key != team and now - used > 900 and not self.busy(key):
                    proc.terminate()
                    await asyncio.to_thread(proc.wait)
                    del self.live[key]
            if team in self.live:
                proc, port, _ = self.live[team]
                self.live[team] = (proc, port, now)
                return port
            if len(self.live) >= int(os.getenv("CLIPFORGE_MAX_WORKSPACES", "4")):
                raise HTTPException(
                    503, "El servidor está ocupado. Reintenta en unos minutos."
                )
            with socket.socket() as s:
                s.bind(("127.0.0.1", 0))
                port = s.getsockname()[1]
            path = home() / "workspaces" / team
            path.mkdir(parents=True, exist_ok=True)
            safe_names = {
                "PATH",
                "SYSTEMROOT",
                "WINDIR",
                "TEMP",
                "TMP",
                "HOME",
                "USERPROFILE",
                "LOCALAPPDATA",
                "LANG",
                "FFMPEG_BIN",
                "FFPROBE_BIN",
                "YTDLP_COOKIES",
                "YTDLP_COOKIES_FROM_BROWSER",
                "CLIPFORGE_SPEAKER_MODEL",
                "WHISPER_MODEL",
                "WHISPER_DEVICE",
                "HF_HOME",
                "WEB_DIST",
                "CLIPFORGE_MODEL_RATES",
                "CLIPFORGE_RENDER_USD_HOUR",
                "CLIPFORGE_STORAGE_USD_GB_MONTH",
                "CLIPFORGE_PUBLIC_ORIGIN",
                "YOUTUBE_CLIENT_ID",
                "YOUTUBE_CLIENT_SECRET",
                "TIKTOK_CLIENT_KEY",
                "TIKTOK_CLIENT_SECRET",
                "LLM_MODEL",
                "LLM_API_KEY",
                "LLM_BASE_URL",
                "OMP_NUM_THREADS",
                "PYTHONUTF8",
            }
            env = {k: v for k, v in os.environ.items() if k.upper() in safe_names}
            env.update(
                DATA_DIR=str(path),
                CLIPFORGE_TEAM_ENGINE="1",
                YTDLP_AUTO_COOKIES="false",
                YOUTUBE_PRIVACY="private",
                TIKTOK_PRIVACY="SELF_ONLY",
                MAX_UPLOAD_MB=os.getenv("CLIPFORGE_CLOUD_UPLOAD_MB", "512"),
                MAX_SOURCE_MINUTES=os.getenv("CLIPFORGE_CLOUD_MAX_MINUTES", "180"),
            )
            log = (path / "engine.log").open("ab")
            try:
                proc = subprocess.Popen(
                    [
                        sys.executable,
                        "-m",
                        "uvicorn",
                        "app.main:app",
                        "--host",
                        "127.0.0.1",
                        "--port",
                        str(port),
                        "--no-access-log",
                    ],
                    cwd=Path(__file__).resolve().parents[1],
                    env=env,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
            finally:
                log.close()
            try:
                async with httpx.AsyncClient(trust_env=False, timeout=1) as client:
                    for _ in range(200):
                        if proc.poll() is not None:
                            break
                        try:
                            response = await client.get(
                                f"http://127.0.0.1:{port}/api/options"
                            )
                            if response.status_code == 200:
                                self.live[team] = (proc, port, time.monotonic())
                                return port
                        except httpx.HTTPError:
                            pass
                        await asyncio.sleep(0.15)
                raise HTTPException(503, "El motor del equipo no pudo arrancar.")
            finally:
                if team not in self.live and proc.poll() is None:
                    proc.terminate()
                    await asyncio.to_thread(proc.wait)

    def busy(self, team):
        import sqlite3
        from contextlib import closing

        path = home() / "workspaces" / team / "Clipwise.db"
        if not path.is_file():
            return False
        try:
            with closing(sqlite3.connect(path, timeout=0.25)) as conn:
                return bool(
                    conn.execute(
                        "SELECT EXISTS(SELECT 1 FROM jobs WHERE status IN ('processing','queued')) OR EXISTS(SELECT 1 FROM clips WHERE status IN ('rendering','queued')) OR EXISTS(SELECT 1 FROM publish_records WHERE status IN ('queued','uploading','processing'))"
                    ).fetchone()[0]
                )
        except sqlite3.Error:
            return True

    async def close(self):
        for proc, _, _ in self.live.values():
            if proc.poll() is None:
                proc.terminate()
                await asyncio.to_thread(proc.wait)
        self.live.clear()
