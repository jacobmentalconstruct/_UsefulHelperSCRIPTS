from _ContentExtractorMS import ContentExtractorMS

# Singleton instance to reuse the extractor logic
_extractor = ContentExtractorMS()

def extract_text_from_pdf(blob: bytes) -> str:
    """Proxy to ContentExtractorMS PDF logic."""
    return _extractor._extract_pdf(blob)

def extract_text_from_html(html_text: str) -> str:
    """Proxy to ContentExtractorMS HTML logic."""
    return _extractor._extract_html(html_text)
