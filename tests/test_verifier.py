"""
Tests for independent verification engine.
"""

import os
import pytest

from app.backend.parsers.detector import ImageFormat
from app.backend.parsers.jpeg import parse_and_strip_jpeg
from app.backend.parsers.png import parse_and_strip_png
from app.backend.parsers.webp import parse_and_strip_webp
from app.backend.parsers.verifier import verify_cleaned_file


FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def test_verify_clean_jpeg():
    with open(os.path.join(FIXTURES_DIR, "CA.jpg"), "rb") as f:
        orig = f.read()

    res = parse_and_strip_jpeg(orig)
    ver = verify_cleaned_file(orig, res.cleaned_bytes, ImageFormat.JPEG)
    assert ver.is_valid is True
    assert all(c.passed for c in ver.checks)
    assert ver.dimensions == (1024, 683)


def test_verify_clean_png():
    with open(os.path.join(FIXTURES_DIR, "signed_test.png"), "rb") as f:
        orig = f.read()

    res = parse_and_strip_png(orig)
    ver = verify_cleaned_file(orig, res.cleaned_bytes, ImageFormat.PNG)
    assert ver.is_valid is True
    assert all(c.passed for c in ver.checks)


def test_verify_clean_webp():
    with open(os.path.join(FIXTURES_DIR, "signed_mars.webp"), "rb") as f:
        orig = f.read()

    res = parse_and_strip_webp(orig)
    ver = verify_cleaned_file(orig, res.cleaned_bytes, ImageFormat.WEBP)
    assert ver.is_valid is True
    assert all(c.passed for c in ver.checks)


def test_verify_fails_if_c2pa_remains():
    with open(os.path.join(FIXTURES_DIR, "CA.jpg"), "rb") as f:
        orig = f.read()

    # Pass original (with C2PA) as cleaned bytes
    ver = verify_cleaned_file(orig, orig, ImageFormat.JPEG)
    assert ver.is_valid is False
    c2pa_check = next(c for c in ver.checks if c.name == "C2PA Provenance Absence")
    assert c2pa_check.passed is False


def test_verify_fails_if_scans_altered():
    with open(os.path.join(FIXTURES_DIR, "CA.jpg"), "rb") as f:
        orig = f.read()

    res = parse_and_strip_jpeg(orig)
    # Tamper with scan data in cleaned bytes
    tampered = bytearray(res.cleaned_bytes)
    tampered[-50] = (tampered[-50] + 1) % 256
    ver = verify_cleaned_file(orig, bytes(tampered), ImageFormat.JPEG)
    assert ver.is_valid is False
    scan_check = next(c for c in ver.checks if c.name == "Lossless Pixel Data Preservation")
    assert scan_check.passed is False


def test_verify_fails_on_corrupt_container():
    with open(os.path.join(FIXTURES_DIR, "CA.jpg"), "rb") as f:
        orig = f.read()

    ver = verify_cleaned_file(orig, b"\x00\x00\x00\x00corrupt", ImageFormat.JPEG)
    assert ver.is_valid is False
    sig_check = next(c for c in ver.checks if c.name == "Container Signature")
    assert sig_check.passed is False
