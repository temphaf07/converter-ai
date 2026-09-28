from __future__ import annotations

import time
from io import BytesIO
from pathlib import Path

import pandas as pd
from fastapi.testclient import TestClient
from PIL import Image

from backend.ai_parser import parse_conversion_intent
from backend.converter import convert_file
from backend import main


def test_prompt_parser_prioritises_explicit_format() -> None:
    intent = parse_conversion_intent("convert this document to PDF", "resume.docx")
    assert intent.source_format == "docx"
    assert intent.target_format == "pdf"


def test_image_and_table_conversions(tmp_path: Path) -> None:
    source_image = tmp_path / "image.jpg"
    Image.new("RGB", (16, 16), "green").save(source_image)
    image_output = convert_file(source_image, parse_conversion_intent("make it PNG", source_image.name), tmp_path)
    assert image_output.suffix == ".png" and image_output.is_file()

    source_table = tmp_path / "table.csv"
    pd.DataFrame({"name": ["A"], "score": [10]}).to_csv(source_table, index=False)
    table_output = convert_file(source_table, parse_conversion_intent("turn this into Excel", source_table.name), tmp_path)
    assert table_output.suffix == ".xlsx" and pd.read_excel(table_output).iloc[0]["name"] == "A"


def test_text_to_pdf(tmp_path: Path) -> None:
    source = tmp_path / "note.txt"
    source.write_text("A local PDF test", encoding="utf-8")
    output = convert_file(source, parse_conversion_intent("convert to PDF", source.name), tmp_path)
    assert output.read_bytes().startswith(b"%PDF")


def test_api_upload_job_and_download(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(main, "UPLOAD_DIR", tmp_path / "uploads")
    monkeypatch.setattr(main, "CONVERTED_DIR", tmp_path / "converted")
    main.UPLOAD_DIR.mkdir()
    main.CONVERTED_DIR.mkdir()
    main.JOBS.clear()
    client = TestClient(main.app)
    image_data = BytesIO()
    Image.new("RGB", (8, 8), "red").save(image_data, "JPEG")
    upload = client.post("/upload", files={"file": ("sample.jpg", image_data.getvalue(), "image/jpeg")})
    assert upload.status_code == 200
    chat = client.post("/chat", json={"filename": upload.json()["filename"], "prompt": "turn this into PNG"})
    assert chat.status_code == 200 and chat.json()["job_id"]
    job_id = chat.json()["job_id"]
    for _ in range(30):
        job = client.get(f"/jobs/{job_id}").json()
        if job["status"] in {"complete", "failed"}:
            break
        time.sleep(0.1)
    assert job["status"] == "complete"
    assert client.get(job["download_url"]).status_code == 200


def test_unsupported_request_is_explained(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(main, "UPLOAD_DIR", tmp_path / "uploads")
    monkeypatch.setattr(main, "CONVERTED_DIR", tmp_path / "converted")
    main.UPLOAD_DIR.mkdir()
    main.CONVERTED_DIR.mkdir()
    client = TestClient(main.app)
    upload = client.post("/upload", files={"file": ("note.txt", b"hello", "text/plain")})
    response = client.post("/chat", json={"filename": upload.json()["filename"], "prompt": "convert this to MP3"})
    assert response.status_code == 200
    assert response.json()["job_id"] is None
    assert "can convert to" in response.json()["message"]
