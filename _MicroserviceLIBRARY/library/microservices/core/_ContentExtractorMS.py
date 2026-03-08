"""
SERVICE_NAME: _ContentExtractorMS
ENTRY_POINT: _ContentExtractorMS.py
INTERNAL_DEPENDENCIES: microservice_std_lib
EXTERNAL_DEPENDENCIES: beautifulsoup4, bs4, pypdf
"""
import io
import re
import time
from typing import Dict, Any, Optional
from microservice_std_lib import service_metadata, service_endpoint

@service_metadata(name='ContentExtractorMS', version='1.0.0', description='The Decoder: A specialist service for extracting clean text from complex formats like PDF and HTML.', tags=['utility', 'extraction', 'nlp'], capabilities=['pdf-to-text', 'html-cleaning'], side_effects=['filesystem:read'], internal_dependencies=['microservice_std_lib'], external_dependencies=['beautifulsoup4', 'bs4', 'pypdf'])
class ContentExtractorMS:
    """
    The Decoder.
    A standalone utility microservice that separates the concern of 
    document parsing from ingestion logic.
    """

    def __init__(self):
        self.start_time = time.time()
        self._pdf_ready = False
        try:
            from pypdf import PdfReader
            self._pdf_ready = True
        except ImportError:
            pass
        self._html_ready = False
        try:
            from bs4 import BeautifulSoup
            self._html_ready = True
        except ImportError:
            pass

    @service_endpoint(inputs={}, outputs={'status': 'str', 'pdf_support': 'bool', 'html_support': 'bool'}, description='Health check to verify which extraction backends are installed.', tags=['diagnostic', 'health'])
    def get_health(self) -> Dict[str, Any]:
        """Returns the operational status and library availability."""
        return {'status': 'online', 'uptime': time.time() - self.start_time, 'pdf_support': self._pdf_ready, 'html_support': self._html_ready}

    @service_endpoint(inputs={'blob': 'bytes', 'mime_type': 'str'}, outputs={'text': 'str'}, description='Unified entry point for text extraction. Routes to the correct parser based on mime_type.', tags=['processing', 'extraction'])
    def extract_text(self, blob: bytes, mime_type: str) -> str:
        """
        Main routing logic for extraction. 
         logic is internalized here.
        """
        if 'pdf' in mime_type.lower():
            return self._extract_pdf(blob)
        elif 'html' in mime_type.lower():
            try:
                html_content = blob.decode('utf-8', errors='ignore')
                return self._extract_html(html_content)
            except:
                return ''
        return ''

    def _extract_pdf(self, file_bytes: bytes) -> str:
        """Extracts text from a PDF blob using pypdf. [cite: 96-97]"""
        if not self._pdf_ready:
            return ''
        from pypdf import PdfReader
        text_content = []
        try:
            stream = io.BytesIO(file_bytes)
            reader = PdfReader(stream)
            for page in reader.pages:
                extracted = page.extract_text()
                if extracted:
                    text_content.append(extracted)
            return '\n'.join(text_content)
        except Exception as e:
            return f'PDF Extraction Error: {e}'

    def _extract_html(self, html_content: str) -> str:
        """Cleans HTML to raw text using BeautifulSoup. [cite: 98-99]"""
        if not self._html_ready:
            return self._strip_tags_regex(html_content)
        from bs4 import BeautifulSoup
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            for script in soup(['script', 'style', 'meta', 'noscript']):
                script.decompose()
            text = soup.get_text()
            lines = (line.strip() for line in text.splitlines())
            chunks = (phrase.strip() for line in lines for phrase in line.split('  '))
            return '\n'.join((chunk for chunk in chunks if chunk))
        except Exception:
            return self._strip_tags_regex(html_content)

    def _strip_tags_regex(self, html: str) -> str:
        """Fallback if BS4 is missing. [cite: 100]"""
        clean = re.compile('<.*?>')
        return re.sub(clean, '', html)
if __name__ == '__main__':
    svc = ContentExtractorMS()
    print('Service ready:', svc._service_info['name'])
    print('Health:', svc.get_health())
