"""
Core application service managing image inspection, C2PA removal, verification,
in-memory artifact caching, SynthID status reporting, and batch processing.
"""

import io
import json
import os
import subprocess
import sys
import tempfile
import uuid
import zipfile
from typing import Dict, List, Optional, Any, Tuple
from PIL import Image

from app.backend.parsers.detector import detect_format, ImageFormat
from app.backend.parsers.jpeg import parse_and_strip_jpeg
from app.backend.parsers.png import parse_and_strip_png
from app.backend.parsers.webp import parse_and_strip_webp
from app.backend.parsers.verifier import verify_cleaned_file, VerificationResult


MAX_FILE_SIZE = 100 * 1024 * 1024  # 100 MB safe limit

# The 5 official states for Content-Level Watermarks (SynthID)
SYNTHID_STATES = [
    "Not checked",
    "Detected by an authorized verifier",
    "Not detected by an authorized verifier",
    "Verification unavailable",
    "Verification inconclusive",
]

def get_c2patool_path() -> str:
    """Resolve c2patool binary across development and PyInstaller frozen runtime."""
    candidates = []
    if getattr(sys, "frozen", False):
        base_dir = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
        candidates.extend([
            os.path.join(base_dir, "tools", "c2patool", "c2patool.exe"),
            os.path.join(os.path.dirname(sys.executable), "_internal", "tools", "c2patool", "c2patool.exe"),
            os.path.join(os.path.dirname(sys.executable), "tools", "c2patool", "c2patool.exe"),
        ])
    candidates.append(
        os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
            "tools",
            "c2patool",
            "c2patool.exe",
        )
    )
    for c in candidates:
        if os.path.isfile(c):
            return c
    return candidates[-1]

C2PATOOL_PATH = get_c2patool_path()


def extract_verified_c2pa_info(file_bytes: bytes, filename: str) -> Optional[Dict[str, Any]]:
    """
    Extract verified C2PA manifest details (issuer, generator, validation state, assertions)
    using the official local c2patool binary if present. Runs locally on loopback with no network calls.
    """
    if not os.path.exists(C2PATOOL_PATH):
        return None

    _, ext = os.path.splitext(filename)
    if not ext:
        ext = ".jpg"

    tmp_file = None
    try:
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tf:
            tf.write(file_bytes)
            tmp_file = tf.name

        proc = subprocess.run(
            [C2PATOOL_PATH, tmp_file],
            capture_output=True,
            text=True,
            timeout=4.0,
        )

        if proc.returncode == 0 and proc.stdout.strip().startswith("{"):
            data = json.loads(proc.stdout)
            active_urn = data.get("active_manifest")
            manifests = data.get("manifests", {})
            active_m = manifests.get(active_urn, {}) if active_urn else {}

            sig_info = active_m.get("signature_info", {})
            assertions_raw = active_m.get("assertions", [])
            assertion_labels = [a.get("label") for a in assertions_raw if a.get("label")]

            generator_str = active_m.get("claim_generator")
            if not generator_str and active_m.get("claim_generator_info"):
                gen_items = active_m.get("claim_generator_info")
                generator_str = ", ".join(f"{g.get('name', '')} {g.get('version', '')}".strip() for g in gen_items)

            return {
                "active_manifest": active_urn,
                "validation_state": data.get("validation_state", "Unknown"),
                "claim_generator": generator_str,
                "title": active_m.get("title"),
                "issuer": sig_info.get("issuer"),
                "common_name": sig_info.get("common_name"),
                "signing_time": sig_info.get("time"),
                "signing_alg": sig_info.get("alg"),
                "assertions": assertion_labels,
                "assertions_count": len(assertion_labels),
            }
    except Exception:
        pass
    finally:
        if tmp_file and os.path.exists(tmp_file):
            try:
                os.remove(tmp_file)
            except OSError:
                pass

    return None


class ImageInspectionResult:
    def __init__(
        self,
        filename: str,
        file_size: int,
        format_name: str,
        is_supported: bool,
        dimensions: Optional[Tuple[int, int]],
        has_c2pa: bool,
        status: str,
        status_code: str,
        details: str,
        structural_chunks: List[str],
        retained_metadata: List[str],
        structure_count: int,
        c2pa_bytes: int,
        c2pa_details: Optional[Dict[str, Any]] = None,
        synthid_status: str = "Not checked",
        error: Optional[str] = None,
    ):
        self.filename = filename
        self.file_size = file_size
        self.format_name = format_name
        self.is_supported = is_supported
        self.dimensions = dimensions
        self.has_c2pa = has_c2pa
        self.status = status
        self.status_code = status_code  # "c2pa_detected", "no_c2pa", "unsupported", "invalid"
        self.details = details
        self.structural_chunks = structural_chunks
        self.retained_metadata = retained_metadata
        self.structure_count = structure_count
        self.c2pa_bytes = c2pa_bytes
        self.c2pa_details = c2pa_details or {}
        self.synthid_status = synthid_status
        self.error = error

    def to_dict(self) -> Dict[str, Any]:
        return {
            "filename": self.filename,
            "file_size": self.file_size,
            "format_name": self.format_name,
            "is_supported": self.is_supported,
            "dimensions": f"{self.dimensions[0]}x{self.dimensions[1]}" if self.dimensions else None,
            "has_c2pa": self.has_c2pa,
            "status": self.status,
            "status_code": self.status_code,
            "details": self.details,
            "structural_chunks": self.structural_chunks,
            "retained_metadata": self.retained_metadata,
            "structure_count": self.structure_count,
            "c2pa_bytes": self.c2pa_bytes,
            "c2pa_details": self.c2pa_details,
            "verified_c2pa": self.c2pa_details if self.c2pa_details else None,
            "synthid": {
                "status": self.synthid_status,
                "supported_states": SYNTHID_STATES,
                "technology": "SynthID (Content-Level Imperceptible Watermark)",
                "explanation": (
                    "SynthID is an imperceptible watermark embedded directly into visual pixel values, "
                    "distinct from C2PA metadata manifests. Local inspection cannot verify or remove SynthID. "
                    "Removing C2PA Content Credentials leaves the image pixel data and any invisible watermark untouched."
                ),
                "external_verifier_url": "https://openai.com/verify/",
                "external_verifier_note": (
                    "To verify SynthID or external provenance signals, you may optionally use authorized external services "
                    "such as openai.com/verify. Note: External verification requires manually uploading your image to third-party servers."
                ),
            },
            "error": self.error,
        }


class CleaningResult:
    def __init__(
        self,
        job_id: str,
        original_filename: str,
        output_filename: str,
        original_size: int,
        output_size: int,
        bytes_removed: int,
        format_name: str,
        structures_removed: int,
        retained_metadata: List[str],
        verification_passed: bool,
        verification_summary: str,
        verification_checks: List[Dict[str, Any]],
        download_url: str,
        synthid_status: str = "Not checked",
        error: Optional[str] = None,
    ):
        self.job_id = job_id
        self.original_filename = original_filename
        self.output_filename = output_filename
        self.original_size = original_size
        self.output_size = output_size
        self.bytes_removed = bytes_removed
        self.format_name = format_name
        self.structures_removed = structures_removed
        self.retained_metadata = retained_metadata
        self.verification_passed = verification_passed
        self.verification_summary = verification_summary
        self.verification_checks = verification_checks
        self.download_url = download_url
        self.synthid_status = synthid_status
        self.error = error

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "original_filename": self.original_filename,
            "output_filename": self.output_filename,
            "original_size": self.original_size,
            "output_size": self.output_size,
            "bytes_removed": self.bytes_removed,
            "format_name": self.format_name,
            "structures_removed": self.structures_removed,
            "retained_metadata": self.retained_metadata,
            "verification_passed": self.verification_passed,
            "verification_summary": self.verification_summary,
            "verification_checks": self.verification_checks,
            "download_url": self.download_url,
            "synthid": {
                "status": self.synthid_status,
                "note": (
                    "Pixel data preserved byte-for-byte. Removing C2PA container metadata does NOT remove "
                    "content-level watermarks such as SynthID. No claim is made regarding invisible watermark removal."
                ),
            },
            "error": self.error,
        }


class CleanerService:
    def __init__(self):
        # Cache for verified cleaned files: job_id -> (filename, mime_type, bytes)
        self._cleaned_cache: Dict[str, Tuple[str, str, bytes]] = {}

    def get_cached_file(self, job_id: str) -> Optional[Tuple[str, str, bytes]]:
        return self._cleaned_cache.get(job_id)

    def inspect_image(self, file_bytes: bytes, filename: str) -> ImageInspectionResult:
        """
        Inspect file bytes safely without re-encoding or sending to external services.
        """
        if len(file_bytes) > MAX_FILE_SIZE:
            return ImageInspectionResult(
                filename=filename,
                file_size=len(file_bytes),
                format_name="Unknown",
                is_supported=False,
                dimensions=None,
                has_c2pa=False,
                status="File exceeds maximum size limit (100MB)",
                status_code="invalid",
                details="File is too large to process safely in local memory.",
                structural_chunks=[],
                retained_metadata=[],
                structure_count=0,
                c2pa_bytes=0,
                error="File size limit exceeded.",
            )

        det = detect_format(file_bytes)
        if not det.is_supported:
            return ImageInspectionResult(
                filename=filename,
                file_size=len(file_bytes),
                format_name=det.format.value,
                is_supported=False,
                dimensions=None,
                has_c2pa=False,
                status=f"Unsupported format ({det.format.value})",
                status_code="unsupported",
                details=det.message,
                structural_chunks=[],
                retained_metadata=[],
                structure_count=0,
                c2pa_bytes=0,
                error=det.message,
            )

        dimensions = None
        try:
            with Image.open(io.BytesIO(file_bytes)) as img:
                dimensions = img.size
        except Exception:
            dimensions = None

        c2pa_info: Optional[Dict[str, Any]] = None

        if det.format == ImageFormat.JPEG:
            res = parse_and_strip_jpeg(file_bytes)
            if not res.is_valid:
                return ImageInspectionResult(
                    filename=filename,
                    file_size=len(file_bytes),
                    format_name="JPEG",
                    is_supported=True,
                    dimensions=dimensions,
                    has_c2pa=False,
                    status="Invalid or corrupt JPEG structure",
                    status_code="invalid",
                    details=res.error_message or "Could not parse JPEG markers safely.",
                    structural_chunks=["SOF0 / Image Stream", "SOS Entropy Scans", "DQT", "DHT"],
                    retained_metadata=[],
                    structure_count=0,
                    c2pa_bytes=0,
                    error=res.error_message,
                )

            if res.has_c2pa:
                c2pa_info = extract_verified_c2pa_info(file_bytes, filename)
                return ImageInspectionResult(
                    filename=filename,
                    file_size=len(file_bytes),
                    format_name="JPEG",
                    is_supported=True,
                    dimensions=dimensions,
                    has_c2pa=True,
                    status="C2PA credentials detected",
                    status_code="c2pa_detected",
                    details=f"Found {res.c2pa_segment_count} embedded C2PA APP11 segment(s) totaling {res.c2pa_total_bytes:,} bytes.",
                    structural_chunks=["SOF0", "SOS", "DQT", "DHT"],
                    retained_metadata=res.retained_metadata,
                    structure_count=res.c2pa_segment_count,
                    c2pa_bytes=res.c2pa_total_bytes,
                    c2pa_details=c2pa_info,
                )
            else:
                return ImageInspectionResult(
                    filename=filename,
                    file_size=len(file_bytes),
                    format_name="JPEG",
                    is_supported=True,
                    dimensions=dimensions,
                    has_c2pa=False,
                    status="No embedded C2PA credentials detected",
                    status_code="no_c2pa",
                    details="No C2PA JUMBF APP11 metadata found in this JPEG file.",
                    structural_chunks=["SOF0", "SOS", "DQT", "DHT"],
                    retained_metadata=res.retained_metadata,
                    structure_count=0,
                    c2pa_bytes=0,
                )

        elif det.format == ImageFormat.PNG:
            res = parse_and_strip_png(file_bytes)
            if not res.is_valid:
                return ImageInspectionResult(
                    filename=filename,
                    file_size=len(file_bytes),
                    format_name="PNG",
                    is_supported=True,
                    dimensions=dimensions,
                    has_c2pa=False,
                    status="Invalid or corrupt PNG structure",
                    status_code="invalid",
                    details=res.error_message or "Could not parse PNG chunks safely.",
                    structural_chunks=[],
                    retained_metadata=[],
                    structure_count=0,
                    c2pa_bytes=0,
                    error=res.error_message,
                )

            if res.has_c2pa:
                c2pa_info = extract_verified_c2pa_info(file_bytes, filename)
                return ImageInspectionResult(
                    filename=filename,
                    file_size=len(file_bytes),
                    format_name="PNG",
                    is_supported=True,
                    dimensions=dimensions,
                    has_c2pa=True,
                    status="C2PA credentials detected",
                    status_code="c2pa_detected",
                    details=f"Found {res.c2pa_chunk_count} embedded C2PA caBX chunk(s) totaling {res.c2pa_total_bytes:,} bytes.",
                    structural_chunks=res.structural_chunks,
                    retained_metadata=res.retained_metadata,
                    structure_count=res.c2pa_chunk_count,
                    c2pa_bytes=res.c2pa_total_bytes,
                    c2pa_details=c2pa_info,
                )
            else:
                return ImageInspectionResult(
                    filename=filename,
                    file_size=len(file_bytes),
                    format_name="PNG",
                    is_supported=True,
                    dimensions=dimensions,
                    has_c2pa=False,
                    status="No embedded C2PA credentials detected",
                    status_code="no_c2pa",
                    details="No C2PA caBX chunk found in this PNG file.",
                    structural_chunks=res.structural_chunks,
                    retained_metadata=res.retained_metadata,
                    structure_count=0,
                    c2pa_bytes=0,
                )

        elif det.format == ImageFormat.WEBP:
            res = parse_and_strip_webp(file_bytes)
            if not res.is_valid:
                return ImageInspectionResult(
                    filename=filename,
                    file_size=len(file_bytes),
                    format_name="WebP",
                    is_supported=True,
                    dimensions=dimensions,
                    has_c2pa=False,
                    status="Invalid or corrupt WebP structure",
                    status_code="invalid",
                    details=res.error_message or "Could not parse WebP chunks safely.",
                    structural_chunks=[],
                    retained_metadata=[],
                    structure_count=0,
                    c2pa_bytes=0,
                    error=res.error_message,
                )

            if res.has_c2pa:
                c2pa_info = extract_verified_c2pa_info(file_bytes, filename)
                return ImageInspectionResult(
                    filename=filename,
                    file_size=len(file_bytes),
                    format_name="WebP",
                    is_supported=True,
                    dimensions=dimensions,
                    has_c2pa=True,
                    status="C2PA credentials detected",
                    status_code="c2pa_detected",
                    details=f"Found {res.c2pa_chunk_count} embedded C2PA chunk(s) totaling {res.c2pa_total_bytes:,} bytes.",
                    structural_chunks=res.structural_chunks,
                    retained_metadata=res.retained_metadata,
                    structure_count=res.c2pa_chunk_count,
                    c2pa_bytes=res.c2pa_total_bytes,
                    c2pa_details=c2pa_info,
                )
            else:
                return ImageInspectionResult(
                    filename=filename,
                    file_size=len(file_bytes),
                    format_name="WebP",
                    is_supported=True,
                    dimensions=dimensions,
                    has_c2pa=False,
                    status="No embedded C2PA credentials detected",
                    status_code="no_c2pa",
                    details="No C2PA RIFF chunk found in this WebP file.",
                    structural_chunks=res.structural_chunks,
                    retained_metadata=res.retained_metadata,
                    structure_count=0,
                    c2pa_bytes=0,
                )

        return ImageInspectionResult(
            filename=filename,
            file_size=len(file_bytes),
            format_name=det.format.value,
            is_supported=False,
            dimensions=dimensions,
            has_c2pa=False,
            status="Unsupported format",
            status_code="unsupported",
            details=det.message,
            structural_chunks=[],
            retained_metadata=[],
            structure_count=0,
            c2pa_bytes=0,
            error=det.message,
        )

    def clean_image(self, file_bytes: bytes, filename: str) -> CleaningResult:
        """
        Perform format-aware structural removal of C2PA manifest data, verify the result,
        and cache it for immediate download.
        """
        det = detect_format(file_bytes)
        if not det.is_supported:
            raise ValueError(f"Cannot process unsupported format: {det.format.value}")

        job_id = str(uuid.uuid4())
        name, ext = os.path.splitext(filename)
        output_ext = det.extension or ext or ".img"
        output_filename = f"{name}_C2PA-removed{output_ext}"

        cleaned_bytes: Optional[bytes] = None
        retained_meta: List[str] = []
        structures_removed = 0

        if det.format == ImageFormat.JPEG:
            res = parse_and_strip_jpeg(file_bytes)
            if not res.is_valid:
                raise ValueError(res.error_message or "Failed to parse JPEG")
            cleaned_bytes = res.cleaned_bytes
            retained_meta = res.retained_metadata
            structures_removed = res.c2pa_segment_count

        elif det.format == ImageFormat.PNG:
            res = parse_and_strip_png(file_bytes)
            if not res.is_valid:
                raise ValueError(res.error_message or "Failed to parse PNG")
            cleaned_bytes = res.cleaned_bytes
            retained_meta = res.retained_metadata
            structures_removed = res.c2pa_chunk_count

        elif det.format == ImageFormat.WEBP:
            res = parse_and_strip_webp(file_bytes)
            if not res.is_valid:
                raise ValueError(res.error_message or "Failed to parse WebP")
            cleaned_bytes = res.cleaned_bytes
            retained_meta = res.retained_metadata
            structures_removed = res.c2pa_chunk_count

        if cleaned_bytes is None:
            raise ValueError("Removal produced no output bytes.")

        # Independent Verification
        ver = verify_cleaned_file(file_bytes, cleaned_bytes, det.format)
        if not ver.is_valid:
            failed_checks = [c.name for c in ver.checks if not c.passed]
            raise ValueError(f"Post-processing verification failed: {', '.join(failed_checks)}")

        # Cache clean output for download
        self._cleaned_cache[job_id] = (output_filename, det.mime_type, cleaned_bytes)

        checks_dicts = [{"name": c.name, "passed": c.passed, "details": c.details} for c in ver.checks]

        return CleaningResult(
            job_id=job_id,
            original_filename=filename,
            output_filename=output_filename,
            original_size=len(file_bytes),
            output_size=len(cleaned_bytes),
            bytes_removed=len(file_bytes) - len(cleaned_bytes),
            format_name=det.format.value,
            structures_removed=structures_removed,
            retained_metadata=retained_meta,
            verification_passed=ver.is_valid,
            verification_summary=ver.summary,
            verification_checks=checks_dicts,
            download_url=f"/api/download/{job_id}",
            synthid_status="Not checked",
        )

    def create_batch_zip(self, job_ids: List[str]) -> Tuple[str, bytes]:
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as z:
            for jid in job_ids:
                item = self._cleaned_cache.get(jid)
                if item:
                    fname, _, bdata = item
                    z.writestr(fname, bdata)
        zip_buf.seek(0)
        return "C2PA_Cleaner_Batch.zip", zip_buf.getvalue()


cleaner_service = CleanerService()
