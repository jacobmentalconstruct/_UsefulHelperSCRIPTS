from typing import Optional

# ContentExtractorMS location can vary after refactors.
# Try a few likely import paths; if not found, raise a clear runtime error.
ContentExtractorMS: Optional[object] = None

try:
    # Try absolute package import first
    from src._microservices._ContentExtractorMS import ContentExtractorMS
except ImportError:
    try:
        # Fallback to relative import if running within the same directory
        from _ContentExtractorMS import ContentExtractorMS
    except ImportError as e:
        ContentExtractorMS = None
        _import_error = e

if ContentExtractorMS is None:
    raise ImportError(
        "ContentExtractorMS could not be imported. Expected one of: "
        "microservices._ContentExtractorMS, _ContentExtractorMS, __ContentExtractorMS. "
        f"Original error: {_import_error}"
    )

# Singleton instance to reuse the extractor logic
_extractor = ContentExtractorMS()  # type: ignore

def extract_text_from_pdf(blob: bytes) -> str:
    """Proxy to ContentExtractorMS PDF logic."""
    return _extractor._extract_pdf(blob)

def extract_text_from_html(html_text: str) -> str:
    """Proxy to ContentExtractorMS HTML logic."""
    return _extractor._extract_html(html_text)


