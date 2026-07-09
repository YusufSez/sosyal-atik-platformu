"""Zaman damgası yardımcıları — UTC saklama, yerel gösterim."""

from datetime import datetime, timezone

from utils import APP_TIMEZONE, format_datetime, to_local, to_utc, tr_time, utc_now


def test_tr_time_returns_naive_utc():
    value = tr_time()
    assert value.tzinfo is None


def test_utc_now_is_naive():
    value = utc_now()
    assert value.tzinfo is None


def test_to_local_adds_istanbul_offset():
    utc_value = datetime(2026, 7, 9, 12, 0, 0)
    local = to_local(utc_value)
    assert local.tzinfo is None
    assert local.hour == 15
    assert local.day == utc_value.day


def test_to_utc_from_local_midnight():
    local = datetime(2026, 7, 9, 0, 0, 0)
    utc_value = to_utc(local)
    assert utc_value.tzinfo is None
    assert utc_value.hour == 21
    assert utc_value.day == 8


def test_format_datetime_default_pattern():
    utc_value = datetime(2026, 1, 15, 9, 30, 0)
    formatted = format_datetime(utc_value)
    assert formatted == "15.01.2026 12:30"


def test_format_datetime_none():
    assert format_datetime(None) == "-"


def test_app_timezone_is_istanbul():
    assert str(APP_TIMEZONE) == "Europe/Istanbul"
