import json
import csv
import re
import logging
import threading
from io import StringIO
from datetime import datetime
from urllib.parse import urljoin
from concurrent.futures import ThreadPoolExecutor, as_completed

from database import (
    update_job_status, update_job_category, add_result, update_result,
    store_extracted_rows, export_to_excel, get_job
)
from scraper import get_url_md, SeleniumSession, clean_markdown, clean_html, to_markdown, crawl4ai_scraper
from pagination import find_next_page_url
from generate_response import (
    generate_response, generate_response2, classify_website,
    generate_with_validation, adapt_fields_for_page
)
from categories import get_category_info

logger = logging.getLogger(__name__)

NEXT_KEYWORDS = ["next", "下一页", "next page", "»", "›", ">>", "next →", "next ›"]

# 并发与限流配置
DEFAULT_URL_WORKERS = 3      # 同时抓取的 URL 数（每个 URL 内部分页仍串行）
DEFAULT_LLM_CONCURRENCY = 2  # 同时调用 LLM 的最大数（避免 rate limit）
_LLM_SEMAPHORE = threading.Semaphore(DEFAULT_LLM_CONCURRENCY)
_DB_LOCK = threading.Lock()  # SQLite 写入串行化


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


def _fix_malformed_header(csv_text: str) -> str:
    """LLM 偶尔会把引号写错(比如 \"title,\"author\" 把第一个引号闭合到逗号后),
    导致 csv.DictReader 把多个字段合成一个 header。这里自动修复:
    - 检测第一行(表头)中含有逗号的字段名(明显异常)
    - 用启发式拆分:在每个字母后跟着 "," 的位置切开
    """
    if not csv_text:
        return csv_text

    lines = csv_text.splitlines()
    if not lines:
        return csv_text

    header = lines[0]
    # 把表头里所有引号去掉,然后重新按逗号切分,看字段名里是否含逗号(异常信号)
    import csv as _csv
    from io import StringIO
    try:
        parsed_header = next(_csv.reader(StringIO(header)))
    except Exception:
        return csv_text

    # 如果某个字段名里含逗号 → 表头损坏,需要修复
    if not any("," in h for h in parsed_header):
        return csv_text

    # 修复:去掉表头所有引号,按"非引号逗号"切分,每段两端补正确引号
    clean_header = header.replace('"', '').replace("'", '')
    fixed_fields = [f.strip() for f in clean_header.split(",") if f.strip()]
    if not fixed_fields:
        return csv_text
    new_header = ",".join(f'"{f}"' for f in fixed_fields)
    logger.info(f"Fixed malformed CSV header: {header[:100]} -> {new_header[:100]}")
    return new_header + "\n" + "\n".join(lines[1:])


def parse_csv_to_rows(csv_text):
    csv_text = _fix_malformed_header(csv_text)
    lines = [l.strip() for l in csv_text.splitlines() if l.strip()]
    if not lines:
        return []
    reader = csv.DictReader(StringIO(csv_text))
    rows = []
    for row in reader:
        # csv.DictReader 把多余列放在 row[None] = list,要清理掉避免下游 .strip() 崩
        # 把多余字段合并回最后一个表头列
        extras = row.pop(None, None)
        if extras and row:
            last_key = list(row.keys())[-1]
            tail = ",".join(str(x) for x in extras if x)
            row[last_key] = f"{row[last_key]},{tail}" if row.get(last_key) else tail
        # 过滤掉所有非字符串值,确保下游 .strip() 安全
        clean_row = {}
        for k, v in row.items():
            if k is None:
                continue
            if isinstance(v, list):
                v = ",".join(str(x) for x in v if x)
            elif v is None:
                v = ""
            else:
                v = str(v)
            clean_row[k] = v
        rows.append(clean_row)
    return rows


def _safe_str(v) -> str:
    """安全地把任意值转成 string,处理 list/None/数字等异常情况"""
    if v is None:
        return ""
    if isinstance(v, list):
        return ",".join(str(x) for x in v if x)
    if not isinstance(v, str):
        return str(v)
    return v


def repair_csv_rows(rows, header_fields):
    """Post-process CSV rows to fix common LLM extraction issues."""
    if not rows or not header_fields:
        return rows

    repaired = []
    for row in rows:
        # Skip completely empty rows
        if all(not _safe_str(v).strip() for v in row.values()):
            continue

        fields = list(row.keys())
        if len(fields) >= 2:
            last_field = fields[-1]
            first_field = fields[0]
            first_val = _safe_str(row.get(first_field)).strip()
            last_val = _safe_str(row.get(last_field)).strip()

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
            val = _safe_str(row.get(field))
            val = val.replace('\\', '').strip()
            val = re.sub(r'^["\x27]+|["\x27]+$', '', val)
            row[field] = val.strip()

        repaired.append(row)

    return repaired

def _row_signature(row):
    """生成行指纹用于去重。优先使用第一个非空字段作为主键,完全相同的行视为重复。"""
    if not row:
        return None
    # 用所有字段的 JSON 序列化作为完整指纹
    return json.dumps(row, sort_keys=True, ensure_ascii=False)


def _row_primary_signature(row):
    """更宽松的去重指纹: 只看前两个字段 (通常是主键如 title + author)。
    用于检测 LLM 循环输出 (整行一字不差地重复)。"""
    if not row:
        return None
    keys = list(row.keys())[:2]
    parts = []
    for k in keys:
        v = (row.get(k) or "").strip().lower()
        parts.append(v)
    sig = "|".join(parts)
    # 全空或全 N/A 不视为有效指纹
    if not sig.replace("|", "").replace("n/a", "").strip():
        return None
    return sig


def deduplicate_within_batch(rows):
    """在同一批 LLM 输出内去重 (防止 LLM 循环输出 / 重复输出)。"""
    if not rows:
        return rows

    seen_full = set()
    seen_primary = set()
    unique = []
    dropped_full = 0
    dropped_primary = 0

    for row in rows:
        full_sig = _row_signature(row)
        primary_sig = _row_primary_signature(row)

        # 完全相同 -> 丢
        if full_sig in seen_full:
            dropped_full += 1
            continue
        # 主键相同(即使其他字段略有差异)也丢
        if primary_sig and primary_sig in seen_primary:
            dropped_primary += 1
            continue

        seen_full.add(full_sig)
        if primary_sig:
            seen_primary.add(primary_sig)
        unique.append(row)

    if dropped_full or dropped_primary:
        logger.info(
            f"In-batch dedup: {len(rows)} -> {len(unique)} rows "
            f"(removed {dropped_full} exact dups, {dropped_primary} primary-key dups)"
        )
    return unique


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

    # 登录态: cookies 字符串放在 pipeline_config.cookies
    config = json.loads(job.get("pipeline_config") or "{}")
    cookies = config.get("cookies") or None
    cookie_domain = config.get("cookie_domain") or None
    if cookies:
        # 有 cookies 时强制走 Selenium(Crawl4AI 不支持注入 cookie)
        if method != "Selenium":
            logger.info(f"Cookies provided, switching method to Selenium for {url}")
        method = "Selenium"

    pages = []

    if not follow_pagination:
        if method == "Selenium" and cookies:
            with SeleniumSession(cookies=cookies, cookie_domain=cookie_domain) as session:
                md, _ = session.scrape_to_markdown(url)
        else:
            md = get_url_md(url, method)
        pages.append({"url": url, "page_number": 1, "markdown": md, "html": None})
        return pages

    if method == "Selenium":
        with SeleniumSession(cookies=cookies, cookie_domain=cookie_domain) as session:
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
    """LLM 提取,带校验+重试,信号量限流。"""
    llm_provider = job.get("llm_provider", "Ollama")
    llm_model = job.get("llm_model", "")
    config = json.loads(job.get("pipeline_config") or "{}")
    max_retries = config.get("llm_max_retries", 2)

    with _LLM_SEMAPHORE:
        return generate_with_validation(
            query=query,
            scraped_data=cleaned_md,
            llm_provider=llm_provider,
            llm_model=llm_model,
            max_retries=max_retries,
        )


def stage_store(job_id, result_id, csv_text, category=None):
    rows = parse_csv_to_rows(csv_text)
    if not rows:
        return 0

    # Repair common LLM extraction issues
    header_fields = list(rows[0].keys()) if rows else []
    rows = repair_csv_rows(rows, header_fields)

    # Stage 4a: 同批次内去重 (防 LLM 循环输出)
    rows = deduplicate_within_batch(rows)

    # Stage 4b: 跨任务去重 (DB read+write under lock)
    with _DB_LOCK:
        rows = deduplicate_rows(job_id, rows)
        if not rows:
            return 0
        # 返回真实入库数(可能因为字段缺失被 store 内部跳过,小于 len(rows))
        actual_inserted = store_extracted_rows(job_id, result_id, rows, category=category)
    if actual_inserted < len(rows):
        logger.warning(
            f"Job {job_id} result {result_id}: store dropped {len(rows) - actual_inserted}/{len(rows)} rows "
            f"(category={category}); often means LLM CSV missing required fields like 'title'"
        )
    return actual_inserted


def _process_single_url(url, job, smart_mode, llm_provider, llm_model, default_query):
    """处理单个 URL 的完整流水线(可并发执行的最小单元)。返回该 URL 抓到的行数。"""
    job_id = job["id"]
    rows_count = 0

    # Stage 1: Scrape (可能是多页)
    try:
        pages = stage_scrape(url, job)
    except Exception as e:
        logger.error(f"[URL {url}] stage_scrape failed: {e}")
        return 0

    # Smart mode 分类只在该 URL 范围内做一次
    url_query = default_query
    detected_category: str | None = None
    if smart_mode and pages:
        first_md = next(
            (p["markdown"] for p in pages if p.get("markdown") and len(p["markdown"]) > 100),
            pages[0].get("markdown", "")
        )
        try:
            with _LLM_SEMAPHORE:
                category, default_fields = classify_website(
                    first_md, llm_provider=llm_provider, llm_model=llm_model
                )
            detected_category = category
            cat_info = get_category_info(category)
            url_query = default_fields

            # 仅在兜底类别或字段数过少时才尝试自适应,避免破坏已设计好的模板
            ADAPT_CATEGORIES = {"general", "forum"}
            if category in ADAPT_CATEGORIES or len(default_fields.split(",")) < 3:
                with _LLM_SEMAPHORE:
                    adapted = adapt_fields_for_page(
                        first_md, category, default_fields,
                        llm_provider=llm_provider, llm_model=llm_model
                    )
                url_query = adapted

            # 把分类结果写回 jobs.category_id (只写一次)
            try:
                with _DB_LOCK:
                    update_job_category(job_id, category)
            except Exception as e:
                logger.warning(f"[URL {url}] failed to update job category: {e}")

            logger.info(
                f"[URL {url}] classified as [{category} / {cat_info['name_zh']}], "
                f"final fields: {url_query}"
            )
        except Exception as e:
            logger.warning(f"[URL {url}] smart classify failed: {e}, fallback to general")
            url_query = "title, description, url, date"

    consecutive_empty = 0
    for page in pages:
        with _DB_LOCK:
            result_id = add_result(job_id, page["url"], page["page_number"])

        try:
            md = page["markdown"]

            # 抓取阶段就失败的页面不要送 LLM
            if not md or md.startswith("Error") or "Selenium failed" in md or len(md.strip()) < 50:
                err = (md[:200] if md else "empty markdown")
                logger.warning(f"[URL {url}] page {page['page_number']} scrape failed/empty: {err}")
                with _DB_LOCK:
                    update_result(result_id, status="failed", error_message=f"scrape failed: {err}")
                consecutive_empty += 1
                if consecutive_empty >= 2:
                    break
                continue

            with _DB_LOCK:
                update_result(result_id, status="scraped", raw_markdown=md[:5000])

            cleaned = stage_clean(md, job)
            csv_text = stage_extract(cleaned, url_query, job)

            with _DB_LOCK:
                update_result(result_id, status="extracted", extracted_csv=csv_text)

            row_count = stage_store(job_id, result_id, csv_text, category=detected_category)
            rows_count += row_count

            with _DB_LOCK:
                update_result(result_id, status="stored", row_count=row_count)

            if row_count == 0:
                consecutive_empty += 1
                logger.warning(
                    f"[URL {url}] page {page['page_number']} yielded 0 rows "
                    f"(consecutive: {consecutive_empty})"
                )
                if consecutive_empty >= 2:
                    logger.info(f"[URL {url}] 2 consecutive empty pages, stopping")
                    break
            else:
                consecutive_empty = 0

        except Exception as e:
            logger.error(f"[URL {url}] page {page['page_number']} failed: {e}")
            with _DB_LOCK:
                update_result(result_id, status="failed", error_message=str(e))

    return rows_count


def execute_pipeline(job):
    job_id = job["id"]
    query = job["query"]
    urls = json.loads(job["urls"]) if isinstance(job["urls"], str) else job["urls"]

    config = json.loads(job.get("pipeline_config") or "{}")
    smart_mode = config.get("smart_mode", False)
    llm_provider = job.get("llm_provider", "Ollama")
    llm_model = job.get("llm_model", "")
    url_workers = config.get("url_workers", DEFAULT_URL_WORKERS)
    # 限制并发数不超过 URL 数,且不小于 1
    url_workers = max(1, min(url_workers, len(urls))) if urls else 1

    update_job_status(job_id, "running")
    total_rows = 0

    try:
        if url_workers <= 1 or len(urls) <= 1:
            # 串行模式(单 URL 或显式禁用并发)
            for url in urls:
                total_rows += _process_single_url(
                    url, job, smart_mode, llm_provider, llm_model, query
                )
        else:
            logger.info(f"Job {job_id}: processing {len(urls)} URLs with {url_workers} workers")
            with ThreadPoolExecutor(max_workers=url_workers) as executor:
                futures = {
                    executor.submit(
                        _process_single_url,
                        url, job, smart_mode, llm_provider, llm_model, query
                    ): url
                    for url in urls
                }
                for future in as_completed(futures):
                    url = futures[future]
                    try:
                        total_rows += future.result()
                    except Exception as e:
                        logger.error(f"[URL {url}] worker exception: {e}")

        # Stage 5: Export Excel if configured
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
