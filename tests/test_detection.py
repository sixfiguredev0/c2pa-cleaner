"""
Tests for binary signature format detection.
"""

import pytest
from app.backend.parsers.detector import detect_format, ImageFormat


def test_detect_jpeg():
    data = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    res = detect_format(data)
    assert res.format == ImageFormat.JPEG
    assert res.is_supported is True
    assert res.mime_type == "image/jpeg"
    assert res.extension == ".jpg"


def test_detect_png():
    data = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00"
    res = detect_format(data)
    assert res.format == ImageFormat.PNG
    assert res.is_supported is True
    assert res.mime_type == "image/png"
    assert res.extension == ".png"


def test_detect_webp():
    data = b"RIFF\x14\x00\x00\x00WEBPVP8 \x08\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
    res = detect_format(data)
    assert res.format == ImageFormat.WEBP
    assert res.is_supported is True
    assert res.mime_type == "image/webp"
    assert res.extension == ".webp"


def test_detect_unsupported_formats():
    # GIF
    res_gif = detect_format(b"GIF89a\x01\x00\x01\x00\x80\x00\x00\xff\xff\xff\x00\x00\x00!\xf9")
    assert res_gif.format == ImageFormat.GIF
    assert res_gif.is_supported is False

    # TIFF (little endian)
    res_tiff = detect_format(b"II*\x00\x08\x00\x00\x00\x00\x00\x00\x00\x00\x00")
    assert res_tiff.format == ImageFormat.TIFF
    assert res_tiff.is_supported is False

    # BMP
    res_bmp = detect_format(b"BM\x36\x00\x00\x00\x00\x00\x00\x00\x36\x00\x00\x00")
    assert res_bmp.format == ImageFormat.BMP
    assert res_bmp.is_supported is False

    # AVIF
    res_avif = detect_format(b"\x00\x00\x00\x1cftypavif\x00\x00\x00\x00avifmif1")
    assert res_avif.format == ImageFormat.AVIF
    assert res_avif.is_supported is False

    # HEIC
    res_heic = detect_format(b"\x00\x00\x00\x1cftypheic\x00\x00\x00\x00mif1msf1")
    assert res_heic.format == ImageFormat.HEIC
    assert res_heic.is_supported is False


def test_detect_corrupt_and_truncated():
    assert detect_format(b"").is_supported is False
    assert detect_format(b"\xff\xd8").is_supported is False  # too short
    assert detect_format(b"random gibberish binary data").is_supported is False
