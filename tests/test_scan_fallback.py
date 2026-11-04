"""Medicine scan fallback: Gemini is mocked; no network, no key, no cost."""
import concurrent.futures
from unittest import mock

import pytest

from ai import scan_fallback as sf

IMG = b"\xff\xd8\xff" + b"0" * 100
GOOD = {"batch": "NL2533", "expiry": "08/2027", "batch_conf": "0.95", "expiry_conf": "0.92"}


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    sf.reset_controls_for_tests()
    monkeypatch.delenv("GEMINI_FALLBACK_ENABLED", raising=False)
    yield


def _on(monkeypatch):
    monkeypatch.setenv("GEMINI_FALLBACK_ENABLED", "true")


def test_clear_ocr_never_calls_gemini(monkeypatch):
    _on(monkeypatch)
    with mock.patch.object(sf, "_call_gemini") as g:
        r = sf.resolve_scan(IMG, GOOD, 1)
    assert g.call_count == 0 and r["scan_source"] == "ocr" and r["batch_number"] == "NL2533"
    assert r["expiry_date"] == "2027-08" and r["uncertain_fields"] == []


@pytest.mark.parametrize("ocr", [
    {}, {"batch": "NL2533"}, {"expiry": "08/2027"},
    {"batch": "NL2533", "expiry": "08/2027", "batch_conf": "0.4", "expiry_conf": "0.9"},
    {"batch": "11/2025", "expiry": "08/2027"},  # date-like batch is invalid
])
def test_unclear_ocr_calls_gemini_when_on(monkeypatch, ocr):
    _on(monkeypatch)
    with mock.patch.object(sf, "_call_gemini", return_value={"batch_number": "AB1234", "expiry_date": "2028-03"}) as g:
        r = sf.resolve_scan(IMG, ocr, 1)
    assert g.call_count == 1 and r["scan_source"] == "fallback" and r["gemini_calls"] == 1
    assert r["expiry_date"] and r["batch_number"]


def test_kill_switch_off_never_calls(monkeypatch):
    with mock.patch.object(sf, "_call_gemini") as g:
        r = sf.resolve_scan(IMG, {"batch": "NL2533"}, 1)
    assert g.call_count == 0 and r["scan_source"] == "ocr_partial" and r["reason"] == "fallback_off"
    assert r["uncertain_fields"] == ["expiry_date"] and r["batch_number"] == "NL2533"


def test_failure_and_timeout_degrade_to_ocr(monkeypatch):
    _on(monkeypatch)
    for exc in (RuntimeError("boom"), concurrent.futures.TimeoutError()):
        sf.reset_controls_for_tests()
        with mock.patch.object(sf, "_call_gemini", side_effect=exc), mock.patch.object(sf.time, "sleep"):
            r = sf.resolve_scan(IMG, {"batch": "NL2533", "batch_conf": "0.95"}, 1)
        assert r["reason"] == "fallback_failed" and r["batch_number"] == "NL2533" and r["needs_manual_review"]


def test_retry_is_at_most_one(monkeypatch):
    _on(monkeypatch)
    with mock.patch.object(sf, "_call_gemini", side_effect=RuntimeError("503 UNAVAILABLE")) as g, \
            mock.patch.object(sf.time, "sleep"):
        sf.resolve_scan(IMG, {}, 1)
    assert g.call_count == 2


def test_cap_reached(monkeypatch):
    _on(monkeypatch)
    monkeypatch.setenv("GEMINI_FALLBACK_HOURLY_CALLS", "1")
    with mock.patch.object(sf, "_call_gemini", return_value={"batch_number": "AB1234"}) as g:
        sf.resolve_scan(IMG, {}, 7)
        r = sf.resolve_scan(IMG + b"x", {}, 7)
        other = sf.resolve_scan(IMG + b"y", {}, 8)  # another pharmacy is unaffected
    assert r["reason"] == "cap_reached" and r["scan_source"] == "failed" and g.call_count == 2 and other["gemini_calls"] == 1


def test_duplicate_image_uses_cache(monkeypatch):
    _on(monkeypatch)
    with mock.patch.object(sf, "_call_gemini", return_value={"batch_number": "AB1234"}) as g:
        sf.resolve_scan(IMG, {}, 1)
        r = sf.resolve_scan(IMG, {}, 1)
    assert g.call_count == 1 and r["gemini_calls"] == 0 and r["batch_number"] == "AB1234"


def test_trusted_ocr_value_never_overwritten(monkeypatch):
    _on(monkeypatch)
    ocr = {"batch": "NL2533", "batch_conf": "0.95"}  # expiry missing -> Gemini runs
    with mock.patch.object(sf, "_call_gemini", return_value={"batch_number": "ZZ9999", "expiry_date": "2028-03"}):
        r = sf.resolve_scan(IMG, ocr, 1)
    assert r["batch_number"] == "NL2533" and r["expiry_date"] == "2028-03"


def test_invalid_gemini_values_are_blanked_not_invented(monkeypatch):
    _on(monkeypatch)
    bad = {"batch_number": "08/2027", "expiry_date": "2099-01", "mrp": 155.96}
    with mock.patch.object(sf, "_call_gemini", return_value=bad):
        r = sf.resolve_scan(IMG, {}, 1)
    assert r["batch_number"] is None and r["expiry_date"] is None
    assert set(r["uncertain_fields"]) == {"batch_number", "expiry_date"} and r["mrp"] == 155.96


def test_price_like_batch_rejected_and_mrp_separate(monkeypatch):
    _on(monkeypatch)
    with mock.patch.object(sf, "_call_gemini", return_value={"batch_number": "155.96", "expiry_date": "2028-03", "mrp": 155.96}):
        r = sf.resolve_scan(IMG, {}, 1)
    assert r["batch_number"] is None and r["mrp"] == 155.96


def test_response_never_mentions_gemini(monkeypatch):
    _on(monkeypatch)
    with mock.patch.object(sf, "_call_gemini", side_effect=RuntimeError("Gemini quota")):
        r = sf.resolve_scan(IMG, {}, 1)
    assert "gemini" not in f"{r['message']} {r['reason']}".lower()  # user-facing text only; field names stay
