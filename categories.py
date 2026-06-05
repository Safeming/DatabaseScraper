"""
网站类别模板 - 定义不同类型网站的常见提取字段。
用于 AI 自动识别网站类型并匹配默认提取字段。
"""

CATEGORY_TEMPLATES = {
    "books": {
        "name_zh": "书籍 / 图书",
        "fields": "title, author, price, rating, availability",
        "description": "图书电商或图书目录网站",
        "examples": ["books.toscrape.com", "amazon.com/books", "豆瓣读书"],
    },
    "news": {
        "name_zh": "新闻 / 资讯",
        "fields": "title, author, publish_date, summary, url",
        "description": "新闻、博客、资讯类网站",
        "examples": ["news.ycombinator.com", "新浪新闻", "BBC"],
    },
    "jobs": {
        "name_zh": "招聘 / 职位",
        "fields": "job_title, company, location, salary, post_date",
        "description": "招聘信息、职位列表网站",
        "examples": ["realpython.github.io/fake-jobs", "智联招聘", "BOSS直聘"],
    },
    "products": {
        "name_zh": "电商 / 商品",
        "fields": "name, price, brand, rating, sku",
        "description": "电商商品列表、产品目录",
        "examples": ["scrapeme.live/shop", "淘宝", "京东"],
    },
    "movies": {
        "name_zh": "电影 / 影视",
        "fields": "title, year, director, rating, genre",
        "description": "电影、影视、视频网站",
        "examples": ["IMDb", "豆瓣电影", "烂番茄"],
    },
    "papers": {
        "name_zh": "论文 / 学术",
        "fields": "title, authors, abstract, year, venue",
        "description": "学术论文、研究成果网站",
        "examples": ["arxiv.org", "Google Scholar", "知网"],
    },
    "real_estate": {
        "name_zh": "房地产",
        "fields": "title, price, location, area, bedrooms, type",
        "description": "房产、租房、二手房网站",
        "examples": ["链家", "贝壳找房", "Zillow"],
    },
    "restaurants": {
        "name_zh": "餐饮 / 美食",
        "fields": "name, cuisine, price_range, rating, address",
        "description": "餐厅、美食点评网站",
        "examples": ["大众点评", "Yelp", "美团"],
    },
    "events": {
        "name_zh": "活动 / 演出",
        "fields": "title, date, location, price, organizer",
        "description": "活动、演唱会、展会网站",
        "examples": ["Eventbrite", "大麦网", "豆瓣同城"],
    },
    "quotes": {
        "name_zh": "名言 / 语录",
        "fields": "quote, author, tags",
        "description": "名言、语录、文学摘录",
        "examples": ["quotes.toscrape.com", "格言网"],
    },
    "courses": {
        "name_zh": "课程 / 教育",
        "fields": "title, instructor, price, rating, duration",
        "description": "在线课程、教育平台",
        "examples": ["Coursera", "Udemy", "网易云课堂"],
    },
    "forum": {
        "name_zh": "论坛 / 社区帖子",
        "fields": "title, author, points, comments_count, posted_at, url",
        "description": "论坛、新闻聚合站、社区(如 Hacker News / Reddit / V2EX)",
        "examples": ["news.ycombinator.com", "Reddit", "V2EX"],
    },
    "general": {
        "name_zh": "通用 / 其他",
        "fields": "title, description, url, date",
        "description": "无法明确分类时的通用模板",
        "examples": [],
    },
}


def get_category_list():
    """返回所有类别的展示列表 (key, 中文名)。"""
    return [(key, val["name_zh"]) for key, val in CATEGORY_TEMPLATES.items()]


def get_template_fields(category_key):
    """根据类别 key 返回默认字段字符串。"""
    template = CATEGORY_TEMPLATES.get(category_key)
    if not template:
        return CATEGORY_TEMPLATES["general"]["fields"]
    return template["fields"]


def get_category_info(category_key):
    """返回类别的完整信息字典。"""
    return CATEGORY_TEMPLATES.get(category_key, CATEGORY_TEMPLATES["general"])


def list_category_keys():
    """返回所有类别 key 列表。"""
    return list(CATEGORY_TEMPLATES.keys())
