"""
API integration tests for FastAPI backend server.
"""

import io
import os
import zipfile
import pytest
from starlette.testclient import TestClient

from app.backend.server import app


client = TestClient(app)
FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def test_api_health():
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert data["local_only"] is True


def test_api_inspect_jpeg_with_c2pa():
    path = os.path.join(FIXTURES_DIR, "CA.jpg")
    with open(path, "rb") as f:
        resp = client.post("/api/inspect", files={"file": ("CA.jpg", f, "image/jpeg")})
    assert resp.status_code == 200
    data = resp.json()
    assert data["format_name"] == "JPEG"
    assert data["has_c2pa"] is True
    assert data["status_code"] == "c2pa_detected"
    assert data["structure_count"] == 2


def test_api_inspect_jpeg_without_c2pa():
    path = os.path.join(FIXTURES_DIR, "no_manifest.jpg")
    with open(path, "rb") as f:
        resp = client.post("/api/inspect", files={"file": ("no_manifest.jpg", f, "image/jpeg")})
    assert resp.status_code == 200
    data = resp.json()
    assert data["format_name"] == "JPEG"
    assert data["has_c2pa"] is False
    assert data["status_code"] == "no_c2pa"


def test_api_inspect_png():
    path = os.path.join(FIXTURES_DIR, "signed_test.png")
    with open(path, "rb") as f:
        resp = client.post("/api/inspect", files={"file": ("signed_test.png", f, "image/png")})
    assert resp.status_code == 200
    data = resp.json()
    assert data["format_name"] == "PNG"
    assert data["has_c2pa"] is True
    assert data["structure_count"] == 1


def test_api_inspect_unsupported():
    fake_gif = b"GIF89a\x01\x00\x01\x00\x80\x00\x00\xff\xff\xff\x00\x00\x00!\xf9"
    resp = client.post("/api/inspect", files={"file": ("test.gif", fake_gif, "image/gif")})
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_supported"] is False
    assert data["status_code"] == "unsupported"


def test_api_clean_and_download_flow():
    path = os.path.join(FIXTURES_DIR, "CA.jpg")
    with open(path, "rb") as f:
        resp = client.post("/api/clean", files={"file": ("CA.jpg", f, "image/jpeg")})
    assert resp.status_code == 200
    data = resp.json()
    assert data["output_filename"] == "CA_C2PA-removed.jpg"
    assert data["verification_passed"] is True
    assert data["structures_removed"] == 2
    assert data["bytes_removed"] > 100000

    job_id = data["job_id"]
    download_url = data["download_url"]

    # Test download
    dl_resp = client.get(download_url)
    assert dl_resp.status_code == 200
    assert dl_resp.headers["content-type"] == "image/jpeg"
    assert 'filename="CA_C2PA-removed.jpg"' in dl_resp.headers["content-disposition"]
    assert len(dl_resp.content) == data["output_size"]


def test_api_batch_inspect_and_clean():
    f1 = open(os.path.join(FIXTURES_DIR, "CA.jpg"), "rb")
    f2 = open(os.path.join(FIXTURES_DIR, "signed_test.png"), "rb")

    # Inspect batch
    resp_insp = client.post(
        "/api/batch/inspect",
        files=[("files", ("CA.jpg", f1, "image/jpeg")), ("files", ("signed_test.png", f2, "image/png"))],
    )
    assert resp_insp.status_code == 200
    items = resp_insp.json()["items"]
    assert len(items) == 2
    assert items[0]["has_c2pa"] is True
    assert items[1]["has_c2pa"] is True

    f1.seek(0)
    f2.seek(0)

    # Clean batch
    resp_clean = client.post(
        "/api/batch/clean",
        files=[("files", ("CA.jpg", f1, "image/jpeg")), ("files", ("signed_test.png", f2, "image/png"))],
    )
    assert resp_clean.status_code == 200
    clean_items = resp_clean.json()["items"]
    assert len(clean_items) == 2
    assert clean_items[0]["success"] is True
    assert clean_items[1]["success"] is True

    job_ids = [item["result"]["job_id"] for item in clean_items]

    # Download batch ZIP
    resp_zip = client.post("/api/batch/download-zip", json={"job_ids": job_ids})
    assert resp_zip.status_code == 200
    assert resp_zip.headers["content-type"] == "application/zip"

    # Verify ZIP contents
    with zipfile.ZipFile(io.BytesIO(resp_zip.content)) as z:
        names = z.namelist()
        assert "CA_C2PA-removed.jpg" in names
        assert "signed_test_C2PA-removed.png" in names

    f1.close()
    f2.close()
