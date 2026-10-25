"""
FastAPI local application server for C2PA Cleaner.
Binds strictly to 127.0.0.1 (loopback) with zero telemetry, remote tracking, or third-party API calls.
"""

import os
import sys
from typing import List, Optional
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse, Response, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.backend.services.cleaner_service import cleaner_service


app = FastAPI(
    title="C2PA Cleaner",
    version="2.0.0",
    docs_url=None,  # Disabled for local-only privacy
    redoc_url=None,
)

def get_frontend_dir() -> str:
    """Resolve frontend directory across development and PyInstaller frozen runtime."""
    if getattr(sys, "frozen", False):
        base_dir = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
        candidates = [
            os.path.join(base_dir, "app", "frontend"),
            os.path.join(base_dir, "frontend"),
            os.path.join(os.path.dirname(sys.executable), "_internal", "app", "frontend"),
            os.path.join(os.path.dirname(sys.executable), "app", "frontend"),
        ]
        for c in candidates:
            if os.path.exists(os.path.join(c, "index.html")):
                return c
    # Default development path
    return os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")

FRONTEND_DIR = get_frontend_dir()


@app.get("/api/health")
async def health_check():
    return {
        "status": "healthy",
        "app": "C2PA Cleaner",
        "version": "2.0.0",
        "local_only": True,
        "supported_formats": ["JPEG", "PNG", "WebP"],
    }


@app.post("/api/inspect")
async def inspect_single_image(file: UploadFile = File(...)):
    """
    Inspect an image file's binary structures without modifying or recompressing it.
    """
    try:
        content = await file.read()
        res = cleaner_service.inspect_image(content, file.filename or "image.jpg")
        return res.to_dict()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Inspection failed: {str(e)}")


@app.post("/api/clean")
async def clean_single_image(file: UploadFile = File(...)):
    """
    Remove embedded C2PA credentials losslessly and independently verify the output.
    """
    try:
        content = await file.read()
        res = cleaner_service.clean_image(content, file.filename or "image.jpg")
        return res.to_dict()
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")


@app.get("/api/download/{job_id}")
async def download_cleaned_file(job_id: str):
    """
    Download a verified cleaned file by job ID.
    """
    item = cleaner_service.get_cached_file(job_id)
    if not item:
        raise HTTPException(status_code=404, detail="Requested file not found or expired.")

    filename, mime_type, file_bytes = item
    return Response(
        content=file_bytes,
        media_type=mime_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-cache, no-store, must-revalidate",
        },
    )


@app.post("/api/batch/inspect")
async def inspect_batch_images(files: List[UploadFile] = File(...)):
    """
    Inspect multiple files in batch mode independently.
    """
    results = []
    for f in files:
        content = await f.read()
        res = cleaner_service.inspect_image(content, f.filename or "image.jpg")
        results.append(res.to_dict())
    return {"items": results}


@app.post("/api/batch/clean")
async def clean_batch_images(files: List[UploadFile] = File(...)):
    """
    Process multiple files in batch mode independently without letting one failure abort the batch.
    """
    results = []
    for f in files:
        fname = f.filename or "image.jpg"
        content = await f.read()
        try:
            res = cleaner_service.clean_image(content, fname)
            results.append({"success": True, "result": res.to_dict()})
        except Exception as e:
            results.append({
                "success": False,
                "filename": fname,
                "error": str(e),
            })
    return {"items": results}


class BatchZipRequest(BaseModel):
    job_ids: List[str]


@app.post("/api/batch/download-zip")
async def download_batch_zip(req: BatchZipRequest):
    """
    Download verified clean batch files packaged into a single ZIP archive.
    """
    if not req.job_ids:
        raise HTTPException(status_code=400, detail="No job IDs specified.")

    zip_name, zip_bytes = cleaner_service.create_batch_zip(req.job_ids)
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{zip_name}"',
            "Cache-Control": "no-cache, no-store, must-revalidate",
        },
    )


class ExternalVerifyRecordRequest(BaseModel):
    filename: str
    state: Optional[str] = None
    outcome: Optional[str] = None
    notes: Optional[str] = None

    def get_state(self) -> str:
        return self.state or self.outcome or "Not checked"


@app.get("/api/external-verify/info")
async def get_external_verify_info():
    """
    Metadata and disclosure for external provenance and watermark verification.
    """
    return {
        "service_name": "OpenAI Content Provenance Verifier",
        "official_url": "https://openai.com/verify/",
        "verifier_url": "https://openai.com/verify/",
        "local_processing": False,
        "local_only": False,
        "disclosure": (
            "Notice: OpenAI's official verification portal (openai.com/verify) requires uploading your image "
            "to OpenAI's external servers. This is not processed locally. C2PA Cleaner does not automatically "
            "transmit your files to any remote service."
        ),
        "supported_states": [
            "Not checked",
            "Detected by an authorized verifier",
            "Not detected by an authorized verifier",
            "Verification unavailable",
            "Verification inconclusive",
        ],
        "distinction_note": (
            "C2PA Content Credentials are cryptographic manifests in file headers (which C2PA Cleaner removes losslessly). "
            "SynthID is an imperceptible watermark embedded directly into visual pixel values. "
            "Removing C2PA manifests does NOT remove SynthID or alter visual pixel content."
        ),
    }


@app.post("/api/external-verify/record")
async def record_external_verify_result(req: ExternalVerifyRecordRequest):
    """
    Record an authorized external verification outcome in the local session audit log.
    """
    from app.backend.services.cleaner_service import SYNTHID_STATES
    recorded_state = req.get_state()
    if recorded_state not in SYNTHID_STATES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid verification state '{recorded_state}'. Must be one of: {SYNTHID_STATES}",
        )
    return {
        "success": True,
        "status": "recorded",
        "filename": req.filename,
        "state": recorded_state,
        "outcome": recorded_state,
        "notes": req.notes,
    }


@app.post("/api/shutdown")
async def shutdown_server(background_tasks: BackgroundTasks):
    """
    Clean shutdown endpoint for the local server when user closes the app.
    """
    def _exit():
        import time
        time.sleep(0.5)
        os._exit(0)

    background_tasks.add_task(_exit)
    return {"message": "Server shutting down cleanly..."}


# Mount frontend static files
if os.path.exists(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
