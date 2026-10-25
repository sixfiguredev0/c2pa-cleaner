"""
Tests for WebP RIFF chunk stream parsing, C2PA chunk detection and lossless removal.
"""

import os
import subprocess
from PIL import Image
import io
import pytest

from app.backend.parsers.webp import parse_and_strip_webp


FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")
C2PATOOL_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "tools", "c2patool", "c2patool.exe")


def test_webp_without_c2pa():
    path = os.path.join(FIXTURES_DIR, "mars.webp")
    with open(path, "rb") as f:
        data = f.read()

    res = parse_and_strip_webp(data)
    assert res.is_valid is True
    assert res.has_c2pa is False
    assert res.c2pa_chunk_count == 0
    assert res.c2pa_total_bytes == 0
    assert "VP8X" in res.retained_chunks
    assert "VP8 " in res.retained_chunks
    assert res.cleaned_bytes == data


def test_webp_with_c2pa():
    path = os.path.join(FIXTURES_DIR, "signed_mars.webp")
    with open(path, "rb") as f:
        data = f.read()

    res = parse_and_strip_webp(data)
    assert res.is_valid is True
    assert res.has_c2pa is True
    assert res.c2pa_chunk_count == 1
    assert res.c2pa_total_bytes == 1690984

    # Verify exact match with un-signed mars.webp
    orig_path = os.path.join(FIXTURES_DIR, "mars.webp")
    with open(orig_path, "rb") as f:
        orig_data = f.read()

    assert res.cleaned_bytes == orig_data

    # Verify Pillow decodes the cleaned file
    with Image.open(io.BytesIO(res.cleaned_bytes)) as img:
        img.load()
        assert img.format == "WEBP"


def test_webp_corruptions():
    # Bad header
    res = parse_and_strip_webp(b"NOT_A_WEBP_FILE")
    assert res.is_valid is False
    assert "Invalid WebP header" in res.error_message

    # Truncated chunk header
    res2 = parse_and_strip_webp(b"RIFF\x10\x00\x00\x00WEBPVP")
    assert res2.is_valid is False
    assert "Truncated" in res2.error_message


@pytest.mark.skipif(not os.path.exists(C2PATOOL_PATH), reason="c2patool not found")
def test_webp_validation_with_c2patool(tmp_path):
    orig_path = os.path.join(FIXTURES_DIR, "signed_mars.webp")
    clean_path = str(tmp_path / "cleaned_mars.webp")

    with open(orig_path, "rb") as f:
        res = parse_and_strip_webp(f.read())
    with open(clean_path, "wb") as f:
        f.write(res.cleaned_bytes)

    # Run c2patool on original -> active_manifest present
    proc_orig = subprocess.run([C2PATOOL_PATH, orig_path], capture_output=True, text=True)
    assert proc_orig.returncode == 0
    assert "active_manifest" in proc_orig.stdout

    # Run c2patool on cleaned -> No claim found
    proc_clean = subprocess.run([C2PATOOL_PATH, clean_path], capture_output=True, text=True)
    assert proc_clean.returncode != 0
    assert "No claim found" in proc_clean.stderr or "No claim found" in proc_clean.stdout
