"""
Small compatibility helpers for legacy content extraction services.
"""

from __future__ import annotations

import io
import re
from html import unescape
from typing import Union


def extract_text_from_pdf(source: Union[bytes, bytearray, str]) -> str:
    """
    Best-effort PDF text extraction.
    """

    try:
        from pypdf import PdfReader
    except Exception:
        return ""

    try:
        if isinstance(source, (bytes, bytearray)):
            reader = PdfReader(io.BytesIO(source))
        else:
            reader = PdfReader(source)
    except Exception:
        return ""

    parts = []
    for page in reader.pages:
        try:
            parts.append(page.extract_text() or "")
        except Exception:
            continue
    return "\n".join(part for part in parts if part)


def extract_text_from_html(raw_html: str) -> str:
    """
    Best-effort HTML to text extraction with stdlib fallback.
    """

    try:
        from bs4 import BeautifulSoup
    except Exception:
        text = re.sub(r"<[^>]+>", " ", raw_html)
        text = unescape(text)
        return re.sub(r"\s+", " ", text).strip()

    try:
        soup = BeautifulSoup(raw_html, "html.parser")
        text = soup.get_text(separator=" ", strip=True)
        return re.sub(r"\s+", " ", text).strip()
    except Exception:
        return ""

