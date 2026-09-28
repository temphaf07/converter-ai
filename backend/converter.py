"""Real local conversion functions and a capability-aware router."""

from __future__ import annotations

import shutil
import subprocess
import textwrap
import tempfile
import uuid
from base64 import b64encode
from collections.abc import Callable
from pathlib import Path

import pandas as pd
import pymupdf
from docx import Document
from pdf2docx import Converter as PdfConverter
from PIL import Image

from .ai_parser import ConversionIntent

Progress = Callable[[int, str], None]
IMAGE_FORMATS = {"jpg", "jpeg", "png", "webp", "bmp", "tiff", "gif", "ico"}
TABLE_INPUTS = {"csv", "tsv", "xlsx", "xls", "json"}
TABLE_OUTPUTS = {"csv", "tsv", "xlsx", "json", "html"}
MEDIA_FORMATS = {"mp3", "wav", "m4a", "flac", "mp4", "mov", "mkv", "webm"}
WORD_EXECUTABLES = (
    Path("C:/Program Files/Microsoft Office/root/Office16/WINWORD.EXE"),
    Path("C:/Program Files (x86)/Microsoft Office/root/Office16/WINWORD.EXE"),
)


class ConversionError(Exception):
    """A user-facing conversion failure."""


def _emit(progress: Progress | None, value: int, message: str) -> None:
    if progress:
        progress(value, message)


def _output(source: Path, destination: Path, target: str) -> Path:
    destination.mkdir(parents=True, exist_ok=True)
    return destination / f"{source.stem}-{uuid.uuid4().hex[:8]}.{target}"


def available_targets(source_format: str) -> list[str]:
    source = source_format.lower()
    if source in IMAGE_FORMATS:
        return sorted((IMAGE_FORMATS | {"pdf"}) - {source})
    if source in TABLE_INPUTS:
        return sorted(TABLE_OUTPUTS - {source})
    if source == "pdf":
        return ["docx", "jpg", "png", "txt"]
    if source == "docx":
        targets = ["txt"]
        if _soffice_path() or any(path.is_file() for path in WORD_EXECUTABLES):
            targets.insert(0, "pdf")
        return targets
    if source in {"txt", "md", "html"}:
        return ["pdf", "txt"]
    if source in MEDIA_FORMATS:
        return sorted(MEDIA_FORMATS - {source})
    return []


def can_convert(source_format: str, target_format: str) -> bool:
    return target_format.lower() in available_targets(source_format)


def convert_image(source: Path, target: str, destination: Path, progress: Progress | None) -> Path:
    output = _output(source, destination, target)
    _emit(progress, 25, "Reading image")
    with Image.open(source) as image:
        if target == "pdf":
            image.convert("RGB").save(output, "PDF", resolution=100.0)
        elif target in {"jpg", "jpeg"}:
            if image.mode in {"RGBA", "LA"} or (image.mode == "P" and "transparency" in image.info):
                canvas = Image.new("RGB", image.size, "white")
                rgba = image.convert("RGBA")
                canvas.paste(rgba, mask=rgba.getchannel("A"))
                image = canvas
            else:
                image = image.convert("RGB")
            image.save(output, "JPEG", quality=95, optimize=True)
        else:
            image.save(output)
    _emit(progress, 90, "Writing converted image")
    return output


def _read_table(source: Path) -> pd.DataFrame:
    suffix = source.suffix.lower().lstrip(".")
    if suffix == "csv":
        try:
            return pd.read_csv(source)
        except UnicodeDecodeError:
            return pd.read_csv(source, encoding="latin-1")
    if suffix == "tsv":
        return pd.read_csv(source, sep="\t")
    if suffix in {"xlsx", "xls"}:
        return pd.read_excel(source)
    if suffix == "json":
        return pd.read_json(source)
    raise ConversionError("That spreadsheet format cannot be read locally.")


def convert_table(source: Path, target: str, destination: Path, progress: Progress | None) -> Path:
    output = _output(source, destination, target)
    _emit(progress, 20, "Reading table data")
    frame = _read_table(source)
    _emit(progress, 65, "Transforming table")
    if target == "xlsx":
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            frame.to_excel(writer, index=False, sheet_name="Data")
    elif target == "csv":
        frame.to_csv(output, index=False)
    elif target == "tsv":
        frame.to_csv(output, index=False, sep="\t")
    elif target == "json":
        frame.to_json(output, orient="records", indent=2)
    elif target == "html":
        output.write_text(frame.to_html(index=False), encoding="utf-8")
    else:
        raise ConversionError(f"Table output {target.upper()} is unavailable.")
    _emit(progress, 90, "Saving converted table")
    return output


def convert_pdf(source: Path, target: str, destination: Path, progress: Progress | None) -> Path:
    output = _output(source, destination, target)
    _emit(progress, 15, "Opening PDF")
    if target == "docx":
        converter = PdfConverter(str(source))
        try:
            _emit(progress, 45, "Extracting PDF layout")
            converter.convert(str(output))
        finally:
            converter.close()
    else:
        document = pymupdf.open(source)
        try:
            if target == "txt":
                _emit(progress, 45, "Extracting PDF text")
                output.write_text("\n\n".join(page.get_text() for page in document), encoding="utf-8")
            else:
                _emit(progress, 45, "Rendering first PDF page")
                pixmap = document[0].get_pixmap(matrix=pymupdf.Matrix(2, 2), alpha=False)
                pixmap.save(str(output))
        finally:
            document.close()
    _emit(progress, 90, "Finalising PDF conversion")
    return output


def _write_text_pdf(text: str, output: Path) -> None:
    """Create a readable, paginated PDF from plain text without cloud tools."""
    lines: list[str] = []
    for paragraph in text.splitlines() or [""]:
        lines.extend(textwrap.wrap(paragraph, width=96, replace_whitespace=False) or [""])
    document = pymupdf.open()
    try:
        for start in range(0, len(lines), 48):
            page = document.new_page()
            y = 54
            for line in lines[start:start + 48]:
                page.insert_text((45, y), line, fontsize=10, fontname="helv")
                y += 14
        document.save(output)
    finally:
        document.close()


def _soffice_path() -> str | None:
    return (
        shutil.which("soffice")
        or shutil.which("libreoffice")
        or next((str(path) for path in (
            Path("C:/Program Files/LibreOffice/program/soffice.exe"),
            Path("C:/Program Files (x86)/LibreOffice/program/soffice.exe"),
        ) if path.is_file()), None)
    )


def _export_docx_pdf_with_libreoffice(source: Path, output: Path, soffice: str) -> bool:
    """Export with LibreOffice when it is installed, retaining document layout."""
    with tempfile.TemporaryDirectory(dir=output.parent) as staging:
        staging_dir = Path(staging)
        profile_dir = staging_dir / "profile"
        result = subprocess.run(
            [
                soffice, "--headless", f"-env:UserInstallation={profile_dir.as_uri()}",
                "--convert-to", "pdf", "--outdir", str(staging_dir), str(source),
            ],
            capture_output=True, text=True, timeout=120,
        )
        generated = staging_dir / f"{source.stem}.pdf"
        if result.returncode == 0 and generated.is_file():
            shutil.move(str(generated), output)
            return True
    return False


def _export_docx_pdf_with_word(source: Path, output: Path) -> None:
    """Use the installed Microsoft Word renderer to retain DOCX layout in PDF."""
    # Passing an encoded PowerShell command keeps file paths safe even when they
    # include quotes, spaces, or non-ASCII characters.
    source_literal = str(source).replace("'", "''")
    output_literal = str(output).replace("'", "''")
    script = f"""
$ErrorActionPreference = 'Stop'
$word = $null
$document = $null
try {{
    $word = New-Object -ComObject Word.Application
    $word.Visible = $false
    $word.DisplayAlerts = 0
    $document = $word.Documents.Open('{source_literal}', $false, $true)
    $document.ExportAsFixedFormat('{output_literal}', 17)
}} finally {{
    if ($document) {{ $document.Close($false) }}
    if ($word) {{ $word.Quit() }}
}}
"""
    encoded = b64encode(script.encode("utf-16-le")).decode("ascii")
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode or not output.is_file():
        output.unlink(missing_ok=True)
        raise ConversionError(
            "Layout-preserving DOCX to PDF needs a working local office renderer. "
            "Microsoft Word is installed, but its automation service did not start. "
            "Close Word, open it once manually to finish activation or first-run setup, "
            "then restart this app and try again. LibreOffice is an alternative local renderer."
        )


def convert_docx(source: Path, target: str, destination: Path, progress: Progress | None) -> Path:
    output = _output(source, destination, target)
    _emit(progress, 30, "Reading Word document")
    document = Document(source)
    text = "\n".join(paragraph.text for paragraph in document.paragraphs)
    if target == "txt":
        output.write_text(text, encoding="utf-8")
    else:
        _emit(progress, 60, "Preserving Word layout")
        soffice = _soffice_path()
        if soffice and _export_docx_pdf_with_libreoffice(source, output, soffice):
            pass
        elif any(path.is_file() for path in WORD_EXECUTABLES):
            _export_docx_pdf_with_word(source, output)
        else:
            raise ConversionError(
                "Layout-preserving DOCX to PDF needs Microsoft Word or LibreOffice installed locally. "
                "The app will not create a plain-text PDF because it would lose your alignment."
            )
    _emit(progress, 90, "Saving converted document")
    return output


def convert_text_to_pdf(source: Path, destination: Path, progress: Progress | None) -> Path:
    output = _output(source, destination, "pdf")
    _emit(progress, 25, "Reading text")
    text = source.read_text(encoding="utf-8", errors="replace")
    _emit(progress, 75, "Creating PDF")
    _write_text_pdf(text, output)
    _emit(progress, 90, "Saving PDF")
    return output


def convert_media(source: Path, target: str, destination: Path, progress: Progress | None) -> Path:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise ConversionError("Audio/video conversion needs FFmpeg. Install FFmpeg, add it to PATH, restart the server, and try again.")
    output = _output(source, destination, target)
    _emit(progress, 15, "Starting FFmpeg")
    process = subprocess.run([ffmpeg, "-y", "-i", str(source), str(output)], capture_output=True, text=True)
    if process.returncode:
        raise ConversionError("FFmpeg could not convert this media file. The target may require an unavailable codec.")
    _emit(progress, 90, "Finalising media file")
    return output


def convert_file(source: Path, intent: ConversionIntent, converted_dir: Path, progress: Progress | None = None) -> Path:
    """Route a validated request to a real local converter."""
    source_format, target = intent.source_format, intent.target_format
    if not can_convert(source_format, target):
        options = ", ".join(item.upper() for item in available_targets(source_format)) or "none detected"
        raise ConversionError(f"{source_format.upper() or 'This file type'} cannot be converted to {target.upper() or 'that format'} here. Available outputs: {options}.")
    _emit(progress, 8, "Conversion queued")
    if source_format in IMAGE_FORMATS:
        return convert_image(source, target, converted_dir, progress)
    if source_format in TABLE_INPUTS:
        return convert_table(source, target, converted_dir, progress)
    if source_format == "pdf":
        return convert_pdf(source, target, converted_dir, progress)
    if source_format == "docx":
        return convert_docx(source, target, converted_dir, progress)
    if source_format in {"txt", "md", "html"} and target == "pdf":
        return convert_text_to_pdf(source, converted_dir, progress)
    if source_format in {"txt", "md", "html"} and target == "txt":
        output = _output(source, converted_dir, "txt")
        output.write_text(source.read_text(encoding="utf-8", errors="replace"), encoding="utf-8")
        return output
    if source_format in MEDIA_FORMATS:
        return convert_media(source, target, converted_dir, progress)
    raise ConversionError("No local converter is available for this file.")
