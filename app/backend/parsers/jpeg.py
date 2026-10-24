"""
Robust, lossless JPEG marker stream parser and C2PA Content Credentials remover.
Complies with ISO/IEC 10918-1 (JPEG) and ISO/IEC 19566-5 (JUMBF in APP11).
Preserves image scan data and unrelated metadata byte-for-byte.
"""

from typing import Dict, List, NamedTuple, Optional, Set, Tuple


C2PA_UUID_SUFFIX = b"\x00\x11\x00\x10\x80\x00\x00\xaa\x00\x38\x9b\x71"
C2PA_STORE_UUID = b"c2pa" + C2PA_UUID_SUFFIX
C2PA_MANIFEST_UUID = b"c2ma" + C2PA_UUID_SUFFIX
C2PA_UPDATE_UUID = b"c2um" + C2PA_UUID_SUFFIX

KNOWN_C2PA_UUIDS = (
    C2PA_STORE_UUID,
    C2PA_MANIFEST_UUID,
    C2PA_UPDATE_UUID,
)


class JpegSegment(NamedTuple):
    marker: int  # e.g. 0xEB for APP11, 0xE1 for APP1
    offset: int
    length: int  # Total segment length including 2-byte marker and Lp length field
    is_c2pa: bool
    c2pa_instance: Optional[bytes]
    c2pa_seq: Optional[int]
    description: str


class JpegParseResult(NamedTuple):
    is_valid: bool
    error_message: Optional[str]
    has_c2pa: bool
    c2pa_segment_count: int
    c2pa_total_bytes: int
    retained_metadata: List[str]
    cleaned_bytes: Optional[bytes]
    segments: List[JpegSegment]


def inspect_app11(payload: bytes) -> Tuple[bool, Optional[bytes], Optional[int], str]:
    """
    Inspect an APP11 payload to determine if it is a C2PA JUMBF segment.
    Payload starts immediately after the 2-byte Lp length field.
    """
    if len(payload) < 8:
        return False, None, None, "APP11 (non-JUMBF: too short)"

    # Must start with Common Identifier 'JP' (0x4A, 0x50)
    if payload[:2] != b"JP":
        return False, None, None, "APP11 (unrelated application data)"

    instance_id = payload[2:4]
    seq_num = int.from_bytes(payload[4:8], "big")

    if seq_num == 1:
        # First segment must contain JUMBF Superbox header and Description Box
        if len(payload) >= 44:
            # Check for 'jumb' box
            tbox = payload[12:16]
            tbox_desc = payload[20:24]
            desc_uuid = payload[24:40]

            if tbox == b"jumb" and tbox_desc == b"jumd":
                if desc_uuid in KNOWN_C2PA_UUIDS or desc_uuid.startswith((b"c2pa", b"c2ma", b"c2um")):
                    return True, instance_id, seq_num, f"C2PA JUMBF Manifest (Instance {instance_id.hex()}, Z=1)"

        # Fallback inspection: check if JUMBF UUID appears in the packet header
        if b"jumb" in payload[:32] and any(uuid in payload[:64] for uuid in KNOWN_C2PA_UUIDS):
            return True, instance_id, seq_num, f"C2PA JUMBF Manifest (Instance {instance_id.hex()}, Z=1)"

        return False, instance_id, seq_num, f"JUMBF (non-C2PA metadata, Instance {instance_id.hex()}, Z=1)"

    # Continuation segment (Z > 1)
    return False, instance_id, seq_num, f"JUMBF Continuation (Instance {instance_id.hex()}, Z={seq_num})"


def parse_and_strip_jpeg(data: bytes) -> JpegParseResult:
    """
    Parse the JPEG marker stream, identify C2PA APP11 segments, and remove them losslessly.
    Preserves all unrelated segments (EXIF, ICC, XMP, Comments, DQT, DHT, SOS entropy data).
    """
    if len(data) < 4:
        return JpegParseResult(
            is_valid=False,
            error_message="File too small to be a valid JPEG.",
            has_c2pa=False,
            c2pa_segment_count=0,
            c2pa_total_bytes=0,
            retained_metadata=[],
            cleaned_bytes=None,
            segments=[],
        )

    # Validate SOI (0xFF, 0xD8)
    if data[0:2] != b"\xff\xd8":
        return JpegParseResult(
            is_valid=False,
            error_message="Missing JPEG SOI (Start of Image) marker.",
            has_c2pa=False,
            c2pa_segment_count=0,
            c2pa_total_bytes=0,
            retained_metadata=[],
            cleaned_bytes=None,
            segments=[],
        )

    pos = 2
    segments: List[JpegSegment] = []
    c2pa_instances: Set[bytes] = set()
    retained_meta: List[str] = []

    # First pass: parse all marker segments and detect C2PA instance numbers
    # We collect segment slices and identify C2PA segments
    raw_segments: List[Tuple[int, int, int, bool, Optional[bytes], Optional[int], str]] = []

    while pos < len(data) - 1:
        if data[pos] != 0xFF:
            # Skip stray non-FF padding between markers if safe, or fail
            while pos < len(data) and data[pos] != 0xFF:
                pos += 1
            if pos >= len(data) - 1:
                break

        # Skip fill bytes (0xFF 0xFF ...)
        while pos < len(data) - 1 and data[pos] == 0xFF and data[pos + 1] == 0xFF:
            pos += 1

        if pos >= len(data) - 1:
            break

        marker = data[pos + 1]

        # Standalone markers with no length field
        if marker in (0xD8, 0xD9, 0x01) or (0xD0 <= marker <= 0xD7):
            desc = f"Marker FF{marker:02X}"
            raw_segments.append((marker, pos, 2, False, None, None, desc))
            pos += 2
            continue

        # Markers with 16-bit length field
        if pos + 4 > len(data):
            return JpegParseResult(
                is_valid=False,
                error_message=f"Truncated segment header at offset {pos}.",
                has_c2pa=False,
                c2pa_segment_count=0,
                c2pa_total_bytes=0,
                retained_metadata=[],
                cleaned_bytes=None,
                segments=[],
            )

        seg_len = int.from_bytes(data[pos + 2 : pos + 4], "big")
        total_seg_len = 2 + seg_len

        if seg_len < 2 or pos + total_seg_len > len(data):
            return JpegParseResult(
                is_valid=False,
                error_message=f"Invalid segment length ({seg_len}) at offset {pos}.",
                has_c2pa=False,
                c2pa_segment_count=0,
                c2pa_total_bytes=0,
                retained_metadata=[],
                cleaned_bytes=None,
                segments=[],
            )

        payload = data[pos + 4 : pos + total_seg_len]

        # Inspect APP11 for C2PA
        if marker == 0xEB:
            is_c2pa, inst, seq, desc = inspect_app11(payload)
            if is_c2pa and inst is not None:
                c2pa_instances.add(inst)
            raw_segments.append((marker, pos, total_seg_len, is_c2pa, inst, seq, desc))
        else:
            # Categorize metadata for reporting
            desc = f"Marker FF{marker:02X}"
            if marker == 0xE0:
                retained_meta.append("JFIF / APP0")
            elif marker == 0xE1:
                if payload.startswith(b"Exif\x00\x00"):
                    retained_meta.append("EXIF (APP1)")
                elif b"http://ns.adobe.com/xap/1.0/" in payload[:40]:
                    retained_meta.append("XMP (APP1)")
                else:
                    retained_meta.append("APP1 Metadata")
            elif marker == 0xE2:
                if payload.startswith(b"ICC_PROFILE\x00"):
                    retained_meta.append("ICC Profile (APP2)")
                else:
                    retained_meta.append("APP2 Metadata")
            elif marker == 0xED:
                retained_meta.append("Photoshop / IPTC (APP13)")
            elif marker == 0xEE:
                retained_meta.append("Adobe (APP14)")
            elif marker == 0xFE:
                retained_meta.append("Comment (COM)")

            raw_segments.append((marker, pos, total_seg_len, False, None, None, desc))

        pos += total_seg_len

        # If SOS (Start of Scan 0xFF, 0xDA), scan data follows
        if marker == 0xDA:
            # We reached SOS. The rest of the scan data follows.
            # Handle entropy coded data until next marker or EOI
            scan_start = pos
            while pos < len(data) - 1:
                if data[pos] == 0xFF:
                    next_b = data[pos + 1]
                    if next_b == 0x00 or (0xD0 <= next_b <= 0xD7):
                        # Escaped 0xFF or restart marker, continue scan
                        pos += 2
                        continue
                    else:
                        # Found marker terminating or continuing scans
                        break
                else:
                    pos += 1
            # pos is now at the next marker after scan data
            # Record the scan data block
            scan_len = pos - scan_start
            raw_segments.append((0xDA, scan_start, scan_len, False, None, None, "Entropy Coded Scan Data"))

    # Second pass: Associate any continuation segments (Z > 1) with confirmed C2PA instances
    final_segments: List[JpegSegment] = []
    cleaned_chunks: List[bytes] = [data[:2]]  # Start with SOI (FF D8)
    c2pa_count = 0
    c2pa_bytes = 0

    for marker, offset, length, is_c2pa, inst, seq, desc in raw_segments:
        # Check if continuation packet belongs to a confirmed C2PA instance
        if marker == 0xEB and not is_c2pa and inst in c2pa_instances:
            is_c2pa = True
            desc = f"C2PA JUMBF Continuation (Instance {inst.hex()}, Z={seq})"

        seg = JpegSegment(
            marker=marker,
            offset=offset,
            length=length,
            is_c2pa=is_c2pa,
            c2pa_instance=inst,
            c2pa_seq=seq,
            description=desc,
        )
        final_segments.append(seg)

        if is_c2pa:
            c2pa_count += 1
            c2pa_bytes += length
        else:
            cleaned_chunks.append(data[offset : offset + length])

    # If any trailing bytes exist after the last parsed marker (e.g. padding after EOI)
    if pos < len(data):
        cleaned_chunks.append(data[pos:])

    cleaned_bytes = b"".join(cleaned_chunks) if c2pa_count > 0 else data

    # Deduplicate retained metadata strings for reporting
    unique_meta = list(dict.fromkeys(retained_meta))

    return JpegParseResult(
        is_valid=True,
        error_message=None,
        has_c2pa=c2pa_count > 0,
        c2pa_segment_count=c2pa_count,
        c2pa_total_bytes=c2pa_bytes,
        retained_metadata=unique_meta,
        cleaned_bytes=cleaned_bytes,
        segments=final_segments,
    )
