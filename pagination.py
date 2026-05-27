import re
import logging
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

NEXT_PAGE_PATTERNS = [
    "next", "下一页", "next page", "»", "›", ">>",
    "next →", "next ›", "下页"
]


def find_next_page_url(html_content, current_url):
    soup = BeautifulSoup(html_content, "html.parser")

    # Strategy 1: <a rel="next">
    link = soup.find("a", rel="next")
    if link and link.get("href"):
        return urljoin(current_url, link["href"])

    # Strategy 2: <a> or <li> with class containing "next"
    for selector in ["a.next", "li.next a", "a.pagination-next",
                     "[class*='next'] a", "a[class*='next']"]:
        link = soup.select_one(selector)
        if link and link.get("href"):
            return urljoin(current_url, link["href"])

    # Strategy 3: <a> with text matching next-page patterns
    all_links = soup.find_all("a", href=True)
    for a in all_links:
        text = a.get_text(strip=True).lower()
        if text in NEXT_PAGE_PATTERNS:
            return urljoin(current_url, a["href"])

    # Strategy 4: URL pattern ?page=N or /page/N/
    parsed = urlparse(current_url)
    page_match = re.search(r'[?&]page=(\d+)', parsed.query)
    if page_match:
        current_page = int(page_match.group(1))
        next_url = re.sub(
            r'([?&]page=)\d+',
            f'\\g<1>{current_page + 1}',
            current_url
        )
        return next_url

    path_match = re.search(r'/page[/-](\d+)', parsed.path)
    if path_match:
        current_page = int(path_match.group(1))
        next_url = re.sub(
            r'/page([/-])\d+',
            f'/page\\g<1>{current_page + 1}',
            current_url
        )
        return next_url

    return None
