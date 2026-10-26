# C2PA Cleaner & Provenance Inspector

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11%20%7C%203.12%20%7C%203.13%20%7C%203.14-blue.svg" alt="Python Version" />
  <img src="https://img.shields.io/badge/FastAPI-0.115+-009688.svg?logo=fastapi&logoColor=white" alt="FastAPI" />
  <img src="https://img.shields.io/badge/License-MIT-green.svg" alt="License: MIT" />
  <img src="https://img.shields.io/badge/Platform-Windows%2010%20%2F%2011-0078D6.svg?logo=windows&logoColor=white" alt="Windows" />
  <img src="https://img.shields.io/badge/Tests-42%20Passed%20%7C%20100%25-brightgreen.svg" alt="Tests" />
  <img src="https://img.shields.io/badge/Security-100%25%20Local%20Loopback-success.svg" alt="Local Loopback" />
  <img src="https://img.shields.io/badge/Bitstream-100%25%20Byte--Identical-blueviolet.svg" alt="Byte-Identical" />
</p>

> **A production-grade, local-first image provenance inspector and lossless metadata export utility for Windows 10/11.**  
> Inspect embedded C2PA Content Credentials and content-level watermarks. Losslessly strip C2PA manifest stores from JPEG, PNG, and WebP images without re-encoding, color quantization, pixel degradation, or network transmission.

---

## Table of Contents
- [1. Overview & Problem Statement](#1-overview--problem-statement)
- [2. Two Distinct Provenance Paradigms](#2-two-distinct-provenance-paradigms)
- [3. Binary Format Specifications & Removal Engine](#3-binary-format-specifications--removal-engine)
  - [JPEG (ISO/IEC 10918-1 & ISO/IEC 19566-5 JUMBF)](#a-jpeg-isoiec-10918-1--isoiec-19566-5-jumbf)
  - [PNG (Portable Network Graphics & caBX Chunk)](#b-png-portable-network-graphics--cabx-chunk)
  - [WebP (RIFF Container & C2PA FourCC)](#c-webp-riff-container--c2pa-fourcc)
- [4. Structural Bitstream vs. Ancillary Metadata](#4-structural-bitstream-vs-ancillary-metadata)
- [5. Truthful Content-Level Watermarking (SynthID)](#5-truthful-content-level-watermarking-synthid)
- [6. Five-Point Integrity Verification Suite](#6-five-point-integrity-verification-suite)
- [7. System Architecture](#7-system-architecture)
- [8. Installation & Quick Start](#8-installation--quick-start)
- [9. Windows Standalone Packaging](#9-windows-standalone-packaging)
- [10. Automated Test Suite](#10-automated-test-suite)
- [11. Privacy, Security & Truthful Boundaries](#11-privacy-security--truthful-boundaries)
- [12. License](#12-license)

---

## 1. Overview & Problem Statement

Digital media provenance standards such as **C2PA (Coalition for Content Provenance and Authenticity)** attach cryptographically signed manifest stores to media containers to record author identity, editing steps, and AI generator lineage.

However, existing off-the-shelf tools and naive scripts attempt to remove metadata by decompressing the image into raw RGB buffers and re-encoding it (e.g., `Image.open(f).save(out)`):
- **Generational Loss**: Irreversible high-frequency DCT quantization artifacts in JPEG, blurring, and banding.
- **Color Profile Shifting**: Unintentional flattening of wide-gamut ICC profiles (Display P3, Adobe RGB) to generic sRGB.
- **Metadata Destruction**: Collateral erasure of unrelated copyright EXIF, camera capture settings, and XMP rights.
- **False Claims**: Misleadingly marketing container metadata stripping as "bypassing AI detection" or "removing invisible watermarks".

**C2PA Cleaner** solves this with format-aware binary surgery: it isolates and removes only the verified C2PA manifest segments directly in the compressed container stream, preserving visual entropy scan payloads byte-for-byte.

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                                 C2PA CLEANER PIPELINE                                  │
│                                                                                        │
│   Input Image ───► Container Sniffer ───► Format-Aware Binary Stream Parser            │
│   (JPG/PNG/WebP)     (Magic Bytes)         ├── Separates Structural Bitstream          │
│                                            ├── Preserves EXIF, ICC, XMP Metadata       │
│                                            └── Targets C2PA Manifest Segments Only     │
│                                                              │                         │
│                                                              ▼                         │
│   Clean Image ◄── 5-Point Verification Suite ◄── Clean Binary Stream Rebuilder         │
│   (100% Exact)     ├── Signature & Marker Bounds (No recompression / No re-encoding)   │
│                    ├── C2PA Remnant Absence                                            │
│                    ├── Bitstream Byte Identity                                         │
│                    └── Pillow Engine Decodability                                      │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Two Distinct Provenance Paradigms

A cornerstone of C2PA Cleaner is maintaining absolute engineering truthfulness regarding media provenance:

```
┌───────────────────────────────────────────────────────────────────────────────────────┐
│                                  MEDIA ASSET CONTAINER                                │
│                                                                                       │
│  ┌─────────────────────────────────────────┐  ┌────────────────────────────────────┐  │
│  │     1. Container-Level Metadata         │  │     2. Content-Level Watermark     │  │
│  │      (C2PA Content Credentials)         │  │          (e.g., SynthID)           │  │
│  ├─────────────────────────────────────────┤  ├────────────────────────────────────┤  │
│  │ • Transported in container headers:     │  │ • Embedded directly into visual    │  │
│  │   - JPEG: APP11 (0xFFEB) JUMBF boxes    │  │   pixel values in frequency space  │  │
│  │   - PNG: caBX ancillary chunk           │  │ • Injected by neural generator     │  │
│  │   - WebP: C2PA RIFF chunk               │  │ • Survives recompression & crops   │  │
│  │ • Author signatures & claims manifests  │  │ • Invisible to human perception    │  │
│  │ • 100% losslessly removable locally     │  │ • CANNOT be detected or stripped   │  │
│  │   WITHOUT modifying visual pixels       │  │   without an authorized detector   │  │
│  └─────────────────────────────────────────┘  └────────────────────────────────────┘  │
│                                                                                       │
│  ┌─────────────────────────────────────────────────────────────────────────────────┐  │
│  │                             IMAGE VISUAL BITSTREAM                              │  │
│  │   JPEG: SOS Entropy Scan | PNG: IDAT Payloads | WebP: VP8/VP8L Compressed Bits  │  │
│  └─────────────────────────────────────────────────────────────────────────────────┘  │
└───────────────────────────────────────────────────────────────────────────────────────┘
```

| Dimension | C2PA Content Credentials | SynthID (Google DeepMind / DALL-E) |
| :--- | :--- | :--- |
| **Storage Layer** | Container metadata segments / boxes | Visual pixel values (latent/frequency bands) |
| **Extraction Feasibility** | 100% lossless binary container excision | Inseparable from pixels without degrading image |
| **Local Inspection** | Fully inspectable offline via parser & `c2patool` | Requires authorized external neural detector |
| **Pixel Impact** | **0% change** (Bitstream byte-identical) | **Untouched** by C2PA Cleaner |
| **Truthful Status** | Detected / Not Detected (Manifest size, Issuer) | Default: `Not checked` (Never fabricated) |

> [!IMPORTANT]
> **Stripping C2PA does NOT remove SynthID or make an image undetectable.**  
> Because C2PA Cleaner preserves compressed visual pixels byte-for-byte, any imperceptible pixel-level watermark remains untouched. The application never infers SynthID absence from C2PA removal, nor does it attempt lossy or destructive image transformations to evade watermarks.

---

## 3. Binary Format Specifications & Removal Engine

### A. JPEG (ISO/IEC 10918-1 & ISO/IEC 19566-5 JUMBF)
- **Marker Stream Parsing**: Scans markers from Start of Image (`0xFF, 0xD8`) through Start of Scan (SOS, `0xFF, 0xDA`) and End of Image (`0xFF, 0xD9`).
- **JUMBF Superbox Framing**: C2PA manifests are stored in `APP11` application markers (`0xFF, 0xEB`). Manifests exceeding 65,533 bytes are partitioned across multiple contiguous `APP11` packets using ISO/IEC 19566-5 multi-segment framing:
  - Common Identifier (CI): `0x4A, 0x50` (`b"JP"`)
  - Box Instance ($E_n$): 2 bytes big-endian
  - Packet Sequence Number ($Z$): 4 bytes big-endian (1-based index)
  - Box Payload: Packet 1 contains the JUMBF Description Box (`jumd`) containing the 16-byte C2PA UUID (`63 32 70 61 00 11 00 10 80 00 00 AA 00 38 9B 71` or `63 32 6D 61 ...`).
- **Selective Excision**: APP11 segments associated with the C2PA JUMBF instance are removed. Unrelated `APP11` markers (non-JUMBF or non-C2PA UUIDs), `APP1` (EXIF/XMP), `APP2` (ICC), `APP13` (IPTC), and `COM` comments are preserved.
- **Scan Data Protection**: The primary entropy-coded scan data following `0xFF, 0xDA` is preserved down to the exact bit.

### B. PNG (Portable Network Graphics & caBX Chunk)
- **Chunk Stream Parsing**: Validates the 8-byte PNG signature (`\x89PNG\r\n\x1a\n`) and iterates through 4-field chunks: `[Length (4B) | Type (4B) | Data (Length B) | CRC-32 (4B)]`.
- **Ancillary Target**: Identifies private ancillary chunk `caBX` (`0x63, 0x61, 0x42, 0x58`) housing the C2PA JUMBF Manifest Store.
- **Selective Excision**: Strips only the `caBX` chunk. Re-verifies CRC-32 values for all retained chunks and guarantees terminating `IEND`.

### C. WebP (RIFF Container & C2PA FourCC)
- **RIFF Stream Parsing**: Validates `RIFF` FourCC header and `WEBP` form type.
- **Chunk Target**: Identifies `C2PA` FourCC chunk placed in the container.
- **Selective Excision**: Removes the `C2PA` chunk (accounting for 2-byte chunk alignment padding) and recalculates the 32-bit little-endian RIFF size field at offset 4:
  $$\text{RIFF Size}_{\text{new}} = \text{RIFF Size}_{\text{old}} - (\text{Chunk Data Size} + 8 + \text{Padding})$$

---

## 4. Structural Bitstream vs. Ancillary Metadata

To maintain engineering clarity, C2PA Cleaner explicitly categorizes container elements:

```
┌───────────────────────────────────────┬───────────────────────────────────────┐
│       IMAGE BITSTREAM (ESSENTIAL)     │      RETAINED METADATA (NON-C2PA)     │
├───────────────────────────────────────┼───────────────────────────────────────┤
│ • PNG: IHDR, PLTE, IDAT, IEND, tRNS   │ • EXIF (APP1 / eXIf)                  │
│ • JPEG: SOF0/SOF2, DHT, DQT, SOS Scan │ • ICC Profiles (APP2 / iCCP)          │
│ • WebP: VP8 , VP8L, VP8X, ANIM, ANMF  │ • XMP Rights & Lineage (APP1 / iTXt)  │
│                                       │ • IPTC / Photoshop Records (APP13)    │
│  *Never labeled as "metadata"*        │ • Comments (COM / tEXt / zTXt)        │
└───────────────────────────────────────┴───────────────────────────────────────┘
```

---

## 5. Truthful Content-Level Watermarking (SynthID)

To counter misinformation and fabricated detection claims, C2PA Cleaner supports **five explicit states** for pixel watermarks:

1. **`Not checked`** *(Default)*: No authorized neural detector has evaluated the asset.
2. **`Detected by an authorized verifier`**: Confirmed by an authorized external verifier (e.g., OpenAI / Google DeepMind).
3. **`Not detected by an authorized verifier`**: Evaluated by an authorized verifier with negative results.
4. **`Verification inconclusive`**: Detector could not reach threshold confidence (e.g., heavy compression, small crops).
5. **`Verification unavailable`**: Verifier service was unreachable, rate-limited, or format unsupported.

### External Verification Disclosure
Users wishing to verify OpenAI DALL-E provenance signals can launch the official external verification tool:
- **Verifier Portal**: [https://openai.com/verify/](https://openai.com/verify/)
- **Mandatory Disclosure**: The application renders an explicit disclosure modal warning that external verification requires manually uploading images to third-party servers. C2PA Cleaner **never** automatically transmits user images.

---

## 6. Five-Point Integrity Verification Suite

Every file processed by C2PA Cleaner undergoes independent automated post-processing verification before download availability:

| Check | Target | Verification Method |
| :--- | :--- | :--- |
| **1. Container Signature** | File magic bytes | Verifies standard container signatures (`FF D8 FF`, `89 50 4E 47`, `RIFF...WEBP`). |
| **2. Container Structure** | Framing & bounds | Validates marker chains, chunk lengths, and terminating markers (`EOI`, `IEND`, RIFF size). |
| **3. C2PA Absence** | Zero remnants | Re-runs the binary detector to confirm 0 remaining C2PA segments or chunks. |
| **4. Bitstream Byte Identity** | Visual pixels | Compares original vs cleaned compressed scan entropy data / `IDAT` payloads byte-for-byte. |
| **5. Decodability** | Rendering engine | Full image decode through Pillow engine to verify canvas renderability without warnings. |

---

## 7. System Architecture

```
C2PA Stripper/
├── app/
│   ├── backend/
│   │   ├── parsers/
│   │   │   ├── detector.py        # Magic byte sniffing & format identification
│   │   │   ├── jpeg.py            # ISO/IEC 10918-1 & ISO/IEC 19566-5 APP11 parser
│   │   │   ├── png.py             # PNG chunk stream parser & caBX stripper
│   │   │   ├── webp.py            # WebP RIFF chunk parser & C2PA stripper
│   │   │   └── verifier.py        # 5-point post-processing verification engine
│   │   ├── services/
│   │   │   └── cleaner_service.py # Orchestration, manifest extraction, caching
│   │   └── server.py              # FastAPI server (127.0.0.1 loopback only)
│   └── frontend/
│       ├── index.html             # High-density dark dashboard UI (1366x768 friendly)
│       ├── styles.css             # Vanilla CSS design system (zero external CDNs)
│       └── app.js                 # Local drag-and-drop, preview, batch & verification logic
├── scripts/
│   ├── build_windows.bat          # Standalone PyInstaller onedir packager
│   ├── launch_portable.bat        # Zero-dependency portable launcher
│   └── run_local.bat              # Local development launcher
├── tests/
│   ├── fixtures/                  # Real C2PA signed & unsigned test images
│   ├── test_detection.py          # Format sniffing & malformed checks
│   ├── test_jpeg.py               # JPEG multi-segment APP11 & byte-preservation tests
│   ├── test_png.py                # PNG caBX extraction & chunk integrity tests
│   ├── test_webp.py               # WebP RIFF chunk handling & size adjustment tests
│   ├── test_verifier.py           # 5-point verification engine tests
│   ├── test_api.py                # FastAPI HTTP route & batch processing tests
│   ├── test_v2_provenance_and_synthid.py # V2 provenance & disclosure tests
│   └── test_e2e_smoke.py          # End-to-end inspection & clean workflow tests
├── tools/
│   └── c2patool/                  # Bundled official offline C2PA inspection binary
├── run.py                         # Application entrypoint (auto-opens browser)
├── requirements.txt               # Locked dependencies
└── LICENSE                        # MIT License
```

---

## 8. Installation & Quick Start

### Option A: Portable Windows Package (No Python Required)
1. Download or build the distribution in `dist\C2PA Cleaner\`.
2. Double-click `Launch C2PA Cleaner.bat` or `C2PA Cleaner.exe`.
3. Your default browser opens automatically to `http://127.0.0.1:8000`.

### Option B: Running from Source
Prerequisites: Python 3.11+ on Windows, Linux, or macOS.

```bash
# Clone the repository
git clone https://github.com/sixfiguredev0/c2pa-cleaner.git
cd c2pa-cleaner

# Create a virtual environment
python -m venv .venv
.venv\Scripts\activate   # On Linux/macOS: source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run the application
python run.py
```

---

## 9. Windows Standalone Packaging

Build a self-contained portable Windows distribution bundling Python runtime, frontend assets, and the offline `c2patool.exe` binary:

```bash
scripts\build_windows.bat
```

The compiled package is output to `dist\C2PA Cleaner\` ready for single-folder deployment without prerequisite installations.

---

## 10. Automated Test Suite

C2PA Cleaner features **42 comprehensive automated tests** covering binary edge cases, corrupted headers, multi-segment JUMBF streams, and independent verification against the official Rust C2PA CLI (`c2patool`):

```bash
py -m pytest tests -v
```

```
tests/test_detection.py::test_detect_jpeg PASSED
tests/test_detection.py::test_detect_png PASSED
tests/test_detection.py::test_detect_webp PASSED
tests/test_detection.py::test_detect_unsupported_formats PASSED
tests/test_detection.py::test_detect_corrupt_and_truncated PASSED
tests/test_jpeg.py::test_jpeg_without_c2pa PASSED
tests/test_jpeg.py::test_jpeg_with_c2pa_multisegment PASSED
tests/test_jpeg.py::test_jpeg_update_manifest PASSED
tests/test_jpeg.py::test_jpeg_preserves_unrelated_app11 PASSED
tests/test_jpeg.py::test_jpeg_scan_data_exact_preservation PASSED
tests/test_jpeg.py::test_jpeg_corrupt_structures PASSED
tests/test_jpeg.py::test_jpeg_validation_with_c2patool PASSED
tests/test_png.py::test_png_without_c2pa PASSED
tests/test_png.py::test_png_with_c2pa PASSED
tests/test_png.py::test_png_preserves_ancillary_chunks PASSED
tests/test_png.py::test_png_corruptions PASSED
tests/test_png.py::test_png_validation_with_c2patool PASSED
tests/test_webp.py::test_webp_without_c2pa PASSED
tests/test_webp.py::test_webp_with_c2pa PASSED
tests/test_webp.py::test_webp_corruptions PASSED
tests/test_webp.py::test_webp_validation_with_c2patool PASSED
tests/test_verifier.py::test_verify_clean_jpeg PASSED
tests/test_verifier.py::test_verify_clean_png PASSED
tests/test_verifier.py::test_verify_clean_webp PASSED
tests/test_verifier.py::test_verify_fails_if_c2pa_remains PASSED
tests/test_verifier.py::test_verify_fails_if_scans_altered PASSED
tests/test_verifier.py::test_verify_fails_on_corrupt_container PASSED
tests/test_api.py::test_api_health PASSED
tests/test_api.py::test_api_inspect_jpeg_with_c2pa PASSED
tests/test_api.py::test_api_inspect_jpeg_without_c2pa PASSED
tests/test_api.py::test_api_inspect_png PASSED
tests/test_api.py::test_api_inspect_unsupported PASSED
tests/test_api.py::test_api_clean_and_download_flow PASSED
tests/test_api.py::test_api_batch_inspect_and_clean PASSED
tests/test_v2_provenance_and_synthid.py::test_distinct_c2pa_and_synthid_statuses PASSED
tests/test_v2_provenance_and_synthid.py::test_no_fabricated_synthid_results PASSED
tests/test_v2_provenance_and_synthid.py::test_png_structural_chunks_not_labeled_metadata PASSED
tests/test_v2_provenance_and_synthid.py::test_c2pa_manifest_details_extraction PASSED
tests/test_v2_provenance_and_synthid.py::test_external_verify_endpoint_and_disclosure PASSED
tests/test_v2_provenance_and_synthid.py::test_external_verify_record_session_log PASSED
tests/test_e2e_smoke.py::test_e2e_frontend_assets_present PASSED
tests/test_e2e_smoke.py::test_e2e_full_inspect_clean_verify_workflow PASSED

======================== 42 passed, 1 warning in 1.31s ========================
```

---

## 11. Privacy, Security & Truthful Boundaries

- **100% Loopback Security**: The backend binds exclusively to `127.0.0.1`. No external interfaces or ports are opened.
- **Zero Remote Telemetry**: Contains zero tracking scripts, remote fonts, external analytics, or cloud API calls.
- **In-Memory Cache Lifecycle**: Processed artifacts are stored in a temporary in-memory LRU cache and never permanently written to unmanaged disk directories.
- **No Deceptive Marketing**: The tool does not claim to make images "invisible" to AI, nor does it claim to strip pixel watermarks.

---

## 12. License

Distributed under the **MIT License**. See [`LICENSE`](LICENSE) for full details.

```
Copyright (c) 2026 Yasen Katevski
```
