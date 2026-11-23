from __future__ import annotations

import os

from app import config


def test_prepend_binary_dir_adds_ffmpeg_folder_once(monkeypatch) -> None:
    monkeypatch.setenv("PATH", r"C:\Windows")
    binary = r"C:\ffmpeg\bin\ffmpeg.exe"

    config._prepend_binary_dir(binary)
    config._prepend_binary_dir(binary)

    entries = os.environ["PATH"].split(os.pathsep)
    assert entries[0] == r"C:\ffmpeg\bin"
    assert entries.count(r"C:\ffmpeg\bin") == 1
    assert entries[-1] == r"C:\Windows"


def test_prepend_binary_dir_ignores_bare_commands(monkeypatch) -> None:
    monkeypatch.setenv("PATH", r"C:\Windows")

    config._prepend_binary_dir("ffmpeg")
    config._prepend_binary_dir(None)

    assert os.environ["PATH"] == r"C:\Windows"
