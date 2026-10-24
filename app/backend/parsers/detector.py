"""
File format detection based strictly on binary signatures (magic bytes).
Never relies on file extension or user-provided MIME types.
"""

from enum import Enum
from typing import NamedTuple, Optional, Tuple


class ImageFormat(str, Enum):
    JPEG = "JPEG"
    PNG = "PNG"
    WEBP = "WEBP"
    GIF = "GIF"
    TIFF = "TIFF"
    BMP = "BMP"
    AVIF = "AVIF"
    HEIC = "HEIC"
    UNKNOWN = "UNKNOWN"


class DetectionResult(NamedTuple):
    format: ImageFormat
    is_supported: bool
    mime_type: str
    extension: str
    message: str


# Supported formats in C2PA Cleaner v1
SUPPORTED_FORMATS = {
    ImageFormat.JPEG: ("image/jpeg", ".jpg"),
    ImageFormat.PNG: ("image/png", ".png"),
    ImageFormat.WEBP: ("image/webp", ".webp"),
}

UNSUPPORTED_FORMAT_MESSAGES = {
    ImageFormat.GIF: "GIF format is not currently supported for C2PA removal in this version.",
    ImageFormat.TIFF: "TIFF format is not currently supported for C2PA removal in this version.",
    ImageFormat.BMP: "BMP format is not currently supported for C2PA removal in this version.",
    ImageFormat.AVIF: "AVIF format is not currently supported for C2PA removal in this version.",
    ImageFormat.HEIC: "HEIC/HEIF format is not currently supported for C2PA removal in this version.",
    ImageFormat.UNKNOWN: "Unrecognized or corrupted file format signature.",
}


def detect_format(data: bytes) -> DetectionResult:
    """
    Inspect the binary data header and determine the actual image container format.
    """
    if len(data) < 12:
        return DetectionResult(
            format=ImageFormat.UNKNOWN,
            is_supported=False,
            mime_type="application/octet-stream",
            extension="",
            message="File is too small to contain a valid image header.",
        )

    # 1. JPEG signature: 0xFF, 0xD8, 0xFF
    if data[0:2] == b"\xff\xd8" and data[2] == 0xff:
        return DetectionResult(
            format=ImageFormat.JPEG,
            is_supported=True,
            mime_type="image/jpeg",
            extension=".jpg",
            message="Valid JPEG image container detected.",
        )

    # 2. PNG signature: 89 50 4E 47 0D 0A 1A 0A
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return DetectionResult(
            format=ImageFormat.PNG,
            is_supported=True,
            mime_type="image/png",
            extension=".png",
            message="Valid PNG image container detected.",
        )

    # 3. WebP / RIFF signature: b"RIFF" + 4 bytes size + b"WEBP"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return DetectionResult(
            format=ImageFormat.WEBP,
            is_supported=True,
            mime_type="image/webp",
            extension=".webp",
            message="Valid WebP image container detected.",
        )

    # 4. GIF signature: b"GIF87a" or b"GIF89a"
    if data.startswith(b"GIF87a") or data.startswith(b"GIF89a"):
        return DetectionResult(
            format=ImageFormat.GIF,
            is_supported=False,
            mime_type="image/gif",
            extension=".gif",
            message=UNSUPPORTED_FORMAT_MESSAGES[ImageFormat.GIF],
        )

    # 5. TIFF signature: b"II*\x00" (little endian) or b"MM\x00*" (big endian)
    if data.startswith(b"II*\x00") or data.startswith(b"MM\x00*"):
        return DetectionResult(
            format=ImageFormat.TIFF,
            is_supported=False,
            mime_type="image/tiff",
            extension=".tiff",
            message=UNSUPPORTED_FORMAT_MESSAGES[ImageFormat.TIFF],
        )

    # 6. BMP signature: b"BM"
    if data.startswith(b"BM"):
        return DetectionResult(
            format=ImageFormat.BMP,
            is_supported=False,
            mime_type="image/bmp",
            extension=".bmp",
            message=UNSUPPORTED_FORMAT_MESSAGES[ImageFormat.BMP],
        )

    # 7. ISOBMFF / ftyp checks (AVIF, HEIC, HEIF)
    if len(data) >= 16 and data[4:8] == b"ftyp":
        major_brand = data[8:12]
        if major_brand in (b"avif", b"avis"):
            return DetectionResult(
                format=ImageFormat.AVIF,
                is_supported=False,
                mime_type="image/avif",
                extension=".avif",
                message=UNSUPPORTED_FORMAT_MESSAGES[ImageFormat.AVIF],
            )
        if major_brand in (b"heic", b"heix", b"heim", b"heis", b"mif1", b"msf1"):
            return DetectionResult(
                format=ImageFormat.HEIC,
                is_supported=False,
                mime_type="image/heic",
                extension=".heic",
                message=UNSUPPORTED_FORMAT_MESSAGES[ImageFormat.HEIC],
            )

    return DetectionResult(
        format=ImageFormat.UNKNOWN,
        is_supported=False,
        mime_type="application/octet-stream",
        extension="",
        message=UNSUPPORTED_FORMAT_MESSAGES[ImageFormat.UNKNOWN],
    )
