"""
End-to-End smoke test verifying the complete V2 workflow:
- Health check with v2.0.0
- Image inspection with separate structural chunks vs metadata
- Verified C2PA manifest extraction via official c2patool
- Truthful SynthID status ('Not checked' by default)
- Safe lossless C2PA removal with 5-point verification
- Independent verification of cleaned bytes with c2patool
- External verification disclosure endpoint & outcome recording
- Frontend static asset integrity
"""

import os
import subprocess
import pytest
from PIL import Image
from starlette.testclient import TestClient

from app.backend.server import app, FRONTEND_DIR
from app.backend.services.cleaner_service import SYNTHID_STATES, C2PATOOL_PATH

client = TestClient(app)
FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def test_e2e_frontend_assets_present():
    """Verify that all V2 UI components and disclosure elements are present in frontend assets."""
    assert os.path.exists(FRONTEND_DIR)
    
    index_path = os.path.join(FRONTEND_DIR, "index.html")
    assert os.path.exists(index_path)
    with open(index_path, "r", encoding="utf-8") as f:
        html = f.read()
    assert "Content-Level Watermark" in html
    assert "Pixel-Level Watermark (e.g. SynthID)" in html
    assert "modal-verify" in html
    assert "openai.com/verify" in html
    assert "Not checked" in html
    assert "Integrity Verification Suite" in html
    assert "Image Bitstream:" in html
    assert "Retained Metadata:" in html

    css_path = os.path.join(FRONTEND_DIR, "styles.css")
    assert os.path.exists(css_path)
    with open(css_path, "r", encoding="utf-8") as f:
        css = f.read()
    assert ".watermark-card" in css
    assert ".badge-synthid" in css
    assert ".badge-synthid.not-checked" in css
    assert ".modal-backdrop" in css

    js_path = os.path.join(FRONTEND_DIR, "app.js")
    assert os.path.exists(js_path)
    with open(js_path, "r", encoding="utf-8") as f:
        js = f.read()
    assert "updateSynthIdBadge" in js
    assert "btnOpenVerifyModal" in js
    assert "btnSaveVerifyOutcome" in js


def test_e2e_full_inspect_clean_verify_workflow():
    """Verify full inspection, C2PA extraction, cleaning, and independent c2patool verification."""
    # 1. Health check
    health_resp = client.get("/api/health")
    assert health_resp.status_code == 200
    health_data = health_resp.json()
    assert health_data["status"] == "healthy"
    assert health_data["version"] == "2.0.0"
    assert health_data["local_only"] is True

    # 2. Inspect JPEG with C2PA (CA.jpg)
    img_path = os.path.join(FIXTURES_DIR, "CA.jpg")
    with open(img_path, "rb") as f:
        orig_bytes = f.read()
        resp = client.post("/api/inspect", files={"file": ("CA.jpg", orig_bytes, "image/jpeg")})
    assert resp.status_code == 200
    inspect_data = resp.json()
    assert inspect_data["has_c2pa"] is True
    assert inspect_data["structure_count"] >= 1
    assert inspect_data["c2pa_bytes"] > 0
    assert "SOF" in " ".join(inspect_data["structural_chunks"])
    assert inspect_data["synthid"]["status"] == "Not checked"

    # Verified manifest details should be present
    assert inspect_data["verified_c2pa"] is not None
    assert inspect_data["verified_c2pa"]["validation_state"] == "Valid"

    # 3. Clean JPEG
    resp = client.post("/api/clean", files={"file": ("CA.jpg", orig_bytes, "image/jpeg")})
    assert resp.status_code == 200
    clean_data = resp.json()
    assert clean_data["verification_passed"] is True
    assert clean_data["bytes_removed"] > 0
    assert len(clean_data["verification_checks"]) == 5
    assert all(c["passed"] for c in clean_data["verification_checks"])

    # 4. Download clean file
    download_url = clean_data["download_url"]
    dl_resp = client.get(download_url)
    assert dl_resp.status_code == 200
    clean_bytes = dl_resp.content

    # 5. Independent verification of clean file with Pillow
    import io
    img = Image.open(io.BytesIO(clean_bytes))
    img.verify()
    assert img.size[0] > 0 and img.size[1] > 0

    # 6. Independent verification with c2patool: must report no manifest
    if os.path.exists(C2PATOOL_PATH):
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tf:
            tf.write(clean_bytes)
            tmp_clean = tf.name
        try:
            res = subprocess.run([C2PATOOL_PATH, tmp_clean], capture_output=True, text=True)
            output = res.stdout + res.stderr
            assert "No claim found" in output or "No manifest found" in output or res.returncode != 0
        finally:
            if os.path.exists(tmp_clean):
                os.remove(tmp_clean)

    # 7. External verification info endpoint
    ev_resp = client.get("/api/external-verify/info")
    assert ev_resp.status_code == 200
    ev_data = ev_resp.json()
    assert ev_data["verifier_url"] == "https://openai.com/verify/"
    assert ev_data["local_only"] is False
    assert "upload" in ev_data["disclosure"].lower()

    # 8. Record external verification outcome
    rec_resp = client.post(
        "/api/external-verify/record",
        json={"filename": "CA.jpg", "outcome": "Detected by an authorized verifier"},
    )
    assert rec_resp.status_code == 200
    assert rec_resp.json()["status"] == "recorded"
