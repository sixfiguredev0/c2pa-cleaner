"""
Tests for JPEG marker parsing, C2PA JUMBF APP11 detection and lossless removal.
"""

import os
import subprocess
from PIL import Image
import io
import pytest

from app.backend.parsers.jpeg import parse_and_strip_jpeg, KNOWN_C2PA_UUIDS


FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")
C2PATOOL_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "tools", "c2patool", "c2patool.exe")


def test_jpeg_without_c2pa():
    path = os.path.join(FIXTURES_DIR, "no_manifest.jpg")
    with open(path, "rb") as f:
        data = f.read()

    res = parse_and_strip_jpeg(data)
    assert res.is_valid is True
    assert res.has_c2pa is False
    assert res.c2pa_segment_count == 0
    assert res.c2pa_total_bytes == 0
    assert "EXIF (APP1)" in res.retained_metadata
    assert "ICC Profile (APP2)" in res.retained_metadata
    assert res.cleaned_bytes == data


def test_jpeg_with_c2pa_multisegment():
    path = os.path.join(FIXTURES_DIR, "CA.jpg")
    with open(path, "rb") as f:
        data = f.read()

    res = parse_and_strip_jpeg(data)
    assert res.is_valid is True
    assert res.has_c2pa is True
    assert res.c2pa_segment_count == 2
    assert res.c2pa_total_bytes == 117273
    assert res.cleaned_bytes is not None
    assert len(res.cleaned_bytes) == len(data) - 117273

    # Verify that clean JPEG can be parsed again and reports 0 C2PA markers
    clean_res = parse_and_strip_jpeg(res.cleaned_bytes)
    assert clean_res.is_valid is True
    assert clean_res.has_c2pa is False
    assert clean_res.c2pa_segment_count == 0

    # Verify Pillow decodes clean JPEG
    with Image.open(io.BytesIO(res.cleaned_bytes)) as img:
        img.load()
        assert img.size == (1024, 683)
        assert img.format == "JPEG"


def test_jpeg_update_manifest():
    path = os.path.join(FIXTURES_DIR, "update_manifest.jpg")
    with open(path, "rb") as f:
        data = f.read()

    res = parse_and_strip_jpeg(data)
    assert res.is_valid is True
    assert res.has_c2pa is True
    assert res.c2pa_segment_count == 1
    assert res.c2pa_total_bytes == 43607

    with Image.open(io.BytesIO(res.cleaned_bytes)) as img:
        img.load()
        assert img.size == (375, 375)


def test_jpeg_preserves_unrelated_app11():
    """
    Test that an APP11 segment containing non-C2PA data is preserved,
    while a C2PA APP11 segment is removed.
    """
    # Construct an unrelated APP11 marker: Marker(2B) + Length(2B) + payload
    unrelated_payload = b"CUSTOM_APP11_VENDOR_DATA_123456789"
    unrelated_len = len(unrelated_payload) + 2
    unrelated_app11 = b"\xff\xeb" + unrelated_len.to_bytes(2, "big") + unrelated_payload

    # Load CA.jpg (which has C2PA APP11 markers)
    with open(os.path.join(FIXTURES_DIR, "CA.jpg"), "rb") as f:
        data = f.read()

    # Insert unrelated APP11 right after SOI (offset 2)
    modified_data = data[:2] + unrelated_app11 + data[2:]

    res = parse_and_strip_jpeg(modified_data)
    assert res.is_valid is True
    assert res.has_c2pa is True
    assert res.c2pa_segment_count == 2  # The 2 C2PA markers removed
    # The unrelated APP11 must still be present in the cleaned bytes!
    assert unrelated_app11 in res.cleaned_bytes


def test_jpeg_scan_data_exact_preservation():
    """
    Verify that the entropy-coded scan data (after the real image SOS) is 100% byte-for-byte identical.
    """
    with open(os.path.join(FIXTURES_DIR, "CA.jpg"), "rb") as f:
        data = f.read()

    res = parse_and_strip_jpeg(data)
    # Locate the real image SOS segment from the parsed segments
    orig_sos_segs = [s for s in res.segments if s.marker == 0xDA and not s.is_c2pa]
    assert len(orig_sos_segs) > 0

    clean_res = parse_and_strip_jpeg(res.cleaned_bytes)
    clean_sos_segs = [s for s in clean_res.segments if s.marker == 0xDA]
    assert len(clean_sos_segs) > 0

    orig_sos = orig_sos_segs[0]
    clean_sos = clean_sos_segs[0]

    # Everything from real image SOS through the end of the file must be byte-identical
    assert data[orig_sos.offset:] == res.cleaned_bytes[clean_sos.offset:]


def test_jpeg_corrupt_structures():
    # Truncated length
    res = parse_and_strip_jpeg(b"\xff\xd8\xff\xe0\x00")
    assert res.is_valid is False
    assert "Truncated" in res.error_message

    # Segment length exceeding file size
    res2 = parse_and_strip_jpeg(b"\xff\xd8\xff\xe0\xff\xff1234")
    assert res2.is_valid is False
    assert "Invalid segment length" in res2.error_message

    # Missing SOI
    res3 = parse_and_strip_jpeg(b"\x00\x00\x00\x00\x00")
    assert res3.is_valid is False
    assert "Missing JPEG SOI" in res3.error_message


@pytest.mark.skipif(not os.path.exists(C2PATOOL_PATH), reason="c2patool not found")
def test_jpeg_validation_with_c2patool(tmp_path):
    orig_path = os.path.join(FIXTURES_DIR, "CA.jpg")
    clean_path = str(tmp_path / "cleaned_CA.jpg")

    with open(orig_path, "rb") as f:
        res = parse_and_strip_jpeg(f.read())
    with open(clean_path, "wb") as f:
        f.write(res.cleaned_bytes)

    # Run c2patool on original -> should succeed (returns JSON)
    proc_orig = subprocess.run([C2PATOOL_PATH, orig_path], capture_output=True, text=True)
    assert proc_orig.returncode == 0
    assert "active_manifest" in proc_orig.stdout

    # Run c2patool on cleaned -> must report "No claim found" (exit code != 0)
    proc_clean = subprocess.run([C2PATOOL_PATH, clean_path], capture_output=True, text=True)
    assert proc_clean.returncode != 0
    assert "No claim found" in proc_clean.stderr or "No claim found" in proc_clean.stdout
