# -*- mode: python ; coding: utf-8 -*-
import os
from pathlib import Path

from PyInstaller.utils.hooks import (
    collect_data_files,
    collect_dynamic_libs,
    collect_submodules,
)

HERE = Path(SPECPATH).resolve()
ROOT = HERE.parent
ENGINE = ROOT / "engine"
ASSETS = HERE / "assets"
MODEL = HERE / "build" / "models" / "tiny"
WEB_DIST = Path(os.getenv("CLIPWISE_WEB_DIST", str(ROOT / "web" / "dist")))


def _ffmpeg_bin() -> Path:
    candidates = [
        ROOT / "tools" / "ffmpeg" / "ffmpeg-9.0.2-essentials_build" / "bin",
    ]
    for candidate in candidates:
        if (candidate / "ffmpeg.exe").exists():
            return candidate
    found = sorted((ROOT / "tools" / "ffmpeg").rglob("ffmpeg.exe"))
    if not found:
        raise SystemExit("No se encontro ffmpeg.exe en tools/ffmpeg")
    return found[0].parent


FFMPEG_BIN = _ffmpeg_bin()

datas = [
    (str(WEB_DIST), "web/dist"),
    (str(FFMPEG_BIN / "ffmpeg.exe"), "bin"),
    (str(FFMPEG_BIN / "ffprobe.exe"), "bin"),
]
if MODEL.exists():
    datas.append((str(MODEL), "models/tiny"))
engine_models = ENGINE / "models"
if engine_models.exists():
    datas.append((str(engine_models), "models"))

datas += collect_data_files("faster_whisper")
datas += collect_data_files("cv2")
datas += collect_data_files("scenedetect")
datas += collect_data_files("yt_dlp")

binaries = []
for package in ("cv2", "ctranslate2", "av", "onnxruntime", "_soundfile_data"):
    try:
        binaries += collect_dynamic_libs(package)
    except Exception:
        pass

hiddenimports = [
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.loops.asyncio",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    "uvicorn.middleware",
    "uvicorn.middleware.proxy_headers",
    "fastapi",
    "starlette",
    "starlette.staticfiles",
    "starlette.responses",
    "anyio._backends._asyncio",
    "httptools",
    "multipart",
    "python_multipart",
    "dotenv",
    "faster_whisper",
    "ctranslate2",
    "tokenizers",
    "huggingface_hub",
    "onnxruntime",
    "av",
    "cv2",
    "scenedetect",
    "yt_dlp",
    "curl_cffi",
    "yt_dlp.networking._curlcffi",
    "webview.platforms.edgechromium",
    "webview.platforms.winforms",
    "clr_loader",
    "pythonnet",
]

for package in ("webview", "scenedetect", "yt_dlp", "faster_whisper"):
    try:
        hiddenimports += collect_submodules(package)
    except Exception:
        pass

a = Analysis(
    [str(HERE / "launcher.py")],
    pathex=[str(ROOT), str(ENGINE)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "matplotlib",
        "pandas",
        "scipy",
        "pytest",
        "PyQt5",
        "PySide6",
        "IPython",
        "notebook",
        "jupyter",
    ],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Clipwise",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ASSETS / "Clipwise.ico"),
    version=str(HERE / "version_info.txt"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="Clipwise",
)
