"""FastAPI application for the local chat-driven file converter."""

from __future__ import annotations

import shutil
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .ai_parser import ConversionIntent, parse_conversion_intent
from .converter import ConversionError, available_targets, can_convert, convert_file

BASE_DIR = Path(__file__).resolve().parent.parent
UPLOAD_DIR = BASE_DIR / "uploads"
CONVERTED_DIR = BASE_DIR / "converted"
FRONTEND_DIR = BASE_DIR / "frontend"
for directory in (UPLOAD_DIR, CONVERTED_DIR):
    directory.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Local AI File Converter")
JOBS: dict[str, dict[str, object]] = {}
JOBS_LOCK = threading.Lock()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8000", "http://127.0.0.1:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    prompt: str
    filename: str


def safe_filename(name: str) -> str:
    original = Path(name).name
    if not original or original in {".", ".."}:
        raise HTTPException(status_code=400, detail="A valid filename is required.")
    return f"{uuid.uuid4().hex}_{original}"


def update_job(job_id: str, progress: int, message: str, status: str = "converting") -> None:
    with JOBS_LOCK:
        if job_id in JOBS:
            JOBS[job_id].update({"progress": progress, "message": message, "status": status})


def run_conversion(job_id: str, source: Path, intent: ConversionIntent) -> None:
    try:
        output = convert_file(source, intent, CONVERTED_DIR, lambda value, text: update_job(job_id, value, text))
        with JOBS_LOCK:
            JOBS[job_id].update({
                "status": "complete", "progress": 100, "message": "Conversion complete",
                "download_url": f"/download/{output.name}", "completed_at": datetime.now(timezone.utc).isoformat(),
            })
    except ConversionError as exc:
        update_job(job_id, 0, str(exc), "failed")
    except Exception:
        update_job(job_id, 0, "The conversion failed. Check that the uploaded file is valid and try again.", "failed")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/formats/{source_format}")
def formats(source_format: str) -> dict[str, object]:
    return {"source_format": source_format.lower(), "targets": available_targets(source_format)}


@app.post("/upload")
async def upload(file: UploadFile = File(...)) -> dict[str, str]:
    if not file.filename:
        raise HTTPException(status_code=400, detail="Choose a file to upload.")
    stored_name = safe_filename(file.filename)
    target = UPLOAD_DIR / stored_name
    try:
        with target.open("wb") as output:
            shutil.copyfileobj(file.file, output)
    finally:
        await file.close()
    return {"filename": stored_name, "original_name": Path(file.filename).name}


@app.post("/chat")
def chat(request: ChatRequest) -> dict[str, object]:
    filename = Path(request.filename).name
    source = UPLOAD_DIR / filename
    if not source.is_file():
        raise HTTPException(status_code=404, detail="The uploaded file was not found. Upload it again and retry.")
    if not request.prompt.strip():
        raise HTTPException(status_code=400, detail="Enter a conversion request.")
    try:
        intent = parse_conversion_intent(request.prompt, filename)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="I couldn't reach the local Ollama model. Confirm Ollama is running, then try again.") from exc

    if not intent.is_supported or not can_convert(intent.source_format, intent.target_format):
        targets = available_targets(intent.source_format)
        readable = ", ".join(item.upper() for item in targets) or "no installed converter"
        return {
            "message": f"I couldn't identify a supported output from that request. For this {intent.source_format.upper()} file, you can convert to: {readable}.",
            "intent": intent.model_dump(), "job_id": None,
        }

    job_id = uuid.uuid4().hex
    with JOBS_LOCK:
        JOBS[job_id] = {"status": "queued", "progress": 0, "message": "Conversion queued", "download_url": None}
    threading.Thread(target=run_conversion, args=(job_id, source, intent), daemon=True).start()
    return {
        "message": f"Converting your {intent.source_format.upper()} file to {intent.target_format.upper()} now.",
        "intent": intent.model_dump(), "job_id": job_id,
    }


@app.get("/jobs/{job_id}")
def job_status(job_id: str) -> dict[str, object]:
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Conversion job not found.")
        return dict(job)


@app.get("/download/{filename}")
def download(filename: str) -> FileResponse:
    path = CONVERTED_DIR / Path(filename).name
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Converted file not found.")
    return FileResponse(path, filename=path.name, media_type="application/octet-stream")


app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
