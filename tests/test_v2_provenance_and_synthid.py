"""
Tests for C2PA Cleaner V2: Provenance Inspector, C2PA vs SynthID distinction,
and truthful status reporting.
"""

import os
import pytest
from starlette.testclient import TestClient

from app.backend.server import app
from app.backend.services.cleaner_service import cleaner_service, SYNTHID_STATES
from app.backend.parsers.png import parse_and_strip_png, PNG_STRUCTURAL_CHUNKS


client = TestClient(app)
FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def test_distinct_c2pa_and_synthid_statuses():
    """
    Verify that C2PA Content Credentials and Content-Level Watermark (SynthID)
    are strictly separated, and C2PA removal does NOT claim to affect SynthID.
    """
    path = os.path.join(FIXTURES_DIR, "CA.jpg")
    with open(path, "rb") as f:
        data = f.read()

    # 1. Inspect image with C2PA
    insp = cleaner_service.inspect_image(data, "CA.jpg").to_dict()
    assert insp["has_c2pa"] is True
    assert insp["status_code"] == "c2pa_detected"
    # SynthID must be "Not checked" - never inferred from C2PA
    assert insp["synthid"]["status"] == "Not checked"
    assert "imperceptible watermark" in insp["synthid"]["explanation"]

    # 2. Clean image
    cleaned = cleaner_service.clean_image(data, "CA.jpg").to_dict()
    assert cleaned["verification_passed"] is True
    assert cleaned["bytes_removed"] > 100000
    # SynthID status must still remain "Not checked"
    assert cleaned["synthid"]["status"] == "Not checked"
    assert "does NOT remove content-level watermarks" in cleaned["synthid"]["note"]


def test_no_fabricated_synthid_results():
    """
    Test that neither inspect nor clean invents a SynthID result for any format.
    """
    for fname in ["CA.jpg", "no_manifest.jpg", "signed_test.png", "libpng-test.png", "signed_mars.webp", "mars.webp"]:
        path = os.path.join(FIXTURES_DIR, fname)
        with open(path, "rb") as f:
            bdata = f.read()

        insp = cleaner_service.inspect_image(bdata, fname).to_dict()
        assert insp["synthid"]["status"] == "Not checked"
        assert insp["synthid"]["status"] in SYNTHID_STATES


def test_png_structural_chunks_not_labeled_metadata():
    """
    Verify that PNG critical structural chunks (IHDR, IDAT, IEND)
    are strictly separated from ancillary metadata and NEVER labeled as metadata.
    """
    path = os.path.join(FIXTURES_DIR, "signed_test.png")
    with open(path, "rb") as f:
        data = f.read()

    res = parse_and_strip_png(data)
    assert res.is_valid is True

    # Critical chunks must be in structural_chunks
    assert "IHDR" in res.structural_chunks
    assert "IDAT" in res.structural_chunks
    assert "IEND" in res.structural_chunks

    # Critical chunks must NEVER appear in retained_metadata
    for meta_item in res.retained_metadata:
        for chunk in ["IHDR", "IDAT", "IEND"]:
            assert chunk not in meta_item

    # Verify service level to_dict() output
    insp = cleaner_service.inspect_image(data, "signed_test.png").to_dict()
    assert "IHDR" in insp["structural_chunks"]
    assert "IDAT" in insp["structural_chunks"]
    assert "IEND" in insp["structural_chunks"]
    assert "IHDR" not in insp["retained_metadata"]
    assert "IDAT" not in insp["retained_metadata"]
    assert "IEND" not in insp["retained_metadata"]


def test_c2pa_manifest_details_extraction():
    """
    Verify that for C2PA-bearing images, verified signature details (issuer, generator, validation state)
    are extracted locally where available.
    """
    path = os.path.join(FIXTURES_DIR, "CA.jpg")
    with open(path, "rb") as f:
        data = f.read()

    insp = cleaner_service.inspect_image(data, "CA.jpg").to_dict()
    assert insp["has_c2pa"] is True
    details = insp["c2pa_details"]
    assert details is not None
    assert details.get("validation_state") == "Valid"
    assert "C2PA" in details.get("issuer", "") or "make_test_images" in details.get("claim_generator", "")


def test_external_verify_endpoint_and_disclosure():
    """
    Verify the external verification info endpoint clearly discloses external transmission
    and provides the official OpenAI verification URL.
    """
    resp = client.get("/api/external-verify/info")
    assert resp.status_code == 200
    data = resp.json()
    assert data["official_url"] == "https://openai.com/verify/"
    assert data["local_processing"] is False
    assert "external servers" in data["disclosure"]
    assert "does not automatically transmit" in data["disclosure"]
    assert len(data["supported_states"]) == 5


def test_external_verify_record_session_log():
    """
    Test recording authorized external verification outcome.
    """
    payload = {
        "filename": "my_test_image.jpg",
        "state": "Detected by an authorized verifier",
        "notes": "Verified via OpenAI Verify portal.",
    }
    resp = client.post("/api/external-verify/record", json=payload)
    assert resp.status_code == 200
    res_data = resp.json()
    assert res_data["success"] is True
    assert res_data["state"] == "Detected by an authorized verifier"
