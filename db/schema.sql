-- ==========================================================================
-- AI-Scraper 数据库 Schema (MySQL 8.0)
-- 课程作品: RPA 数据自动化采集 + 关系数据库系统
-- 一键导入: mysql -u root -p --default-character-set=utf8mb4 < db/schema.sql
-- ==========================================================================

SET NAMES utf8mb4;
SET CHARACTER SET utf8mb4;

DROP DATABASE IF EXISTS ai_scraper_db;
CREATE DATABASE ai_scraper_db
    DEFAULT CHARACTER SET utf8mb4
    DEFAULT COLLATE utf8mb4_unicode_ci;

USE ai_scraper_db;

-- ==========================================================================
-- 元数据层: 类别字典 + 任务表 + 抓取结果表
-- ==========================================================================

CREATE TABLE categories (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    code            VARCHAR(50)  NOT NULL UNIQUE COMMENT '类别 key (英文)',
    name_zh         VARCHAR(50)  NOT NULL        COMMENT '类别中文名',
    description     VARCHAR(500)                 COMMENT '描述',
    default_fields  VARCHAR(500)                 COMMENT '默认字段列表 (CSV)',
    INDEX idx_code (code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='网站类别字典';

CREATE TABLE jobs (
    id                BIGINT AUTO_INCREMENT PRIMARY KEY,
    name              VARCHAR(200) NOT NULL                                   COMMENT '任务名称',
    status            ENUM('pending','running','completed','failed') DEFAULT 'pending' COMMENT '状态',
    category_id       INT                                                     COMMENT '识别后的类别',
    method            VARCHAR(20)  DEFAULT 'Crawl4AI'                         COMMENT '抓取引擎',
    llm_provider      VARCHAR(20)  DEFAULT 'Ollama'                           COMMENT 'LLM 提供商',
    llm_model         VARCHAR(80)                                             COMMENT 'LLM 模型',
    follow_pagination TINYINT(1)   DEFAULT 0                                  COMMENT '是否翻页',
    max_pages         INT          DEFAULT 5                                  COMMENT '最大页数',
    schedule_cron     VARCHAR(50)                                             COMMENT 'Cron 表达式',
    pipeline_config   JSON                                                    COMMENT 'pipeline 配置',
    urls              JSON                                                    COMMENT 'URL 列表',
    `query`           VARCHAR(500)                                            COMMENT '提取字段',
    created_at        TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    started_at        TIMESTAMP    NULL,
    completed_at      TIMESTAMP    NULL,
    error_message     TEXT,
    FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE SET NULL,
    INDEX idx_status_created (status, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='采集任务';

-- 占位 marker:STEP_3_PART1

CREATE TABLE results (
    id            BIGINT AUTO_INCREMENT PRIMARY KEY,
    job_id        BIGINT       NOT NULL,
    url           VARCHAR(2048) NOT NULL,
    page_number   INT          DEFAULT 1,
    raw_markdown  MEDIUMTEXT                       COMMENT '原始抓取的 markdown',
    extracted_csv MEDIUMTEXT                       COMMENT 'LLM 输出的 CSV',
    row_count     INT          DEFAULT 0,
    status        VARCHAR(20)  DEFAULT 'pending',
    error_message TEXT,
    created_at    TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE,
    INDEX idx_job (job_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='每页抓取结果';

-- ==========================================================================
-- 维度表 (供业务表外键引用)
-- ==========================================================================

CREATE TABLE authors (
    id          BIGINT AUTO_INCREMENT PRIMARY KEY,
    name        VARCHAR(200) NOT NULL,
    nationality VARCHAR(50)                        COMMENT '国籍',
    birth_year  SMALLINT                           COMMENT '出生年',
    bio         TEXT                               COMMENT '简介',
    UNIQUE KEY uk_author_name (name),
    CHECK (birth_year IS NULL OR (birth_year BETWEEN 1000 AND 2100))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='作者维表';

CREATE TABLE brands (
    id   INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='品牌维表';

CREATE TABLE news_sources (
    id   INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    url  VARCHAR(500)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='新闻来源维表';

CREATE TABLE tags (
    id   INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(50) NOT NULL UNIQUE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='标签维表';

-- ==========================================================================
-- 业务数据层 (类别专属表)
-- ==========================================================================

-- 图书表
CREATE TABLE books (
    id           BIGINT AUTO_INCREMENT PRIMARY KEY,
    job_id       BIGINT,
    title        VARCHAR(500) NOT NULL,
    author_id    BIGINT                                COMMENT '关联作者维表',
    price        DECIMAL(10,2)                         COMMENT '价格',
    currency     CHAR(3)      DEFAULT 'GBP'            COMMENT '币种 ISO 4217',
    rating       TINYINT                               COMMENT '评分 1-5',
    availability VARCHAR(50)                           COMMENT '库存状态',
    isbn         VARCHAR(20),
    source_url   VARCHAR(2048),
    cover_image_url VARCHAR(2048)                        COMMENT '封面图 URL',
    scraped_at   TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (job_id)    REFERENCES jobs(id)    ON DELETE SET NULL,
    FOREIGN KEY (author_id) REFERENCES authors(id) ON DELETE SET NULL,
    UNIQUE KEY uk_book_title_author (title, author_id),
    INDEX idx_price  (price),
    INDEX idx_rating (rating),
    INDEX idx_scraped_at (scraped_at),
    FULLTEXT KEY ft_title (title),
    CHECK (price IS NULL OR price >= 0),
    CHECK (rating IS NULL OR (rating BETWEEN 1 AND 5))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='图书业务表';

-- 名言表
CREATE TABLE quotes (
    id         BIGINT AUTO_INCREMENT PRIMARY KEY,
    job_id     BIGINT,
    quote      TEXT         NOT NULL,
    author_id  BIGINT,
    source_url VARCHAR(2048),
    scraped_at TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (job_id)    REFERENCES jobs(id)    ON DELETE SET NULL,
    FOREIGN KEY (author_id) REFERENCES authors(id) ON DELETE SET NULL,
    INDEX idx_author (author_id),
    INDEX idx_scraped_at (scraped_at),
    FULLTEXT KEY ft_quote (quote)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='名言业务表';

-- 名言-标签 多对多关联表
CREATE TABLE quote_tags (
    quote_id BIGINT NOT NULL,
    tag_id   INT    NOT NULL,
    PRIMARY KEY (quote_id, tag_id),
    FOREIGN KEY (quote_id) REFERENCES quotes(id) ON DELETE CASCADE,
    FOREIGN KEY (tag_id)   REFERENCES tags(id)   ON DELETE CASCADE,
    INDEX idx_tag (tag_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='名言-标签多对多';

-- 商品表
CREATE TABLE products (
    id         BIGINT AUTO_INCREMENT PRIMARY KEY,
    job_id     BIGINT,
    name       VARCHAR(500) NOT NULL,
    brand_id   INT,
    price      DECIMAL(10,2),
    currency   CHAR(3)      DEFAULT 'USD',
    sku        VARCHAR(100),
    rating     DECIMAL(3,2),
    source_url VARCHAR(2048),
    image_url  VARCHAR(2048)                             COMMENT '商品图 URL',
    scraped_at TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (job_id)   REFERENCES jobs(id)   ON DELETE SET NULL,
    FOREIGN KEY (brand_id) REFERENCES brands(id) ON DELETE SET NULL,
    UNIQUE KEY uk_product_name_brand (name, brand_id),
    INDEX idx_brand_price (brand_id, price),
    INDEX idx_scraped_at (scraped_at),
    FULLTEXT KEY ft_name (name),
    CHECK (price IS NULL OR price >= 0),
    CHECK (rating IS NULL OR (rating BETWEEN 0 AND 5))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='商品业务表';

-- 新闻表
CREATE TABLE news (
    id           BIGINT AUTO_INCREMENT PRIMARY KEY,
    job_id       BIGINT,
    title        VARCHAR(500) NOT NULL,
    author       VARCHAR(200),
    source_id    INT,
    publish_date DATE,
    summary      TEXT,
    url          VARCHAR(2048),
    cover_image_url VARCHAR(2048)                        COMMENT '新闻头图 URL',
    url_hash     CHAR(64) GENERATED ALWAYS AS (SHA2(url, 256)) STORED COMMENT 'URL 的 SHA256 用于唯一约束',
    scraped_at   TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (job_id)    REFERENCES jobs(id)         ON DELETE SET NULL,
    FOREIGN KEY (source_id) REFERENCES news_sources(id) ON DELETE SET NULL,
    UNIQUE KEY uk_news_url (url_hash),
    INDEX idx_publish_date (publish_date),
    INDEX idx_source (source_id),
    FULLTEXT KEY ft_title_summary (title, summary)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='新闻业务表';

-- 招聘信息表 (避免和 jobs 任务表名冲突)
CREATE TABLE jobs_listings (
    id         BIGINT AUTO_INCREMENT PRIMARY KEY,
    job_id     BIGINT,
    job_title  VARCHAR(300) NOT NULL,
    company    VARCHAR(200),
    location   VARCHAR(200),
    salary     VARCHAR(100),
    post_date  DATE,
    source_url VARCHAR(2048),
    scraped_at TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE SET NULL,
    UNIQUE KEY uk_jobs_listing (job_title(150), company(80), location(80)),
    INDEX idx_company  (company),
    INDEX idx_location (location),
    INDEX idx_post_date (post_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='招聘信息业务表';

-- 通用 fallback 表 (其他冷门类别走这里)
CREATE TABLE generic_items (
    id         BIGINT AUTO_INCREMENT PRIMARY KEY,
    job_id     BIGINT,
    category   VARCHAR(50)  NOT NULL,
    data_json  JSON         NOT NULL,
    source_url VARCHAR(2048),
    scraped_at TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE SET NULL,
    INDEX idx_category (category),
    INDEX idx_scraped_at (scraped_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='通用回退表';

-- ==========================================================================
-- 历史 / 审计层 (展示触发器)
-- ==========================================================================

CREATE TABLE price_history (
    id          BIGINT AUTO_INCREMENT PRIMARY KEY,
    book_id     BIGINT,
    product_id  BIGINT,
    old_price   DECIMAL(10,2),
    new_price   DECIMAL(10,2),
    changed_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (book_id)    REFERENCES books(id)    ON DELETE CASCADE,
    FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE,
    INDEX idx_book    (book_id, changed_at),
    INDEX idx_product (product_id, changed_at),
    CHECK (book_id IS NOT NULL OR product_id IS NOT NULL)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='价格变更历史 (由触发器维护)';

-- ==========================================================================
-- 触发器
-- ==========================================================================

DELIMITER //

-- 图书价格变更 → 自动写入 price_history
CREATE TRIGGER trg_book_price_change
AFTER UPDATE ON books
FOR EACH ROW
BEGIN
    IF NOT (OLD.price <=> NEW.price) THEN
        INSERT INTO price_history(book_id, old_price, new_price)
        VALUES (OLD.id, OLD.price, NEW.price);
    END IF;
END//

-- 商品价格变更 → 自动写入 price_history
CREATE TRIGGER trg_product_price_change
AFTER UPDATE ON products
FOR EACH ROW
BEGIN
    IF NOT (OLD.price <=> NEW.price) THEN
        INSERT INTO price_history(product_id, old_price, new_price)
        VALUES (OLD.id, OLD.price, NEW.price);
    END IF;
END//

DELIMITER ;

-- ==========================================================================
-- 视图 (封装常用 JOIN)
-- ==========================================================================

CREATE VIEW v_book_summary AS
SELECT
    b.id, b.title,
    a.name        AS author_name,
    a.nationality AS author_nationality,
    b.price, b.currency, b.rating, b.availability,
    j.name        AS job_name,
    b.scraped_at
FROM books b
LEFT JOIN authors a ON b.author_id = a.id
LEFT JOIN jobs    j ON b.job_id    = j.id;

CREATE VIEW v_top_authors AS
SELECT
    a.id, a.name,
    COUNT(b.id)        AS book_count,
    AVG(b.price)       AS avg_price,
    AVG(b.rating)      AS avg_rating,
    MAX(b.scraped_at)  AS last_scraped_at
FROM authors a
JOIN books   b ON a.id = b.author_id
GROUP BY a.id, a.name;

CREATE VIEW v_category_stats AS
SELECT
    c.code, c.name_zh,
    COUNT(DISTINCT j.id) AS job_count,
    COUNT(r.id)          AS page_count,
    COALESCE(SUM(r.row_count), 0) AS total_rows
FROM categories c
LEFT JOIN jobs    j ON c.id = j.category_id
LEFT JOIN results r ON j.id = r.job_id
GROUP BY c.code, c.name_zh;

CREATE VIEW v_product_summary AS
SELECT
    p.id, p.name,
    br.name AS brand_name,
    p.price, p.currency, p.rating, p.sku,
    j.name AS job_name,
    p.scraped_at
FROM products p
LEFT JOIN brands br ON p.brand_id = br.id
LEFT JOIN jobs   j  ON p.job_id   = j.id;

-- ==========================================================================
-- 初始化数据: 类别字典 (与 categories.py 同步)
-- ==========================================================================

INSERT INTO categories (code, name_zh, description, default_fields) VALUES
    ('books',       '书籍 / 图书',     '图书电商或图书目录网站',                   'title, author, price, rating, availability'),
    ('news',        '新闻 / 资讯',     '新闻、博客、资讯类网站',                   'title, author, publish_date, summary, url'),
    ('jobs',        '招聘 / 职位',     '招聘信息、职位列表网站',                   'job_title, company, location, salary, post_date'),
    ('products',    '电商 / 商品',     '电商商品列表、产品目录',                   'name, price, brand, rating, sku'),
    ('movies',      '电影 / 影视',     '电影、影视、视频网站',                     'title, year, director, rating, genre'),
    ('papers',      '论文 / 学术',     '学术论文、研究成果网站',                   'title, authors, abstract, year, venue'),
    ('real_estate', '房地产',         '房产、租房、二手房网站',                   'title, price, location, area, bedrooms, type'),
    ('restaurants', '餐饮 / 美食',     '餐厅、美食点评网站',                       'name, cuisine, price_range, rating, address'),
    ('events',      '活动 / 演出',     '活动、演唱会、展会网站',                   'title, date, location, price, organizer'),
    ('quotes',      '名言 / 语录',     '名言、语录、文学摘录',                     'quote, author, tags'),
    ('courses',     '课程 / 教育',     '在线课程、教育平台',                       'title, instructor, price, rating, duration'),
    ('forum',       '论坛 / 社区帖子', '论坛、新闻聚合站、社区',                   'title, author, points, comments_count, posted_at, url'),
    ('general',     '通用 / 其他',     '无法明确分类时的通用模板',                 'title, description, url, date');

-- 完成提示
SELECT 'Schema created successfully.' AS status;

