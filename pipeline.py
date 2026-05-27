import json
import csv
import re
import logging
from io import StringIO
from datetime import datetime
from urllib.parse import urljoin

from database import (
    update_job_status, add_result, update_result,
    store_extracted_rows, export_to_excel, get_job
)
from scraper import get_url_md, SeleniumSession, clean_markdown, clean_html, to_markdown, crawl4ai_scraper
from pagination import find_next_page_url
from generate_response import generate_response, generate_response2

logger = logging.getLogger(__name__)

NEXT_KEYWORDS = ["next", "下一页", "next page", "»", "›", ">>", "next →", "next ›"]


def find_next_page_in_markdown(md_content, current_url):
    """Find next page URL from markdown content (looks for [Next](/page/2/) style links)."""
    links = re.findall(r'\[([^\]]*)\]\(([^)]+)\)', md_content)
    for text, href in links:
        text_lower = text.strip().lower()
        if text_lower in NEXT_KEYWORDS or "next" in text_lower:
            logger.info(f"Found next page link: [{text}]({href})")
            return urljoin(current_url, href)

    # Fallback: look for bare URLs with /page/ pattern
    page_urls = re.findall(r'(https?://[^\s)]+/page[/-]\d+[^\s)]*)', md_content)
    if page_urls:
        return page_urls[-1]

    # Fallback: URL pattern detection from pagination module
    from pagination import find_next_page_url
    next_from_html = find_next_page_url(md_content, current_url)
    if next_from_html:
        return next_from_html

    # Final fallback: URL pattern increment for common pagination schemes
    page_match = re.search(r'/page/(\d+)/?', current_url)
    if page_match:
        current_page = int(page_match.group(1))
        next_page_url = re.sub(r'/page/\d+/?', f'/page/{current_page + 1}/', current_url)
        logger.info(f"URL pattern fallback: {next_page_url}")
        return next_page_url

    # If first page (no /page/ in URL) and content hints at pagination
    if '/page/' not in current_url:
        if any(kw in md_content.lower() for kw in ['next', 'page 2', '/page/', '下一页']):
            base = current_url.rstrip('/')
            next_url = f"{base}/page/2/"
            logger.info(f"First-page fallback: {next_url}")
            return next_url

    return None


def parse_csv_to_rows(csv_text):
    lines = [l.strip() for l in csv_text.splitlines() if l.strip()]
    if not lines:
        return []
    reader = csv.DictReader(StringIO(csv_text))
    return [row for row in reader]


def repair_csv_rows(rows, header_fields):
    """Post-process CSV rows to fix common LLM extraction issues."""
    if not rows or not header_fields:
        return rows

    repaired = []
    for row in rows:
        # Skip completely empty rows
        if all(not v or not v.strip() for v in row.values()):
            continue

        fields = list(row.keys())
        if len(fields) >= 2:
            last_field = fields[-1]
            first_field = fields[0]
            first_val = (row.get(first_field) or "").strip()
            last_val = (row.get(last_field) or "").strip()

            # Fix: quote contains "by Author Name" at end while author column also has the name
            if last_val and first_val:
                # Remove trailing "by Author" from first field if author matches
                pattern = re.compile(
                    r'\s*\.?\s*by\s+' + re.escape(last_val) + r'\s*$',
                    re.IGNORECASE
                )
                cleaned = pattern.sub('', first_val)
                if cleaned != first_val:
                    row[first_field] = cleaned.rstrip(' .')

            # Fix: if last column is empty but its value is appended to first column
            if (not last_val) and first_val:
                val = first_val.rstrip('"').rstrip("'")
                match = re.search(r'[.!?“”]\s+([A-Z][a-z]+(?:\s+[A-Z]\.?)?(?:\s+[A-Z][a-z]+)*)\s*$', val)
                if match:
                    author = match.group(1).strip()
                    quote = val[:match.start(1)].rstrip().rstrip('.').rstrip()
                    row[first_field] = quote
                    row[last_field] = author

        # Clean up stray escape characters and extra quotes
        for field in fields:
            val = row.get(field) or ""
            val = val.replace('\\', '').strip()
            val = re.sub(r'^["\x27]+|["\x27]+$', '', val)
            row[field] = val.strip()

        repaired.append(row)

    return repaired

def deduplicate_rows(job_id, new_rows):
    """Remove rows that already exist in the database for this job."""
    from database import get_job_data
    existing_data = get_job_data(job_id)
    if not existing_data:
        return new_rows

    existing_set = set()
    for row in existing_data:
        key = json.dumps(row, sort_keys=True, ensure_ascii=False)
        existing_set.add(key)

    unique_rows = []
    for row in new_rows:
        key = json.dumps(row, sort_keys=True, ensure_ascii=False)
        if key not in existing_set:
            unique_rows.append(row)
            existing_set.add(key)

    if len(new_rows) != len(unique_rows):
        logger.info(f"Dedup: {len(new_rows)} -> {len(unique_rows)} rows (removed {len(new_rows) - len(unique_rows)} duplicates)")

    return unique_rows


def stage_scrape(url, job):
    method = job.get("method", "Crawl4AI")
    follow_pagination = job.get("follow_pagination", 0)
    max_pages = job.get("max_pages", 5)

    pages = []

    if not follow_pagination:
        md = get_url_md(url, method)
        pages.append({"url": url, "page_number": 1, "markdown": md, "html": None})
        return pages

    if method == "Selenium":
        with SeleniumSession() as session:
            current_url = url
            for page_num in range(1, max_pages + 1):
                logger.info(f"Scraping page {page_num}: {current_url}")
                md, html = session.scrape_to_markdown(current_url)
                pages.append({
                    "url": current_url,
                    "page_number": page_num,
                    "markdown": md,
                    "html": html
                })
                if len(md.strip()) < 100:
                    logger.info(f"Page {page_num} content too short, stopping pagination")
                    break
                next_url = find_next_page_url(html, current_url)
                if not next_url or next_url == current_url:
                    break
                current_url = next_url
    else:
        current_url = url
        for page_num in range(1, max_pages + 1):
            logger.info(f"Scraping page {page_num}: {current_url}")

            # Get RAW markdown for pagination detection (links preserved)
            raw_md = crawl4ai_scraper(current_url, raw=True)
            if not raw_md or raw_md.startswith("Error"):
                logger.warning(f"Crawl4AI failed for {current_url}, falling back to Selenium")
                from scraper import selenium_scraper
                md = selenium_scraper(current_url)
                raw_md = md
            else:
                md = clean_markdown(raw_md)

            pages.append({
                "url": current_url,
                "page_number": page_num,
                "markdown": md,
                "html": None
            })
            if md.startswith("Error"):
                break

            # Empty page detection: if content is too short, likely a 404 or empty page
            if len(md.strip()) < 100:
                logger.info(f"Page {page_num} content too short ({len(md.strip())} chars), stopping pagination")
                break

            # Detect next page from RAW markdown (before clean strips links)
            next_url = find_next_page_in_markdown(raw_md, current_url)
            logger.info(f"Page {page_num} next_url detected: {next_url}")
            if not next_url or next_url == current_url:
                break
            current_url = next_url

    return pages


def stage_clean(markdown, job):
    config = json.loads(job.get("pipeline_config") or "{}")
    clean_config = config.get("clean", {})
    remove_links = clean_config.get("remove_links", False)
    return clean_markdown(markdown, remove_links=remove_links)


def stage_extract(cleaned_md, query, job):
    llm_provider = job.get("llm_provider", "Ollama")
    llm_model = job.get("llm_model", "")

    if llm_provider == "Ollama":
        return generate_response(llm_model, query, cleaned_md)
    else:
        return generate_response2(query, cleaned_md, llm_model)


def stage_store(job_id, result_id, csv_text):
    rows = parse_csv_to_rows(csv_text)
    if not rows:
        return 0

    # Repair common LLM extraction issues
    header_fields = list(rows[0].keys()) if rows else []
    rows = repair_csv_rows(rows, header_fields)

    # Deduplicate against existing data for this job
    rows = deduplicate_rows(job_id, rows)

    if rows:
        store_extracted_rows(job_id, result_id, rows)
    return len(rows)


def execute_pipeline(job):
    job_id = job["id"]
    query = job["query"]
    urls = json.loads(job["urls"]) if isinstance(job["urls"], str) else job["urls"]

    update_job_status(job_id, "running")
    total_rows = 0

    try:
        for url in urls:
            # Stage 1: Scrape
            pages = stage_scrape(url, job)

            consecutive_empty = 0
            for page in pages:
                result_id = add_result(job_id, page["url"], page["page_number"])

                try:
                    # Stage 2: Clean
                    update_result(result_id, status="scraped", raw_markdown=page["markdown"][:5000])
                    cleaned = stage_clean(page["markdown"], job)

                    # Stage 3: Extract
                    csv_text = stage_extract(cleaned, query, job)
                    import re
                    csv_text = re.sub(r"^.*?</think>", "", csv_text, flags=re.DOTALL).strip()
                    csv_text = re.sub(r'```(?:csv|CSV)?\s*\n?', '', csv_text)
                    csv_text = re.sub(r'```\s*$', '', csv_text, flags=re.MULTILINE)
                    update_result(result_id, status="extracted", extracted_csv=csv_text)

                    # Stage 4: Store
                    row_count = stage_store(job_id, result_id, csv_text)
                    total_rows += row_count
                    update_result(result_id, status="stored", row_count=row_count)

                    # Stop pagination if page yields no data
                    if row_count == 0:
                        consecutive_empty += 1
                        logger.warning(f"Page {page['page_number']} yielded 0 rows (consecutive: {consecutive_empty})")
                        if consecutive_empty >= 2:
                            logger.info("2 consecutive empty pages, stopping extraction for this URL")
                            break
                    else:
                        consecutive_empty = 0

                except Exception as e:
                    logger.error(f"Error processing {page['url']} page {page['page_number']}: {e}")
                    update_result(result_id, status="failed", error_message=str(e))

        # Stage 5: Export Excel if configured
        config = json.loads(job.get("pipeline_config") or "{}")
        if config.get("store", {}).get("export_excel", False):
            import os
            export_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "exports")
            os.makedirs(export_dir, exist_ok=True)
            filepath = os.path.join(export_dir, f"job_{job_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx")
            export_to_excel(job_id, filepath)
            logger.info(f"Exported to {filepath}")

        update_job_status(job_id, "completed")
        logger.info(f"Job {job_id} completed. Total rows: {total_rows}")

    except Exception as e:
        logger.error(f"Job {job_id} failed: {e}")
        update_job_status(job_id, "failed", error=str(e))
