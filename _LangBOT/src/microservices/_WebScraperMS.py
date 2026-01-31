import importlib.util
import sys
import httpx
import logging
import asyncio
import re
from typing import Optional, Dict, Any
REQUIRED = ['httpx', 'readability-lxml']
MISSING = []
for lib in REQUIRED:
    clean_lib = lib.split('>=')[0].replace('-', '_')
    if clean_lib == 'readability_lxml':
        clean_lib = 'readability'
    if importlib.util.find_spec(clean_lib) is None:
        MISSING.append(lib)
if MISSING:
    print('\n' + '!' * 60)
    print(f'MISSING DEPENDENCIES for _WebScraperMS:')
    print(f"Run:  pip install {' '.join(MISSING)}")
    print('!' * 60 + '\n')
try:
    from readability import Document
except ImportError:
    Document = None
from src.microservices.microservice_std_lib import service_metadata, service_endpoint
from src.microservices.base_service import BaseService

DEFAULT_MEMORY_FILE = Path('working_memory.jsonl')
USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
TIMEOUT_SECONDS = 15.0
logger = logging.getLogger('WebScraper')

@service_metadata(name='WebScraper', version='1.0.0', description='Fetches URLs and extracts main content using Readability (stripping ads/nav).', tags=['scraper', 'web', 'readability'], capabilities=['network:outbound', 'compute'], internal_dependencies=['microservice_std_lib'], external_dependencies=['httpx', 'readability'])
class WebScraperMS:
    """
    The Reader: Fetches URLs and extracts the main content using Readability.
    Strips ads, navbars, and boilerplate to return clean text for LLMs.
    """

    def __init__(self, config: Optional[Dict[str, Any]]=None):
        self.config = config or {}
        self.headers = {'User-Agent': USER_AGENT}

    @service_endpoint(inputs={'url': 'str'}, outputs={'data': 'Dict[str, Any]'}, description='Fetches and cleans a URL.', tags=['scraper', 'read'], side_effects=['network:outbound'])
    def scrape(self, url: str) -> Dict[str, Any]:
        """
        Synchronous wrapper for fetching and cleaning a URL.
        Returns: {
            "url": str,
            "title": str,
            "content": str (The main body text),
            "html": str (The raw HTML of the main content area)
        }
        """
        return asyncio.run(self._scrape_async(url))

    async def _scrape_async(self, url: str) -> Dict[str, Any]:
        if Document is None:
            raise ImportError('readability-lxml is missing.')
        logger.info(f'Fetching: {url}')
        async with httpx.AsyncClient(headers=self.headers, follow_redirects=True, timeout=TIMEOUT_SECONDS) as client:
            try:
                response = await client.get(url)
                response.raise_for_status()
            except httpx.HTTPStatusError as e:
                logger.error(f'HTTP Error {e.response.status_code}: {e}')
                raise
            except httpx.RequestError as e:
                logger.error(f'Request failed: {e}')
                raise
        try:
            doc = Document(response.text)
            title = doc.title()
            clean_html = doc.summary()
            clean_text = self._strip_tags(clean_html)
            logger.info(f"Successfully scraped '{title}' ({len(clean_text)} chars)")
            return {'url': url, 'title': title, 'content': clean_text, 'html': clean_html}
        except Exception as e:
            logger.error(f'Parsing failed: {e}')
            raise

    def _strip_tags(self, html: str) -> str:
        """
        Removes HTML tags to leave only the readable text.
        """
        html = re.sub('<(script|style).*?>.*?</\\1>', '', html, flags=re.DOTALL)
        text = re.sub('<[^>]+>', ' ', html)
        text = re.sub('\\s+', ' ', text).strip()
        return text
if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
    scraper = WebScraperMS()
    print('Service ready:', scraper)
    target_url = 'https://peps.python.org/pep-0008/'
    print(f'--- Scraping {target_url} ---')
    try:
        data = scraper.scrape(target_url)
        print(f"\nTitle: {data['title']}")
        print(f"Content Preview:\n{data['content'][:500]}...")
        print(f"\nTotal Length: {len(data['content'])} characters")
    except Exception as e:
        print(f'Scrape failed: {e}')
