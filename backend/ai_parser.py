"""Local intent detection for natural-language conversion requests."""

from __future__ import annotations

import os
import re
from pathlib import Path

import ollama
from pydantic import BaseModel, Field


class ConversionIntent(BaseModel):
    source_format: str = Field(description="Lowercase input extension, without a dot")
    target_format: str = Field(description="Requested lowercase output extension, without a dot")
    is_supported: bool = Field(description="True when a target format was identified")


ALIASES = {
    "excel": "xlsx", "spreadsheet": "xlsx", "word": "docx", "document": "docx",
    "jpeg": "jpg", "photo": "jpg", "image": "png", "text": "txt",
    "markdown": "md", "web page": "html", "webpage": "html",
}
KNOWN_FORMATS = {
    "pdf", "docx", "doc", "txt", "md", "html", "json", "xml", "yaml", "yml",
    "csv", "tsv", "xlsx", "xls", "ods", "jpg", "jpeg", "png", "webp", "bmp",
    "tiff", "gif", "ico", "mp3", "wav", "m4a", "flac", "mp4", "mov", "mkv", "webm",
}


def _extension(filename: str) -> str:
    return Path(filename).suffix.lower().lstrip(".")


def _normalise(value: str) -> str:
    value = value.strip().lower().lstrip(".")
    return ALIASES.get(value, value)


def _target_from_prompt(prompt: str) -> str:
    """Handle direct wording immediately, without waiting on a language model."""
    cleaned = prompt.lower().replace(".", " ")
    # A literal extension such as “PDF” wins over generic words such as
    # “document” or “image”, which may merely describe the uploaded file.
    for word in reversed(re.findall(r"\b[a-z0-9]+\b", cleaned)):
        if word in KNOWN_FORMATS:
            return _normalise(word)
    alias_matches = [
        (match.start(), target)
        for phrase, target in ALIASES.items()
        for match in re.finditer(rf"\b{re.escape(phrase)}\b", cleaned)
    ]
    if alias_matches:
        return max(alias_matches, key=lambda item: item[0])[1]
    return ""


def parse_conversion_intent(prompt: str, filename: str) -> ConversionIntent:
    """Use a quick local parser first, then local Ollama only when needed."""
    source = _extension(filename)
    target = _target_from_prompt(prompt)
    if target:
        return ConversionIntent(source_format=source, target_format=target, is_supported=True)

    response = ollama.chat(
        model=os.getenv("OLLAMA_MODEL", "mistral:latest"),
        messages=[
            {"role": "system", "content": "Return JSON only. Identify the requested output extension, lowercase and without a dot. Leave target_format empty if unknown."},
            {"role": "user", "content": f"Input file: {filename}\nRequest: {prompt}"},
        ],
        format=ConversionIntent.model_json_schema(),
        options={"temperature": 0},
    )
    intent = ConversionIntent.model_validate_json(response.message.content)
    intent.source_format = source
    intent.target_format = _normalise(intent.target_format)
    intent.is_supported = bool(intent.target_format)
    return intent
