"""
Tests for PNG chunk stream parsing, caBX chunk detection and lossless removal.
"""

import os
import subprocess
from PIL import Image
import io
import pytest

from app.backend.parsers.png import parse_and_strip_png


FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")
C2PATOOL_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "tools", "c2patool", "c2patool.exe")


def test_png_without_c2pa():
    path = os.path.join(FIXTURES_DIR, "libpng-test.png")
    with open(path, "rb") as f:
        data = f.read()

    res = parse_and_strip_png(data)
    assert res.is_valid is True
    assert res.has_c2pa is False
    assert res.c2pa_chunk_count == 0
    assert res.c2pa_total_bytes == 0
    assert "PLTE" in res.retained_chunks
    assert "IDAT" in res.retained_chunks
    assert res.cleaned_bytes == data


def test_png_with_c2pa():
    path = os.path.join(FIXTURES_DIR, "signed_test.png")
    with open(path, "rb") as f:
        data = f.read()

    res = parse_and_strip_png(data)
    assert res.is_valid is True
    assert res.has_c2pa is True
    assert res.c2pa_chunk_count == 1
    assert res.c2pa_total_bytes == 863774
    assert res.cleaned_bytes is not None

    # Load original un-signed file
    orig_path = os.path.join(FIXTURES_DIR, "libpng-test.png")
    with open(orig_path, "rb") as f:
        orig_data = f.read()

    # Must be 100% byte-for-byte identical to the original un-signed file!
    assert res.cleaned_bytes == orig_data

    # Verify Pillow decodes the cleaned file
    with Image.open(io.BytesIO(res.cleaned_bytes)) as img:
        img.load()
        assert img.format == "PNG"


def test_png_preserves_ancillary_chunks():
    path = os.path.join(FIXTURES_DIR, "sample1.png")
    with open(path, "rb") as f:
        data = f.read()

    res = parse_and_strip_png(data)
    assert res.is_valid is True
    assert res.has_c2pa is False
    # All ancillary chunks preserved
    for chunk_name in ["gAMA", "sRGB", "bKGD", "pHYs", "eXIf", "tEXt"]:
        assert chunk_name in res.retained_chunks
    assert res.cleaned_bytes == data


def test_png_corruptions():
    # Bad signature
    res = parse_and_strip_png(b"NOT_A_PNG_FILE_HEADER")
    assert res.is_valid is False
    assert "Invalid PNG signature" in res.error_message

    # Truncated chunk header
    res2 = parse_and_strip_png(b"\x89PNG\r\n\x1a\n\x00\x00")
    assert res2.is_valid is False
    assert "Truncated" in res2.error_message

    # CRC mismatch
    bad_crc_chunk = (
        b"\x89PNG\r\n\x1a\n"
        b"\x00\x00\x00\x01"  # len = 1
        b"IHDR"              # type
        b"\x00"              # data
        b"\xff\xff\xff\xff"  # invalid CRC
    )
    res3 = parse_and_strip_png(bad_crc_chunk)
    assert res3.is_valid is False
    assert "CRC mismatch" in res3.error_message

    # Missing IEND
    no_iend = (
        b"\x89PNG\r\n\x1a\n"
        b"\x00\x00\x00\x00"
        b"IHDR"
        b"\x00\x00\x00\x00"  # fake CRC
    )
    res4 = parse_and_strip_png(no_iend)
    assert res4.is_valid is False


@pytest.mark.skipif(not os.path.exists(C2PATOOL_PATH), reason="c2patool not found")
def test_png_validation_with_c2patool(tmp_path):
    orig_path = os.path.join(FIXTURES_DIR, "signed_test.png")
    clean_path = str(tmp_path / "cleaned_test.png")

    with open(orig_path, "rb") as f:
        res = parse_and_strip_png(f.read())
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
