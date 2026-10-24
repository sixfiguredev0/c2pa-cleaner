"""
Robust, lossless PNG chunk stream parser and C2PA Content Credentials remover.
Complies with the PNG Specification (ISO/IEC 15948) and C2PA caBX chunk specification.
Preserves image pixel data (IDAT) and unrelated metadata chunks byte-for-byte.
"""

import zlib
from typing import List, NamedTuple, Optional, Tuple


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
C2PA_CHUNK_TYPE = b"caBX"

# PNG Critical / Structural chunks (required for image rendering and bitstream)
# These MUST NOT be described as ordinary metadata.
PNG_STRUCTURAL_CHUNKS = {b"IHDR", b"PLTE", b"IDAT", b"IEND", b"tRNS"}

# Human-readable labels for ancillary metadata chunks
PNG_METADATA_LABELS = {
    b"eXIf": "EXIF (eXIf)",
    b"iCCP": "ICC Color Profile (iCCP)",
    b"sRGB": "Standard RGB (sRGB)",
    b"gAMA": "Gamma (gAMA)",
    b"cHRM": "Chromaticities (cHRM)",
    b"pHYs": "Pixel Aspect Ratio / DPI (pHYs)",
    b"tEXt": "Text Metadata (tEXt)",
    b"zTXt": "Compressed Text (zTXt)",
    b"iTXt": "International Text (iTXt)",
    b"tIME": "Timestamp (tIME)",
    b"bKGD": "Background Color (bKGD)",
    b"sBIT": "Significant Bits (sBIT)",
}


class PngChunk(NamedTuple):
    offset: int
    length: int  # Data payload length
    total_size: int  # Total chunk bytes on disk (length + 12)
    chunk_type: bytes
    is_c2pa: bool
    is_crc_valid: bool
    is_structural: bool
    description: str


class PngParseResult(NamedTuple):
    is_valid: bool
    error_message: Optional[str]
    has_c2pa: bool
    c2pa_chunk_count: int
    c2pa_total_bytes: int
    retained_chunks: List[str]  # Raw chunk FourCCs retained
    structural_chunks: List[str]  # Essential rendering chunks (IHDR, IDAT, IEND)
    retained_metadata: List[str]  # Non-structural metadata chunks (eXIf, iCCP, etc.)
    cleaned_bytes: Optional[bytes]
    chunks: List[PngChunk]


def parse_and_strip_png(data: bytes) -> PngParseResult:
    """
    Parse the PNG chunk stream, validate chunk boundaries and CRCs,
    detect and remove caBX C2PA chunks losslessly, and preserve all other chunks.
    """
    if len(data) < 8:
        return PngParseResult(
            is_valid=False,
            error_message="File too small to contain a valid PNG signature.",
            has_c2pa=False,
            c2pa_chunk_count=0,
            c2pa_total_bytes=0,
            retained_chunks=[],
            structural_chunks=[],
            retained_metadata=[],
            cleaned_bytes=None,
            chunks=[],
        )

    if not data.startswith(PNG_SIGNATURE):
        return PngParseResult(
            is_valid=False,
            error_message="Invalid PNG signature header.",
            has_c2pa=False,
            c2pa_chunk_count=0,
            c2pa_total_bytes=0,
            retained_chunks=[],
            structural_chunks=[],
            retained_metadata=[],
            cleaned_bytes=None,
            chunks=[],
        )

    pos = 8
    chunks: List[PngChunk] = []
    cleaned_parts: List[bytes] = [PNG_SIGNATURE]
    c2pa_count = 0
    c2pa_bytes = 0
    retained_names: List[str] = []
    structural_names: List[str] = []
    metadata_names: List[str] = []
    has_ihdr = False
    has_iend = False

    while pos < len(data):
        if pos + 8 > len(data):
            return PngParseResult(
                is_valid=False,
                error_message=f"Truncated PNG chunk header at offset {pos}.",
                has_c2pa=False,
                c2pa_chunk_count=0,
                c2pa_total_bytes=0,
                retained_chunks=[],
                structural_chunks=[],
                retained_metadata=[],
                cleaned_bytes=None,
                chunks=[],
            )

        payload_len = int.from_bytes(data[pos : pos + 4], "big")
        chunk_type = data[pos + 4 : pos + 8]
        total_chunk_len = 4 + 4 + payload_len + 4  # length(4) + type(4) + data(N) + crc(4)

        # Enforce PNG maximum chunk size (2^31 - 1)
        if payload_len > 0x7FFFFFFF or pos + total_chunk_len > len(data):
            return PngParseResult(
                is_valid=False,
                error_message=f"Invalid or truncated PNG chunk length ({payload_len}) for type {chunk_type!r} at offset {pos}.",
                has_c2pa=False,
                c2pa_chunk_count=0,
                c2pa_total_bytes=0,
                retained_chunks=[],
                structural_chunks=[],
                retained_metadata=[],
                cleaned_bytes=None,
                chunks=[],
            )

        # First chunk must be IHDR
        if not has_ihdr:
            if chunk_type != b"IHDR":
                return PngParseResult(
                    is_valid=False,
                    error_message=f"First PNG chunk must be IHDR, found {chunk_type!r}.",
                    has_c2pa=False,
                    c2pa_chunk_count=0,
                    c2pa_total_bytes=0,
                    retained_chunks=[],
                    structural_chunks=[],
                    retained_metadata=[],
                    cleaned_bytes=None,
                    chunks=[],
                )
            has_ihdr = True

        # Check CRC-32
        chunk_data = data[pos + 8 : pos + 8 + payload_len]
        expected_crc = int.from_bytes(data[pos + 8 + payload_len : pos + total_chunk_len], "big")
        actual_crc = zlib.crc32(chunk_type + chunk_data) & 0xFFFFFFFF
        is_crc_ok = (expected_crc == actual_crc)

        if not is_crc_ok:
            return PngParseResult(
                is_valid=False,
                error_message=f"CRC mismatch in PNG chunk {chunk_type!r} at offset {pos} (expected {expected_crc:08X}, got {actual_crc:08X}).",
                has_c2pa=False,
                c2pa_chunk_count=0,
                c2pa_total_bytes=0,
                retained_chunks=[],
                structural_chunks=[],
                retained_metadata=[],
                cleaned_bytes=None,
                chunks=[],
            )

        # Check if C2PA chunk (caBX)
        is_c2pa = (chunk_type == C2PA_CHUNK_TYPE)
        is_structural = chunk_type in PNG_STRUCTURAL_CHUNKS

        type_str = chunk_type.decode("latin1", errors="replace")
        desc = f"PNG Chunk {type_str}"

        chunk_info = PngChunk(
            offset=pos,
            length=payload_len,
            total_size=total_chunk_len,
            chunk_type=chunk_type,
            is_c2pa=is_c2pa,
            is_crc_valid=is_crc_ok,
            is_structural=is_structural,
            description=desc,
        )
        chunks.append(chunk_info)

        if is_c2pa:
            c2pa_count += 1
            c2pa_bytes += total_chunk_len
        else:
            cleaned_parts.append(data[pos : pos + total_chunk_len])
            if type_str not in retained_names:
                retained_names.append(type_str)
            if is_structural:
                if type_str not in structural_names:
                    structural_names.append(type_str)
            else:
                label = PNG_METADATA_LABELS.get(chunk_type, f"Ancillary Metadata ({type_str})")
                if label not in metadata_names:
                    metadata_names.append(label)

        if chunk_type == b"IEND":
            has_iend = True
            pos += total_chunk_len
            break

        pos += total_chunk_len

    if not has_iend:
        return PngParseResult(
            is_valid=False,
            error_message="PNG file missing terminating IEND chunk.",
            has_c2pa=False,
            c2pa_chunk_count=0,
            c2pa_total_bytes=0,
            retained_chunks=[],
            structural_chunks=[],
            retained_metadata=[],
            cleaned_bytes=None,
            chunks=[],
        )

    # Any trailing bytes after IEND (if any)
    if pos < len(data):
        cleaned_parts.append(data[pos:])

    cleaned_bytes = b"".join(cleaned_parts) if c2pa_count > 0 else data

    return PngParseResult(
        is_valid=True,
        error_message=None,
        has_c2pa=c2pa_count > 0,
        c2pa_chunk_count=c2pa_count,
        c2pa_total_bytes=c2pa_bytes,
        retained_chunks=retained_names,
        structural_chunks=structural_names,
        retained_metadata=metadata_names,
        cleaned_bytes=cleaned_bytes,
        chunks=chunks,
    )
