from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from app import transcribe as transcribe_module


class FakeModel:
    def __init__(self, segments):
        self._segments = segments
        self.calls: list[dict] = []

    def transcribe(self, path: str, **kwargs):
        self.calls.append({"path": path, **kwargs})
        return iter(self._segments), SimpleNamespace(
            language="es",
            language_probability=0.94,
        )


def test_transcribe_single_applies_offset_and_builds_fallback_words() -> None:
    model = FakeModel(
        [
            SimpleNamespace(
                start=0.5,
                end=2.0,
                text="hola",
                words=[
                    SimpleNamespace(
                        word="hola",
                        start=0.6,
                        end=1.2,
                        probability=0.91,
                    )
                ],
            ),
            SimpleNamespace(
                start=2.5,
                end=4.0,
                text="mundo cruel",
                words=None,
            ),
        ]
    )
    progress: list[float] = []

    segments, info = transcribe_module._transcribe_single(
        model,
        Path("audio.wav"),
        10.0,
        language="es",
        offset=100.0,
        total_duration=200.0,
        on_progress=progress.append,
    )

    assert info.language == "es"
    assert len(segments) == 2
    first, second = segments
    assert first["start"] == pytest.approx(100.5)
    assert first["end"] == pytest.approx(102.0)
    assert first["words"][0]["start"] == pytest.approx(100.6)
    assert first["words"][0]["end"] == pytest.approx(101.2)

    assert second["start"] == pytest.approx(102.5)
    assert second["end"] == pytest.approx(104.0)
    assert [word["w"] for word in second["words"]] == ["mundo", "cruel"]
    assert second["words"][0]["start"] == pytest.approx(102.5)
    assert second["words"][-1]["end"] == pytest.approx(104.0)

    # One report per segment, scaled against the total source duration.
    assert progress == pytest.approx([51.0, 52.0])


def test_transcribe_chunks_long_audio_and_keeps_source_offsets(monkeypatch) -> None:
    calls: list[tuple[str, float, float]] = []
    progress: list[float] = []

    monkeypatch.setattr(transcribe_module, "_get_model", lambda: object())

    def fake_chunk_audio(audio_path: Path, duration: float, *, directory: Path, cached_offsets):
        assert audio_path == Path("audio.wav")
        assert duration == pytest.approx(700.0)
        return [
            (Path("chunk_000.wav"), 0.0, 420.0),
            (Path("chunk_001.wav"), 420.0, 280.0),
        ]

    def fake_transcribe_single(
        model,
        audio_path: Path,
        duration: float,
        *,
        language: str | None,
        offset: float,
        total_duration: float,
        on_progress,
    ):
        calls.append((audio_path.name, offset, duration))
        return (
            [
                {
                    "start": offset + 1.0,
                    "end": offset + 2.0,
                    "text": audio_path.name,
                    "words": [],
                }
            ],
            SimpleNamespace(language="es", language_probability=0.9),
        )

    monkeypatch.setattr(transcribe_module, "_chunk_audio", fake_chunk_audio)
    monkeypatch.setattr(
        transcribe_module, "_transcribe_single", fake_transcribe_single
    )

    result = transcribe_module.transcribe(
        Path("audio.wav"),
        700.0,
        language="es",
        on_progress=progress.append,
    )

    assert calls == [
        ("chunk_000.wav", 0.0, 420.0),
        ("chunk_001.wav", 420.0, 280.0),
    ]
    assert [segment["start"] for segment in result["segments"]] == [1.0, 421.0]
    assert result["language"] == "es"
    assert result["language_probability"] == 0.9
    assert progress[-1] == 99.0


def test_short_transcript_is_returned_with_checkpoint_dir(monkeypatch, tmp_path):
    model = FakeModel([SimpleNamespace(start=0, end=2, text="¿Qué pasó?", words=[])])
    monkeypatch.setattr(transcribe_module, "_get_model", lambda: model)
    result = transcribe_module.transcribe(Path("audio.wav"), 32, checkpoint_dir=tmp_path)
    assert result["segments"][0]["text"] == "¿Qué pasó?"
    assert result["language"] == "es"


def test_fully_resumed_job_reuses_speech_without_decoding(monkeypatch, tmp_path):
    import json
    checkpoint = tmp_path / "asr_checkpoint.jsonl"
    checkpoint.write_text("\n".join(json.dumps({"offset": t, "segments": [{"start": t}]})
                                    for t in (0, 420)))
    result = transcribe_module.transcribe(tmp_path / "unused.wav", 600, language="es",
                                          checkpoint_dir=tmp_path)
    assert result["segments"] == [{"start": 0}, {"start": 420}]
    assert not checkpoint.exists()
