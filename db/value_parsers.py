"""LLM 抽出来的字符串值 → Python 类型转换器。

用于业务表入库前的字段清洗:
- "£51.77"   -> (51.77, "GBP")
- "Four"     -> 4
- "★★★★"    -> 4
- "4.5/5"    -> 4
- "1.2k"     -> 1200
- "3 days ago" / "2024-03-15" / "March 15, 2024" -> date
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Optional, Tuple

# 货币符号 → ISO 4217 代码
_CURRENCY_MAP = {
    "£": "GBP", "$": "USD", "€": "EUR", "¥": "CNY", "₹": "INR",
    "₩": "KRW", "₽": "RUB", "฿": "THB", "₫": "VND",
    "RMB": "CNY", "USD": "USD", "EUR": "EUR", "GBP": "GBP",
    "JPY": "JPY", "CNY": "CNY",
}

# 英文星级数字
_RATING_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "1": 1, "2": 2, "3": 3, "4": 4, "5": 5,
}


def parse_price(raw: Optional[str]) -> Tuple[Optional[float], Optional[str]]:
    """解析价格,返回 (金额, 币种代码)。识别失败返回 (None, None)。"""
    if raw is None:
        return None, None
    text = str(raw).strip()
    if not text or text.upper() in ("N/A", "NULL", "NONE"):
        return None, None

    # 优先匹配 ISO 三字母代码 (放在数字前后都行)
    currency = None
    for token, code in _CURRENCY_MAP.items():
        if token in text:
            currency = code
            break

    # 抓取第一个数字 (含小数 / 千分位)
    match = re.search(r"(\d{1,3}(?:[,，]\d{3})*(?:\.\d+)?|\d+(?:\.\d+)?)", text)
    if not match:
        return None, currency

    num_str = match.group(1).replace(",", "").replace(",", "")
    try:
        return float(num_str), currency
    except ValueError:
        return None, currency


def parse_rating(raw: Optional[str], scale: int = 5) -> Optional[float]:
    """解析评分到 0-scale 区间。返回 float (调用方按需 round 到 int)。"""
    if raw is None:
        return None
    text = str(raw).strip()
    if not text or text.upper() in ("N/A", "NULL", "NONE"):
        return None

    # 形如 "4.5/5" / "4/5"
    m = re.search(r"(\d+(?:\.\d+)?)\s*/\s*(\d+)", text)
    if m:
        num, denom = float(m.group(1)), float(m.group(2))
        if denom > 0:
            return round(num / denom * scale, 2)

    # 星号 ★ ☆ * 数量
    star_count = sum(1 for c in text if c in "★⭐")
    if star_count > 0:
        return min(star_count, scale)

    # 英文 / 数字单词
    lower = text.lower()
    for word, n in _RATING_WORDS.items():
        if re.search(rf"\b{word}\b", lower):
            return float(n)

    # 纯数字
    m = re.search(r"\d+(?:\.\d+)?", text)
    if m:
        v = float(m.group(0))
        # 如果 >scale,推断是 0-100 制
        if v > scale and v <= 100:
            return round(v / 100 * scale, 2)
        return min(v, scale)

    return None


def parse_int_with_suffix(raw: Optional[str]) -> Optional[int]:
    """'1.2k' -> 1200, '3M' -> 3000000, '5,234' -> 5234"""
    if raw is None:
        return None
    text = str(raw).strip().lower().replace(",", "")
    if not text or text in ("n/a", "null", "none"):
        return None

    multiplier = 1
    if text.endswith("k"):
        multiplier, text = 1_000, text[:-1]
    elif text.endswith("m"):
        multiplier, text = 1_000_000, text[:-1]
    elif text.endswith("b"):
        multiplier, text = 1_000_000_000, text[:-1]

    m = re.search(r"\d+(?:\.\d+)?", text)
    if not m:
        return None
    try:
        return int(float(m.group(0)) * multiplier)
    except ValueError:
        return None


_REL_TIME_PATTERN = re.compile(
    r"(\d+)\s*(second|minute|hour|day|week|month|year)s?\s*ago", re.I
)


def parse_date(raw: Optional[str], today: Optional[date] = None) -> Optional[date]:
    """解析多种格式:
    - '2024-03-15', '2024/03/15', '15.03.2024'
    - 'March 15, 2024', '15 Mar 2024'
    - '3 days ago', 'yesterday'
    """
    if raw is None:
        return None
    text = str(raw).strip()
    if not text or text.upper() in ("N/A", "NULL", "NONE"):
        return None

    today = today or date.today()
    lower = text.lower()

    if lower in ("today", "今天"):
        return today
    if lower in ("yesterday", "昨天"):
        return today - timedelta(days=1)

    m = _REL_TIME_PATTERN.search(lower)
    if m:
        n, unit = int(m.group(1)), m.group(2).lower()
        delta_days = {
            "second": 0, "minute": 0, "hour": 0,
            "day": n, "week": n * 7, "month": n * 30, "year": n * 365,
        }.get(unit, 0)
        return today - timedelta(days=delta_days)

    # ISO / 斜杠 / 点分隔
    formats = [
        "%Y-%m-%d", "%Y/%m/%d", "%d.%m.%Y", "%d/%m/%Y",
        "%B %d, %Y", "%d %b %Y", "%b %d, %Y", "%d %B %Y",
        "%Y年%m月%d日",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue

    # 兜底:从字符串里提取 yyyy-mm-dd 模式
    m = re.search(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})", text)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    return None


def coerce_str(raw, max_len: Optional[int] = None) -> Optional[str]:
    """普通字符串清洗:去首尾空白、N/A/None 视为空、可选截断。"""
    if raw is None:
        return None
    text = str(raw).strip()
    if not text or text.upper() in ("N/A", "NULL", "NONE"):
        return None
    if max_len and len(text) > max_len:
        text = text[:max_len]
    return text


# LLM 可能用的图片 URL 字段别名(按常见度排序)
_IMAGE_URL_ALIASES = (
    "cover_image_url", "image_url", "cover", "thumbnail",
    "photo", "image", "img", "picture", "cover_url",
)


def extract_image_url(row: dict) -> Optional[str]:
    """从 LLM 输出的 row dict 里挖图片 URL,容忍 LLM 用各种字段名 + [IMG: url] 标记格式。"""
    for key in _IMAGE_URL_ALIASES:
        v = row.get(key)
        if not v:
            continue
        s = str(v).strip()
        if not s or s.upper() in ("N/A", "NULL", "NONE"):
            continue
        # 可能是 LLM 保留了 [IMG: url] 标记格式,挖出真实 URL
        import re
        m = re.search(r"\[IMG:\s*(https?://[^\]\s]+)\s*\]", s)
        if m:
            s = m.group(1)
        # 必须是 http(s) 开头才算有效
        if s.startswith(("http://", "https://", "//")):
            if s.startswith("//"):
                s = "https:" + s
            return s[:2048]
    return None
