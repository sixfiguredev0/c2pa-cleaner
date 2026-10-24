"""
Independent verification and file integrity engine.
Validates structural integrity, image bitstream preservation, absence of C2PA remnants,
and decodability of the resulting output.
"""

import io
from typing import NamedTuple, Optional, List, Dict, Any
from PIL import Image

from app.backend.parsers.detector import detect_format, ImageFormat
from app.backend.parsers.jpeg import parse_and_strip_jpeg
from app.backend.parsers.png import parse_and_strip_png
from app.backend.parsers.webp import parse_and_strip_webp


class VerificationCheck(NamedTuple):
    name: str
    passed: bool
    details: str


class VerificationResult(NamedTuple):
    is_valid: bool
    summary: str
    format: ImageFormat
    checks: List[VerificationCheck]
    dimensions: Optional[Tuple[int, int]]
    mode: Optional[str]


def verify_cleaned_file(original_bytes: bytes, cleaned_bytes: bytes, expected_format: ImageFormat) -> VerificationResult:
    """
    Perform multi-level independent verification on the cleaned image bytes.
    """
    checks: List[VerificationCheck] = []
    dimensions: Optional[Tuple[int, int]] = None
    mode: Optional[str] = None

    # Check 1: Format signature matches expected format
    det = detect_format(cleaned_bytes)
    sig_ok = (det.format == expected_format and det.is_supported)
    checks.append(VerificationCheck(
        name="Container Signature",
        passed=sig_ok,
        details=f"Detected container format: {det.format.value} ({det.mime_type})",
    ))

    if not sig_ok:
        return VerificationResult(
            is_valid=False,
            summary="Verification failed: Output file has invalid container signature.",
            format=det.format,
            checks=checks,
            dimensions=None,
            mode=None,
        )

    # Check 2: C2PA Absence & Container Structure
    no_c2pa = False
    structure_ok = False
    details_str = ""

    if expected_format == ImageFormat.JPEG:
        res = parse_and_strip_jpeg(cleaned_bytes)
        structure_ok = res.is_valid
        no_c2pa = not res.has_c2pa
        details_str = f"JPEG markers parsed: {len(res.segments)}, C2PA markers remaining: {res.c2pa_segment_count}"
    elif expected_format == ImageFormat.PNG:
        res = parse_and_strip_png(cleaned_bytes)
        structure_ok = res.is_valid
        no_c2pa = not res.has_c2pa
        details_str = f"PNG chunks parsed: {len(res.chunks)}, caBX chunks remaining: {res.c2pa_chunk_count}"
    elif expected_format == ImageFormat.WEBP:
        res = parse_and_strip_webp(cleaned_bytes)
        structure_ok = res.is_valid
        no_c2pa = not res.has_c2pa
        details_str = f"WebP chunks parsed: {len(res.chunks)}, C2PA chunks remaining: {res.c2pa_chunk_count}"

    checks.append(VerificationCheck(
        name="Structural Container Integrity",
        passed=structure_ok,
        details="Container headers, lengths, and terminating markers are structurally valid." if structure_ok else "Corrupt structure.",
    ))

    checks.append(VerificationCheck(
        name="C2PA Provenance Absence",
        passed=no_c2pa,
        details="No embedded C2PA manifest segments or chunks found in output." if no_c2pa else "C2PA structures detected in output!",
    ))

    # Check 3: Image data preservation (Bitstream / IDAT / Scans)
    data_intact = False
    intact_details = ""

    if expected_format == ImageFormat.JPEG:
        # Extract SOS scan entropy bytes from original and cleaned
        orig_res = parse_and_strip_jpeg(original_bytes)
        clean_res = parse_and_strip_jpeg(cleaned_bytes)
        orig_scans = [original_bytes[s.offset : s.offset + s.length] for s in orig_res.segments if s.marker == 0xDA]
        clean_scans = [cleaned_bytes[s.offset : s.offset + s.length] for s in clean_res.segments if s.marker == 0xDA]
        data_intact = (orig_scans == clean_scans and len(orig_scans) > 0)
        intact_details = "JPEG entropy-coded scan data (SOS) is 100% byte-identical to original." if data_intact else "Scan data altered or missing!"
    elif expected_format == ImageFormat.PNG:
        # Extract IDAT payloads from original and cleaned
        orig_res = parse_and_strip_png(original_bytes)
        clean_res = parse_and_strip_png(cleaned_bytes)
        orig_idats = [original_bytes[c.offset + 8 : c.offset + 8 + c.length] for c in orig_res.chunks if c.chunk_type == b"IDAT"]
        clean_idats = [cleaned_bytes[c.offset + 8 : c.offset + 8 + c.length] for c in clean_res.chunks if c.chunk_type == b"IDAT"]
        data_intact = (b"".join(orig_idats) == b"".join(clean_idats) and len(orig_idats) > 0)
        intact_details = "PNG image data stream (IDAT) is 100% byte-identical to original." if data_intact else "IDAT data altered or missing!"
    elif expected_format == ImageFormat.WEBP:
        # Extract VP8/VP8L chunks from original and cleaned
        orig_res = parse_and_strip_webp(original_bytes)
        clean_res = parse_and_strip_webp(cleaned_bytes)
        orig_vp8 = [original_bytes[c.offset + 8 : c.offset + 8 + c.payload_size] for c in orig_res.chunks if c.fourcc in (b"VP8 ", b"VP8L")]
        clean_vp8 = [cleaned_bytes[c.offset + 8 : c.offset + 8 + c.payload_size] for c in clean_res.chunks if c.fourcc in (b"VP8 ", b"VP8L")]
        data_intact = (orig_vp8 == clean_vp8 and len(orig_vp8) > 0)
        intact_details = "WebP visual bitstream (VP8/VP8L) is 100% byte-identical to original." if data_intact else "WebP visual data altered or missing!"

    checks.append(VerificationCheck(
        name="Lossless Pixel Data Preservation",
        passed=data_intact,
        details=intact_details,
    ))

    # Check 4: Decodability test
    decode_ok = False
    try:
        with Image.open(io.BytesIO(cleaned_bytes)) as img:
            img.load()  # Force full pixel decoding
            dimensions = img.size
            mode = img.mode
            decode_ok = True
            decode_details = f"Decoded successfully: {dimensions[0]}x{dimensions[1]} pixels, {mode} mode."
    except Exception as e:
        decode_details = f"Failed to decode image pixels: {str(e)}"

    checks.append(VerificationCheck(
        name="Image Rendering & Decodability",
        passed=decode_ok,
        details=decode_details,
    ))

    overall_ok = all(c.passed for c in checks)
    summary = "File verified successfully: container is intact, C2PA removed, pixel data unchanged, and decodable." if overall_ok else "File integrity verification failed."

    return VerificationResult(
        is_valid=overall_ok,
        summary=summary,
        format=expected_format,
        checks=checks,
        dimensions=dimensions,
        mode=mode,
    )
