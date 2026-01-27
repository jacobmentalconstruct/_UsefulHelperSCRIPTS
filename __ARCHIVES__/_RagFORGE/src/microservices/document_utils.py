import io
import re
from typing import Tuple, Optional

# Third-party imports (from requirements.txt)
try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

def extract_text_from_pdf(file_bytes: bytes) -> str:
    """Extracts text from a PDF blob using pypdf."""
    if not PdfReader:
        return ""
    
    text_content = []
    try:
        # Wrap bytes in a stream for PdfReader
        stream = io.BytesIO(file_bytes)
        reader = PdfReader(stream)
        
        for page in reader.pages:
            extracted = page.extract_text()
            if extracted:
                text_content.append(extracted)
        
        return "\n".join(text_content)
    except Exception as e:
        print(f"[DocumentUtils] PDF Extraction Error: {e}")
        return ""

def extract_text_from_html(html_content: str) -> str:
    """Cleans HTML to raw text using BeautifulSoup."""
    if not BeautifulSoup:
        return strip_tags_regex(html_content)
    
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Kill all script and style elements
        for script in soup(["script", "style", "meta", "noscript"]):
            script.decompose()
            
        text = soup.get_text()
        
        # Collapse whitespace
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        text = '\n'.join(chunk for chunk in chunks if chunk)
        
        return text
    except Exception as e:
        print(f"[DocumentUtils] HTML Parsing Error: {e}")
        return strip_tags_regex(html_content)

def strip_tags_regex(html: str) -> str:
    """Fallback if BS4 is missing."""
    clean = re.compile('<.*?>')
    return re.sub(clean, '', html)
