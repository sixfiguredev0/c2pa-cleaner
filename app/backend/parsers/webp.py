"""
Robust, lossless WebP (RIFF) chunk stream parser and C2PA Content Credentials remover.
Complies with WebP RIFF container specifications and C2PA RIFF chunk embedding rules.
Preserves image bitstream (VP8/VP8L/VP8X) and unrelated metadata chunks byte-for-byte.
"""

from typing import List, NamedTuple, Optional, Tuple


WEBP_FOURCC_RIFF = b"RIFF"
WEBP_FOURCC_WEBP = b"WEBP"
C2PA_FOURCC = b"C2PA"

WEBP_STRUCTURAL_CHUNKS = {b"VP8 ", b"VP8L", b"VP8X", b"ANIM", b"ANMF", b"ALPH"}

WEBP_METADATA_LABELS = {
    b"ICCP": "ICC Color Profile (ICCP)",
    b"EXIF": "EXIF Metadata (EXIF)",
    b"XMP ": "XMP Metadata (XMP)",
}


class WebpChunk(NamedTuple):
    offset: int
    payload_size: int
    total_size: int  # 8-byte header + payload + pad byte if odd
    fourcc: bytes
    is_c2pa: bool
    is_structural: bool
    description: str


class WebpParseResult(NamedTuple):
    is_valid: bool
    error_message: Optional[str]
    has_c2pa: bool
    c2pa_chunk_count: int
    c2pa_total_bytes: int
    retained_chunks: List[str]
    structural_chunks: List[str]
    retained_metadata: List[str]
    cleaned_bytes: Optional[bytes]
    chunks: List[WebpChunk]


def parse_and_strip_webp(data: bytes) -> WebpParseResult:
    """
    Parse the WebP RIFF chunk stream, detect and remove C2PA chunks losslessly,
    adjust the 32-bit little-endian RIFF header length, and preserve all other chunks.
    """
    if len(data) < 12:
        return WebpParseResult(
            is_valid=False,
            error_message="File too small to contain a valid WebP RIFF header.",
            has_c2pa=False,
            c2pa_chunk_count=0,
            c2pa_total_bytes=0,
            retained_chunks=[],
            structural_chunks=[],
            retained_metadata=[],
            cleaned_bytes=None,
            chunks=[],
        )

    if data[:4] != WEBP_FOURCC_RIFF or data[8:12] != WEBP_FOURCC_WEBP:
        return WebpParseResult(
            is_valid=False,
            error_message="Invalid WebP header (missing RIFF or WEBP fourcc).",
            has_c2pa=False,
            c2pa_chunk_count=0,
            c2pa_total_bytes=0,
            retained_chunks=[],
            structural_chunks=[],
            retained_metadata=[],
            cleaned_bytes=None,
            chunks=[],
        )

    riff_size = int.from_bytes(data[4:8], "little")
    pos = 12
    chunks: List[WebpChunk] = []
    retained_parts: List[bytes] = []
    c2pa_count = 0
    c2pa_bytes = 0
    retained_names: List[str] = []
    structural_names: List[str] = []
    metadata_names: List[str] = []

    while pos < len(data):
        if pos + 8 > len(data):
            return WebpParseResult(
                is_valid=False,
                error_message=f"Truncated WebP chunk header at offset {pos}.",
                has_c2pa=False,
                c2pa_chunk_count=0,
                c2pa_total_bytes=0,
                retained_chunks=[],
                structural_chunks=[],
                retained_metadata=[],
                cleaned_bytes=None,
                chunks=[],
            )

        fourcc = data[pos : pos + 4]
        chunk_len = int.from_bytes(data[pos + 4 : pos + 8], "little")
        pad = chunk_len % 2
        total_chunk_len = 8 + chunk_len + pad

        if pos + total_chunk_len > len(data):
            # Some encoders omit the trailing pad byte at the very end of file
            if pos + 8 + chunk_len == len(data):
                total_chunk_len = 8 + chunk_len
                pad = 0
            else:
                return WebpParseResult(
                    is_valid=False,
                    error_message=f"Invalid or truncated WebP chunk {fourcc!r} at offset {pos}.",
                    has_c2pa=False,
                    c2pa_chunk_count=0,
                    c2pa_total_bytes=0,
                    retained_chunks=[],
                    structural_chunks=[],
                    retained_metadata=[],
                    cleaned_bytes=None,
                    chunks=[],
                )

        is_c2pa = (fourcc == C2PA_FOURCC)
        is_structural = fourcc in WEBP_STRUCTURAL_CHUNKS
        name_str = fourcc.decode("latin1", errors="replace")

        chunk_info = WebpChunk(
            offset=pos,
            payload_size=chunk_len,
            total_size=total_chunk_len,
            fourcc=fourcc,
            is_c2pa=is_c2pa,
            is_structural=is_structural,
            description=f"WebP Chunk {name_str}",
        )
        chunks.append(chunk_info)

        if is_c2pa:
            c2pa_count += 1
            c2pa_bytes += total_chunk_len
        else:
            retained_parts.append(data[pos : pos + total_chunk_len])
            if name_str not in retained_names:
                retained_names.append(name_str)
            if is_structural:
                if name_str not in structural_names:
                    structural_names.append(name_str)
            else:
                label = WEBP_METADATA_LABELS.get(fourcc, f"Ancillary Metadata ({name_str})")
                if label not in metadata_names:
                    metadata_names.append(label)

        pos += total_chunk_len

    if c2pa_count > 0:
        new_payload = b"".join(retained_parts)
        # Recalculate RIFF size: 4 bytes for b"WEBP" + size of remaining chunks
        new_riff_size = 4 + len(new_payload)
        cleaned_bytes = WEBP_FOURCC_RIFF + new_riff_size.to_bytes(4, "little") + WEBP_FOURCC_WEBP + new_payload
    else:
        cleaned_bytes = data

    return WebpParseResult(
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
