#!/usr/bin/env python3
"""
Site indexer: Crawl sitemap and index content for entity matching.
Extracts text content and existing JSON-LD from site pages.
"""

import json
import re
import time
from dataclasses import dataclass, asdict
from typing import Optional, Generator
from pathlib import Path
from urllib.parse import urljoin, urlparse
import xml.etree.ElementTree as ET

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    requests = None
    BeautifulSoup = None


@dataclass
class IndexedPage:
    """Represents an indexed page from the site."""
    url: str
    title: str
    text: str
    json_ld: list
    meta_description: str = ""
    last_indexed: str = ""
    
    def to_dict(self):
        return asdict(self)


class SiteIndexer:
    """Index site content for entity matching."""
    
    def __init__(self, 
                 base_url: str,
                 cache_dir: Optional[Path] = None,
                 rate_limit: float = 1.0,
                 user_agent: str = "EntityValidator/1.0"):
        """
        Initialize indexer.
        
        Args:
            base_url: Site base URL
            cache_dir: Directory to cache indexed content
            rate_limit: Seconds between requests
            user_agent: User agent string
        """
        if requests is None or BeautifulSoup is None:
            raise ImportError("requests and beautifulsoup4 required. Install with: pip install requests beautifulsoup4")
        
        self.base_url = base_url.rstrip('/')
        self.cache_dir = cache_dir
        self.rate_limit = rate_limit
        self.session = requests.Session()
        self.session.headers['User-Agent'] = user_agent
        
        if cache_dir:
            cache_dir.mkdir(parents=True, exist_ok=True)
    
    def index_from_sitemap(self, sitemap_url: Optional[str] = None,
                          max_pages: int = 100) -> list[IndexedPage]:
        """
        Index pages from sitemap.
        
        Args:
            sitemap_url: Sitemap URL (default: {base_url}/sitemap.xml)
            max_pages: Maximum pages to index
            
        Returns:
            List of IndexedPage objects
        """
        sitemap_url = sitemap_url or f"{self.base_url}/sitemap.xml"
        
        urls = list(self._parse_sitemap(sitemap_url))[:max_pages]
        
        pages = []
        for i, url in enumerate(urls):
            print(f"Indexing {i+1}/{len(urls)}: {url}")
            
            try:
                page = self._index_page(url)
                if page:
                    pages.append(page)
            except Exception as e:
                print(f"  Error: {e}")
            
            if i < len(urls) - 1:
                time.sleep(self.rate_limit)
        
        return pages
    
    def index_urls(self, urls: list[str]) -> list[IndexedPage]:
        """Index specific URLs."""
        pages = []
        for i, url in enumerate(urls):
            print(f"Indexing {i+1}/{len(urls)}: {url}")
            
            try:
                page = self._index_page(url)
                if page:
                    pages.append(page)
            except Exception as e:
                print(f"  Error: {e}")
            
            if i < len(urls) - 1:
                time.sleep(self.rate_limit)
        
        return pages
    
    def _parse_sitemap(self, sitemap_url: str) -> Generator[str, None, None]:
        """Parse sitemap and yield URLs."""
        try:
            response = self.session.get(sitemap_url, timeout=30)
            response.raise_for_status()
        except Exception as e:
            print(f"Failed to fetch sitemap: {e}")
            return
        
        # Handle sitemap index
        if '<sitemapindex' in response.text:
            root = ET.fromstring(response.content)
            ns = {'sm': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
            
            for sitemap in root.findall('.//sm:sitemap/sm:loc', ns):
                yield from self._parse_sitemap(sitemap.text)
        else:
            root = ET.fromstring(response.content)
            ns = {'sm': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
            
            for url in root.findall('.//sm:url/sm:loc', ns):
                yield url.text
    
    def _index_page(self, url: str) -> Optional[IndexedPage]:
        """Index a single page."""
        # Check cache
        if self.cache_dir:
            cache_file = self._get_cache_path(url)
            if cache_file.exists():
                data = json.loads(cache_file.read_text())
                return IndexedPage(**data)
        
        # Fetch page
        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
        except Exception as e:
            print(f"  Failed to fetch: {e}")
            return None
        
        # Parse HTML
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Extract title
        title = ""
        title_tag = soup.find('title')
        if title_tag:
            title = title_tag.get_text(strip=True)
        
        # Extract meta description
        meta_desc = ""
        meta_tag = soup.find('meta', attrs={'name': 'description'})
        if meta_tag:
            meta_desc = meta_tag.get('content', '')
        
        # Extract text content
        text = self._extract_text(soup)
        
        # Extract JSON-LD
        json_ld = self._extract_json_ld(soup)
        
        # Create page object
        from datetime import datetime
        page = IndexedPage(
            url=url,
            title=title,
            text=text,
            json_ld=json_ld,
            meta_description=meta_desc,
            last_indexed=datetime.utcnow().isoformat(),
        )
        
        # Cache
        if self.cache_dir:
            cache_file = self._get_cache_path(url)
            cache_file.write_text(json.dumps(page.to_dict(), indent=2))
        
        return page
    
    def _extract_text(self, soup: BeautifulSoup) -> str:
        """Extract readable text from HTML."""
        # Remove script, style, nav, footer, etc.
        for tag in soup(['script', 'style', 'nav', 'footer', 'header', 
                         'aside', 'noscript', 'iframe']):
            tag.decompose()
        
        # Try to find main content
        main = soup.find('main') or soup.find('article') or soup.find('body')
        
        if main:
            text = main.get_text(separator=' ', strip=True)
        else:
            text = soup.get_text(separator=' ', strip=True)
        
        # Clean up whitespace
        text = re.sub(r'\s+', ' ', text)
        
        return text[:50000]  # Limit size
    
    def _extract_json_ld(self, soup: BeautifulSoup) -> list:
        """Extract JSON-LD schemas from page."""
        schemas = []
        
        for script in soup.find_all('script', type='application/ld+json'):
            try:
                data = json.loads(script.string)
                if isinstance(data, list):
                    schemas.extend(data)
                else:
                    schemas.append(data)
            except (json.JSONDecodeError, TypeError):
                continue
        
        return schemas
    
    def _get_cache_path(self, url: str) -> Path:
        """Get cache file path for URL."""
        parsed = urlparse(url)
        path = parsed.path.strip('/').replace('/', '_') or 'index'
        return self.cache_dir / f"{parsed.netloc}_{path}.json"
    
    def save_index(self, pages: list[IndexedPage], output_path: Path):
        """Save index to JSON file."""
        data = [p.to_dict() for p in pages]
        output_path.write_text(json.dumps(data, indent=2))
    
    def load_index(self, input_path: Path) -> list[IndexedPage]:
        """Load index from JSON file."""
        data = json.loads(input_path.read_text())
        return [IndexedPage(**p) for p in data]


def main():
    """CLI interface for site indexing."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Index site content')
    parser.add_argument('url', help='Base URL or sitemap URL')
    parser.add_argument('-o', '--output', required=True, help='Output JSON file')
    parser.add_argument('-c', '--cache', help='Cache directory')
    parser.add_argument('-m', '--max-pages', type=int, default=100,
                        help='Maximum pages to index')
    parser.add_argument('-r', '--rate-limit', type=float, default=1.0,
                        help='Seconds between requests')
    parser.add_argument('--urls-file', help='File with list of URLs to index')
    
    args = parser.parse_args()
    
    # Determine base URL
    if args.url.endswith('.xml'):
        sitemap_url = args.url
        parsed = urlparse(args.url)
        base_url = f"{parsed.scheme}://{parsed.netloc}"
    else:
        base_url = args.url
        sitemap_url = None
    
    cache_dir = Path(args.cache) if args.cache else None
    
    indexer = SiteIndexer(
        base_url=base_url,
        cache_dir=cache_dir,
        rate_limit=args.rate_limit,
    )
    
    if args.urls_file:
        urls = Path(args.urls_file).read_text().strip().split('\n')
        pages = indexer.index_urls(urls)
    else:
        pages = indexer.index_from_sitemap(sitemap_url, args.max_pages)
    
    indexer.save_index(pages, Path(args.output))
    print(f"\nIndexed {len(pages)} pages to {args.output}")


if __name__ == '__main__':
    main()
