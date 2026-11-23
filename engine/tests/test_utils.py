from __future__ import annotations

from app.utils import (
    clamp,
    fmt_ass_time,
    fmt_seconds,
    fmt_srt_time,
    parse_json_object,
)


def test_time_formatters() -> None:
    assert fmt_seconds(1.5) == "1.500"
    assert fmt_seconds(-3.0) == "0.000"
    assert fmt_ass_time(3661.239) == "1:01:01.24"
    assert fmt_srt_time(3661.239) == "01:01:01,239"
    assert fmt_srt_time(0.0) == "00:00:00,000"


def test_clamp() -> None:
    assert clamp(5, 0, 10) == 5
    assert clamp(-1, 0, 10) == 0
    assert clamp(11, 0, 10) == 10


def test_parse_json_object_extracts_object_from_text() -> None:
    assert parse_json_object('texto {"a": 1, "b": [2, 3]} fin') == {
        "a": 1,
        "b": [2, 3],
    }


def test_parse_json_object_rejects_invalid_payloads() -> None:
    assert parse_json_object("") is None
    assert parse_json_object("sin llaves") is None
    assert parse_json_object("{roto}") is None
    assert parse_json_object("[1, 2, 3]") is None
