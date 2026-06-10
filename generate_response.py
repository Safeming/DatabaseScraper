import os
import re
import csv
import ollama
import logging
import tiktoken
from io import StringIO
from sambanova import SambaNova

from scraper import clean_markdown
from categories import CATEGORY_TEMPLATES, list_category_keys, get_category_info

from dotenv import load_dotenv
load_dotenv()

API_KEY = os.getenv('API_KEY')

logger = logging.getLogger(__name__)

_client = None

def get_sambanova_client():
    global _client
    if _client is None:
        _client = SambaNova(
            api_key=API_KEY,
            base_url="https://api.sambanova.ai/v1",
        )
    return _client

def format_time(response_time):
    minutes = response_time // 60
    seconds = response_time % 60
    return f"{int(minutes)}m {int(seconds)}s" if minutes else f"Time: {int(seconds)}s"


def trim_to_token_limit(text, model, max_tokens=40000):
    encoder = tiktoken.encoding_for_model(model)
    tokens = encoder.encode(text)
    if len(tokens) > max_tokens:
        trimmed_text = encoder.decode(tokens[:max_tokens])
        return trimmed_text
    return text


def get_prompt(query, scraped_data) :
    prompt = f"""You are a precise data extraction engine. Extract EVERY matching item from the scraped data into CSV format.

### Scraped Data:
'''
{scraped_data}
'''

### Fields to extract:
"{query}"

### Rules (STRICT):
1. Output ONLY valid CSV. No explanation, no preamble, no markdown, no code blocks.
2. First line = header row. Use EXACTLY the field names from "Fields to extract" above (in the same order).
3. Every data row MUST have the SAME number of columns as the header.
4. Each column contains ONLY its own value — never merge multiple fields into one cell.
5. If a value contains a comma, wrap the entire value in double quotes.
6. If a value contains a double quote, escape it as "".
7. If a field's value is genuinely missing for an item, write "N/A" (not empty, not None, not null).
8. NEVER skip an item just because some fields are missing — fill missing ones with N/A and KEEP the row.
9. Extract EVERY visible item from the source. If you see 30 items, output 30 rows. Do NOT stop early.
10. Do NOT invent or hallucinate data. Only extract what is actually in the source.
11. Do NOT summarize, paraphrase, or reword — copy values verbatim from the source.
12. Process items in the order they appear in the source.

### Anti-patterns (do NOT do these):
- ❌ Stuffing all info into the first column when other columns "don't fit"
- ❌ Outputting only the first 5-10 items and stopping
- ❌ Leaving cells empty (use "N/A" instead)
- ❌ Adding any text before or after the CSV (no "Here is the CSV:", no "```csv")
- ❌ REPEATING items: each row must be UNIQUE. If you finish all items, STOP — do NOT loop back and output them again.
- ❌ Outputting an item twice with slight wording differences. Each unique source item appears EXACTLY ONCE.

### Example (for fields: quote, author):
quote,author
"The world is a book, and those who do not travel read only one page.",Saint Augustine
Life is short. Smile while you still have teeth.,Unknown
Some quote without known source,N/A

### CSV Output:
"""

    print('prompt : ', prompt[:200], '...')
    return prompt

# - If the required information is missing, output: "The provided context does not contain enough information."  

def generate_response(ollama_model, query, scraped_data):
    """Generates a response using scraped data and an LLM."""

    logger.info(f"Generate Response from Ollama LLM: {ollama_model}")

    prompt = get_prompt(query, scraped_data)

    try:
      response = ollama.chat(
        model=ollama_model,
        messages=[{"role": "user", "content": prompt}],
        options={"num_predict": 16384, "temperature": 0.0}
      )
      return response.get("message", {}).get("content", "")
    except Exception as e:
      logger.error(f"Ollama error: {e}")
      raise RuntimeError(f"Failed to generate response using Ollama: {e}")


def generate_response2(query, scraped_data, llm_name='QwQ-32B', retry=2):

    logger.info(f"Generate Response from Sambanova LLM: {llm_name}")

    if not API_KEY or API_KEY == "placeholder":
        raise RuntimeError("Sambanova API_KEY not configured. Set it in .env file.")

    prompt = get_prompt(query, scraped_data)
    client = get_sambanova_client()

    response = client.chat.completions.create(
        model=llm_name,
        messages=[
          {
            "role": "user",
            "content": prompt
          }
        ],
        temperature=0.1,
        top_p=0.1,
        timeout=120
    )

    # print(f'Response: {response}')

    if hasattr(response, "error"):
      error_message = response.error.get("message", "Unknown error")
      logger.error(f"Sambanova API error: {error_message}")

      if "maximum context length" in error_message.lower() and retry != 0:
        logger.warning("Token limit exceeded, retrying with reduced content...")

        if retry == 2:
          cleaned_scraped_data = clean_markdown(scraped_data, remove_links=True)
          return generate_response2(query, cleaned_scraped_data, llm_name, retry=1)

        elif retry == 1:
          cleaned_scraped_data = trim_to_token_limit(scraped_data, "gpt-4o", max_tokens=35000)
          return generate_response2(query, cleaned_scraped_data, llm_name, retry=0)

      raise RuntimeError(f"API Error: {error_message}")

    return response.choices[0].message.content


# ─── 网站智能分类 ───

def get_classify_prompt(scraped_sample):
    """构造分类提示词。让 LLM 根据网页摘要返回类别 key。"""
    categories_desc = "\n".join([
        f"- {key}: {val['name_zh']} - {val['description']}"
        for key, val in CATEGORY_TEMPLATES.items()
    ])

    prompt = f"""You are a website classifier. Analyze the webpage content and classify it into ONE of the predefined categories.

### Available categories:
{categories_desc}

### Webpage content sample:
'''
{scraped_sample}
'''

### Classification hints (use these signals):
- "points by USER N hours/days ago | hide | NN comments" pattern → "forum" (Hacker News style)
- "X upvotes / X comments / posted by u/USER" → "forum" (Reddit style)
- "X 个回复" / "回复" / 主题列表 → "forum" (V2EX/Discuz style)
- "Quote ... by Author" 引用块结构 → "quotes"
- "Add to basket" / "£/¥/$ price" / "Availability: In stock" → "books" or "products"
- 大量 article + publish date + author with full content → "news"
- 招聘岗位 + 薪资 + 公司 → "jobs"

### Rules:
1. Output ONLY the category key (e.g. "books", "news", "forum"), nothing else.
2. No explanation, no markdown, no quotes.
3. If uncertain or no good match, output "general".
4. The output must be one of: {", ".join(list_category_keys())}

### Category:"""
    return prompt


def _parse_category(raw_response):
    """从 LLM 输出中解析出类别 key,容错处理。"""
    if not raw_response:
        return "general"

    # 移除 think 标签内容
    import re
    text = re.sub(r"^.*?</think>", "", raw_response, flags=re.DOTALL).strip()

    # 取第一个有效行的第一个单词
    first_word = text.strip().split()[0] if text.strip() else ""
    first_word = first_word.strip('"').strip("'").strip(".").strip(":").lower()

    valid_keys = list_category_keys()
    if first_word in valid_keys:
        return first_word

    # 兜底:遍历整段文本找匹配的 key
    text_lower = text.lower()
    for key in valid_keys:
        if key in text_lower:
            return key

    return "general"


def classify_website(scraped_data, llm_provider="Ollama", llm_model=None,
                     sample_chars=2000):
    """
    根据网页内容自动识别网站类别。

    :param scraped_data: 抓取的网页 markdown 内容
    :param llm_provider: "Ollama" 或 "Sambanova"
    :param llm_model: 模型名
    :param sample_chars: 喂给 LLM 的内容字符数(避免过长)
    :return: (category_key, default_fields)
    """
    sample = scraped_data[:sample_chars] if scraped_data else ""
    if not sample.strip():
        logger.warning("No content to classify, returning general")
        return "general", CATEGORY_TEMPLATES["general"]["fields"]

    prompt = get_classify_prompt(sample)
    logger.info(f"Classifying website with {llm_provider} / {llm_model}")

    raw = ""
    try:
        if llm_provider == "Ollama":
            response = ollama.chat(
                model=llm_model,
                messages=[{"role": "user", "content": prompt}],
                options={"num_predict": 50, "temperature": 0.0}
            )
            raw = response.get("message", {}).get("content", "")
        else:
            if not API_KEY or API_KEY == "placeholder":
                raise RuntimeError("Sambanova API_KEY not configured.")
            client = get_sambanova_client()
            resp = client.chat.completions.create(
                model=llm_model or "QwQ-32B",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                top_p=0.1,
                timeout=60,
                max_tokens=50,
            )
            raw = resp.choices[0].message.content
    except Exception as e:
        logger.error(f"Classification failed: {e}, falling back to general")
        return "general", CATEGORY_TEMPLATES["general"]["fields"]

    category = _parse_category(raw)
    info = get_category_info(category)
    logger.info(f"Classified as: {category} ({info['name_zh']}) - default fields: {info['fields']}")
    return category, info["fields"]


# ─── 字段自适应 ───

FIELD_ADAPT_PROMPT = """You are a data schema designer. The user wants to extract data from a webpage.
A category template provides DEFAULT fields. Your job is ONLY to suggest ADDITIONAL fields that this
specific page clearly contains but defaults missed.

### Webpage sample:
'''
{sample}
'''

### Category: {category}
### Default fields (MUST KEEP all of these): {default_fields}

### Rules:
1. ALWAYS keep every default field, in the same order. NEVER remove a default field.
2. You may APPEND at most 2 new fields if the page clearly has them and they're commonly useful.
   Examples: a forum page → add "points" and "comments_count"; a product page → add "sku".
3. If the default fields already cover the page well, output them UNCHANGED.
4. Use lowercase snake_case for any new field names.
5. Output ONLY a comma-separated field list. No explanation, no markdown, no quotes, no commentary.
6. The output MUST start with the default fields verbatim.

### Final fields (default + optional additions):"""


def adapt_fields_for_page(scraped_sample, category, default_fields,
                          llm_provider="Ollama", llm_model=None):
    """
    Conservative field adaptation: keep all defaults, only allow ADDING up to 2 fields.
    Falls back to default_fields on any failure or invalid output.
    """
    sample = (scraped_sample or "")[:2500]
    if not sample.strip():
        return default_fields

    default_list = [f.strip() for f in default_fields.split(",") if f.strip()]
    if not default_list:
        return default_fields

    prompt = FIELD_ADAPT_PROMPT.format(
        sample=sample, category=category, default_fields=default_fields
    )

    raw = ""
    try:
        if llm_provider == "Ollama":
            response = ollama.chat(
                model=llm_model,
                messages=[{"role": "user", "content": prompt}],
                options={"num_predict": 100, "temperature": 0.0}
            )
            raw = response.get("message", {}).get("content", "")
        else:
            if not API_KEY or API_KEY == "placeholder":
                logger.warning("Sambanova API_KEY missing; cannot adapt fields")
                return default_fields
            client = get_sambanova_client()
            resp = client.chat.completions.create(
                model=llm_model or "QwQ-32B",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                top_p=0.1,
                timeout=60,
                max_tokens=120,
            )
            raw = resp.choices[0].message.content
    except Exception as e:
        logger.warning(f"Field adaptation failed: {e}, using default fields")
        return default_fields

    # 清洗:去掉 think 标签 + markdown
    text = re.sub(r"^.*?</think>", "", raw, flags=re.DOTALL).strip()
    text = re.sub(r"```[a-zA-Z]*\n?", "", text)
    text = re.sub(r"```", "", text)
    text = text.strip().strip("`").strip()

    # 取最后一行非空内容
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    candidate = lines[-1] if lines else ""

    if not candidate or len(candidate) > 300:
        return default_fields

    # 解析 LLM 输出
    proposed = [f.strip().strip('"').strip("'") for f in candidate.split(",")]
    proposed = [f for f in proposed if f and re.match(r'^[a-zA-Z][a-zA-Z0-9_]*$', f)]

    if not proposed:
        return default_fields

    # 强制保护:输出必须包含所有默认字段(顺序不强求,但全部要在)
    proposed_lower = [f.lower() for f in proposed]
    default_lower = [f.lower() for f in default_list]
    missing_defaults = [d for d in default_list if d.lower() not in proposed_lower]
    if missing_defaults:
        logger.warning(
            f"Adapted fields missing defaults {missing_defaults}, using defaults only"
        )
        return default_fields

    # 找出新增的字段(不在默认列表里的)
    additions = []
    for f in proposed:
        if f.lower() not in default_lower and f.lower() not in [a.lower() for a in additions]:
            additions.append(f)

    # 限制新增字段最多 2 个
    additions = additions[:2]

    # 总字段数不能超过 8
    final_list = default_list + additions
    if len(final_list) > 8:
        final_list = final_list[:8]

    final_fields = ", ".join(final_list)
    if final_fields != default_fields:
        logger.info(f"Fields adapted (added {additions}): {default_fields} -> {final_fields}")
    else:
        logger.info(f"Fields adapted: kept defaults {default_fields}")
    return final_fields


# ─── LLM 输出校验与重试 ───

def _strip_csv_wrappers(text):
    """Remove think tags, markdown code fences, and surrounding whitespace."""
    if not text:
        return ""
    text = re.sub(r"^.*?</think>", "", text, flags=re.DOTALL).strip()
    text = re.sub(r"```(?:csv|CSV)?\s*\n?", "", text)
    text = re.sub(r"```\s*$", "", text, flags=re.MULTILINE)
    return text.strip()


def _expected_field_count(query):
    """Count fields requested in the user query (rough heuristic)."""
    if not query:
        return 0
    parts = [p.strip() for p in query.split(",") if p.strip()]
    return len(parts)


def _try_fix_malformed_header(text: str, expected: int) -> str:
    """如果 header 中某个字段名含逗号(说明 LLM 引号位置错乱),尝试用预期字段数硬切表头。"""
    if not text or expected <= 0:
        return text
    lines = text.splitlines()
    if not lines:
        return text
    header_line = lines[0]
    try:
        parsed_header = next(csv.reader(StringIO(header_line)))
    except Exception:
        return text
    # 字段名含逗号 = 引号开错位置
    if any("," in h for h in parsed_header):
        clean = header_line.replace('"', '').replace("'", '')
        fields = [f.strip() for f in clean.split(",") if f.strip()]
        # 仅当切出来正好等于 expected 时才修复
        if len(fields) == expected:
            new_header = ",".join(f'"{f}"' for f in fields)
            return new_header + "\n" + "\n".join(lines[1:])
    return text


def validate_csv_output(raw_text, query, min_rows=1):
    """
    Validate LLM CSV output. Returns (is_valid, reason, parsed_rows).

    Checks:
      - Non-empty content
      - At least one data row
      - Header column count matches (or is close to) the requested field count
      - Most rows have the same column count as the header
    """
    text = _strip_csv_wrappers(raw_text)
    if not text:
        return False, "empty output", []

    expected = _expected_field_count(query)
    # 尝试修复 LLM 引号错位导致的畸形表头(把 "a,"b","c" 修成 "a","b","c")
    text = _try_fix_malformed_header(text, expected)

    lines = [l for l in text.splitlines() if l.strip()]
    if len(lines) < 1 + min_rows:
        return False, f"too few lines ({len(lines)})", []

    try:
        reader = csv.reader(StringIO(text))
        rows = list(reader)
    except Exception as e:
        return False, f"csv parse failed: {e}", []

    if not rows:
        return False, "no parsed rows", []

    header = rows[0]
    header_cols = len(header)

    if expected > 0 and abs(header_cols - expected) > 1:
        return False, f"header columns {header_cols} != expected {expected}", []

    data_rows = rows[1:]
    if len(data_rows) < min_rows:
        return False, f"only {len(data_rows)} data rows", []

    # Tolerate some malformed rows but reject if >50% misaligned
    aligned = sum(1 for r in data_rows if len(r) == header_cols)
    if aligned < len(data_rows) * 0.5:
        return False, f"only {aligned}/{len(data_rows)} rows aligned with header", []

    parsed = []
    for r in data_rows:
        if len(r) == header_cols:
            parsed.append(dict(zip(header, r)))
    return True, "ok", parsed


def generate_with_validation(query, scraped_data, llm_provider="Ollama",
                              llm_model=None, max_retries=2):
    """
    Generate CSV with validation + retry on bad output.

    Returns the raw CSV text (validated). Raises RuntimeError if all attempts fail.
    """
    last_raw = ""
    last_reason = ""

    for attempt in range(max_retries + 1):
        try:
            if llm_provider == "Ollama":
                raw = generate_response(llm_model, query, scraped_data)
            else:
                raw = generate_response2(query, scraped_data, llm_model)
        except Exception as e:
            last_reason = f"call failed: {e}"
            logger.warning(f"LLM attempt {attempt + 1} raised: {e}")
            continue

        is_valid, reason, _ = validate_csv_output(raw, query)
        last_raw = raw
        last_reason = reason

        if is_valid:
            if attempt > 0:
                logger.info(f"LLM output validated on attempt {attempt + 1}")
            # 返回经过 header 修复的文本,确保下游解析能拿到正确表头
            stripped = _strip_csv_wrappers(raw)
            return _try_fix_malformed_header(stripped, _expected_field_count(query))

        logger.warning(
            f"LLM attempt {attempt + 1} produced invalid CSV ({reason}), retrying..."
        )

    logger.error(f"LLM validation failed after {max_retries + 1} attempts: {last_reason}")
    # Return last raw output anyway — pipeline downstream may still salvage some rows
    return _strip_csv_wrappers(last_raw)