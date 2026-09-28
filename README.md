# Convertly

A fully local, chat-driven file converter. The browser uploads to the local FastAPI server; conversion intent is interpreted by a locally running Ollama model. No cloud service is used.

## Run it

1. Install and start [Ollama](https://ollama.com). This project defaults to
   `mistral:latest`, which is already installed on this machine. To use a
   different installed model for one terminal session, set `OLLAMA_MODEL`, for
   example: `$env:OLLAMA_MODEL = "gpt-oss:20b"`.
2. Create a virtual environment and install backend packages:
   `python -m venv .venv`
   `.venv\\Scripts\\pip install -r backend\\requirements.txt`
3. Start the app from the repository root:
   `.venv\\Scripts\\uvicorn backend.main:app --reload`
4. Open http://127.0.0.1:8000.

## Run the checks

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

## Supported local conversions

- Images: JPG, JPEG, PNG, WebP, BMP, TIFF, GIF and ICO between each other, plus image → PDF.
- Tables: CSV, TSV, XLS/XLSX and JSON → CSV, TSV, XLSX, JSON or HTML.
- PDFs: PDF → DOCX, TXT, PNG or JPG (PNG/JPG renders the first page).
- Text: TXT, Markdown and HTML → PDF; DOCX → TXT or PDF.
- Media: MP3, WAV, M4A, FLAC, MP4, MOV, MKV and WebM when FFmpeg is installed and available on `PATH`.

The app reports progress during a conversion and provides the download button below
the chat when it finishes. No fixed program can faithfully convert every possible
file format; unsupported combinations are reported with the formats that work for
the uploaded file.

### Keeping DOCX layout in PDFs

DOCX → PDF uses Microsoft Word's local PDF renderer to preserve headings,
tables, margins, fonts, and alignment. Open Microsoft Word once and complete
any activation or first-run prompts before using this conversion. If Word is
not available, install LibreOffice as a local alternative; the app will not
fall back to a plain-text PDF because that would lose the original layout.
