# AI-Scraper · 智能网页数据采集与关系数据库系统

> **基于 LLM + Web Scraping 的智能数据提取系统**
> 输入 URL,AI 自动识别网站类型并提取结构化数据,直接入库到 MySQL 关系数据库,支持可视化分析和复杂 SQL 查询。

---

## ✨ 核心特性

### 🤖 智能采集
- **AI 自动识别网站类型** — 13 个内置类别(图书/名言/商品/新闻/招聘等),AI 自动选字段
- **零代码提取** — 用自然语言描述字段,无需 XPath/CSS 选择器
- **双引擎抓取** — Crawl4AI + Selenium,自动降级容错
- **登录态支持** — 支持 Cookie 注入,可采集需登录的网站
- **自动翻页** — 智能检测分页链接,支持多页连续采集
- **批量与并发** — 多 URL 并行,信号量限流防 API 滥用

### 🗄️ 关系数据库 (MySQL 8.0)
- **15 张表** — 元数据 / 维度 / 业务 / 审计四层
- **类别专属表** — books/quotes/products/news/jobs_listings 各有专属字段约束
- **完整约束** — 主外键、UNIQUE、CHECK、生成列、全文索引
- **触发器** — 价格变更自动写入 history 表
- **视图** — 4 个常用 JOIN 视图供前端复用

### 📊 可视化与查询
- **6 个 Streamlit 页面** — 主页 / 批量采集 / 任务历史 / 数据浏览 / 统计仪表盘 / SQL 查询 / 数据库结构
- **Plotly 图表** — 类别分布 / 价格分析 / 作者排行 / 趋势曲线
- **SQL 查询器** — 11 个预设示例 + 白名单防注入 + 只读账号双保险
- **多格式导出** — CSV / JSON / Excel / Markdown

---

## 🏗️ 系统架构

```
   用户输入 URL + 字段
            │
   ┌────────▼─────────────────────────────────┐
   │     Streamlit Web UI (6 个页面)           │
   │  主页 / 批量 / 历史 / 浏览 / 仪表盘 / SQL  │
   └────────┬─────────────────────────────────┘
            │
   ┌────────▼─────────────────────────────────┐
   │     Pipeline 流程编排                     │
   │  抓取 → 清洗 → AI 分类 → LLM 提取 → 入库  │
   └────────┬─────────────────────────────────┘
            │
   ┌────────▼─────────────────────────────────┐
   │     MySQL 8.0 关系数据库                  │
   │  15 表 + 4 视图 + 2 触发器 + 多种索引      │
   └──────────────────────────────────────────┘
```

---

## 📋 环境要求

| 组件 | 最低要求 | 推荐 |
|------|----------|------|
| 操作系统 | Windows 10 / macOS / Linux | Windows 10/11 |
| Python | 3.10 | 3.10 / 3.11 (Conda) |
| MySQL | 8.0+ | 8.0.40+ |
| 浏览器 | Google Chrome 或 Microsoft Edge | Edge (Windows 自带) |
| 内存 | 8 GB | 16 GB+ (本地 Ollama 需要) |
| LLM 选项 | Ollama 本地 **或** Sambanova API | 二选一即可 |

---

## 🚀 快速开始

### 1. 克隆项目

```bash
git clone https://github.com/Safeming/DatabaseScraper.git
cd DatabaseScraper
```

### 2. 安装 MySQL

**Windows**(推荐):
- 下载 [MySQL Installer](https://dev.mysql.com/downloads/installer/)
- 安装时选 `Developer Default`
- 设置 root 密码并记牢

**macOS**:
```bash
brew install mysql
brew services start mysql
mysql_secure_installation
```

**Linux** (Ubuntu/Debian):
```bash
sudo apt install mysql-server
sudo mysql_secure_installation
```

验证:
```bash
mysql --version  # 应显示 8.0+
```

### 3. 创建 Python 环境

**用 Conda(推荐)**:
```bash
conda create -n scraper python=3.10 -y
conda activate scraper
```

**用 venv**:
```bash
python -m venv venv
# Windows
venv\Scripts\activate
# macOS/Linux
source venv/bin/activate
```

### 4. 安装 Python 依赖

```bash
pip install -r requirements.txt
```

如果 Crawl4AI 报 playwright 错误,运行:
```bash
crawl4ai-setup
playwright install chromium
```

### 5. 初始化数据库

**5.1 一键导入 schema**

```bash
mysql -u root -p --default-character-set=utf8mb4 < db/schema.sql
```

输入你的 root 密码后,会自动创建数据库 `ai_scraper_db`、15 张表、4 个视图、2 个触发器、13 个类别字典。

**5.2 创建只读账号(SQL 查询页面用)**

```bash
mysql -u root -p
```
进入 mysql 提示符后执行:
```sql
CREATE USER 'ai_scraper_ro'@'localhost' IDENTIFIED BY 'readonly_pass';
GRANT SELECT, SHOW VIEW ON ai_scraper_db.* TO 'ai_scraper_ro'@'localhost';
FLUSH PRIVILEGES;
EXIT;
```

**5.3 (可选) 迁移老 SQLite 数据**

如果你之前用过 SQLite 版本,可以把数据迁移到 MySQL:
```bash
python -m db.migration
```

### 6. 配置 .env 文件

复制模板:
```bash
# Windows
copy .env.example .env
# macOS/Linux
cp .env.example .env
```

编辑 `.env`,填入你的 MySQL 密码:
```ini
# MySQL 主账号(读写)
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=你的MySQL密码
DB_NAME=ai_scraper_db

# 只读账号(SQL 查询页面专用)
DB_RO_USER=ai_scraper_ro
DB_RO_PASSWORD=readonly_pass

# Sambanova API Key (可选,使用云端 LLM 时填)
API_KEY=
```

### 7. 配置 LLM(二选一)

**方式 A:Ollama 本地运行(免费,推荐入门)**

1. 安装: https://ollama.com/download
2. 拉取模型(约 4GB):
   ```bash
   ollama pull qwen2.5:latest
   ```
3. 验证:
   ```bash
   ollama list
   ```

**方式 B:Sambanova 云端 API(付费/有免费额度,响应快)**

1. 注册: https://cloud.sambanova.ai/apis
2. 获取 API Key 后填入 `.env` 的 `API_KEY=`

### 8. 启动应用

```bash
python -m streamlit run app.py
```

浏览器自动打开 http://localhost:8501

如果要使用定时调度功能,**另开一个终端**:
```bash
python scheduler.py
```
或 Windows 双击 `start_scheduler.bat`。

---

## 🎯 功能页面导览

应用有 **7 个页面**(左侧导航栏):

| 页面 | 功能 |
|------|------|
| **🏠 主页** | 单 URL 快速抓取,智能识别 + 一键入库到 MySQL |
| **📦 批量采集** | 多 URL + 翻页 + 调度 + Cookie 注入 + 并发控制 |
| **📜 任务历史** | 查看所有采集任务、状态、提取数据、重新执行 |
| **📂 数据浏览** | 6 类 tab(图书/名言/商品/新闻/招聘/通用)+ 关键字筛选 |
| **📊 统计仪表盘** | 6 个 Plotly 图表 + KPI + 每图配 SQL |
| **🔍 SQL 查询** | 11 个预设示例 + EXPLAIN + 安全白名单 |
| **🗂️ 数据库结构** | ER 图 + 表/视图/触发器/索引动态展示 |

---

## 📁 项目结构

```
AI-Scraper/
├── app.py                    # 🏠 主页 - 快速抓取 + 一键入库
├── scraper.py                # 网页抓取引擎(Crawl4AI + Selenium + Cookie)
├── pagination.py             # 翻页检测(HTML + URL 模式)
├── pipeline.py               # 流程编排(抓取→清洗→分类→提取→入库)
├── generate_response.py      # LLM 调用 + 输出校验 + 字段适配
├── categories.py             # 13 个网站类别模板
├── sambanova.py              # Sambanova API 封装
├── scheduler.py              # 定时调度进程
├── database.py               # 兼容 shim(转发到 db/repository.py)
├── assets.py                 # User-Agent 列表
│
├── db/                       # ★ MySQL 数据层
│   ├── schema.sql            # 完整 DDL(一键导入)
│   ├── connection.py         # SQLAlchemy 引擎与 session
│   ├── models.py             # 16 个 ORM 模型
│   ├── repository.py         # 数据访问层
│   ├── value_parsers.py      # 价格/评分/日期解析器
│   ├── migration.py          # 老 SQLite → MySQL 迁移脚本
│   └── stores/               # 类别专属入库逻辑
│       ├── books.py
│       ├── quotes.py
│       ├── products.py
│       ├── news.py
│       ├── jobs_listings.py
│       └── generic.py
│
├── pages/                    # Streamlit 多页面
│   ├── 1_批量采集.py
│   ├── 2_任务历史.py
│   ├── 3_数据浏览.py
│   ├── 4_统计仪表盘.py
│   ├── 5_SQL查询.py
│   └── 6_数据库结构.py
│
├── doc/                      # 项目文档
│   ├── 数据库设计文档.md      # 完整设计文档(范式/约束/索引等)
│   ├── ER图.dbml             # dbdiagram.io 兼容的 ER 图源文件
│   ├── ER图.png              # ER 图(可选,从 dbml 导出)
│   ├── 修改记录.md            # 改动历史
│   └── PPT大纲.md            # 汇报大纲
│
├── tests/                    # 单元测试
├── exports/                  # Excel 导出输出目录(运行时生成)
├── requirements.txt          # Python 依赖
├── .env.example              # 环境变量模板(复制成 .env 后填)
├── .env                      # 实际配置(已在 .gitignore 中)
├── start_scheduler.bat       # Windows 一键启动调度器
└── README.md                 # 本文件
```

---

## 💡 使用示例

### 示例 1:智能识别 + 一键入库

1. 打开主页
2. URL 框: `https://books.toscrape.com/`
3. 提取模式: 🤖 智能识别(AI 自动选字段)
4. 点 "Start Scraping"
5. AI 识别为"📚 书籍"类别,自动用 `title, author, price, rating, availability`
6. 数据出来后展开 "💾 存入数据库" → 点击保存
7. 自动写入 `books` 表 + 自动建 `authors` 维表
8. 切到"数据浏览 → 📚 图书"tab 看结果

### 示例 2:批量采集 + 自动翻页 + 定时

1. 进入"📦 批量采集"页
2. 输入多个 URL(每行一个)
3. 勾选 "🤖 启用智能识别"
4. 勾选 "自动翻页",设置最大页数 = 5
5. 调度选 "每 24 小时" → Cron 表达式自动生成
6. 提交后,启动 `python scheduler.py` 让定时调度生效

### 示例 3:登录态采集

1. 进入"📦 批量采集"页 → 展开 "🔧 高级选项"
2. 在浏览器中登录目标网站
3. F12 → Network → 任意请求 → Headers → 复制 Cookie 字符串
4. 粘贴到"Cookie"框
5. 提交任务,Pipeline 自动用 Selenium + 注入 Cookie 抓取登录后页面

### 示例 4:SQL 查询数据库

切到"🔍 SQL 查询"页:

```sql
-- 高于平均价的图书(子查询)
SELECT title, price
FROM books
WHERE price > (SELECT AVG(price) FROM books)
ORDER BY price DESC;
```

```sql
-- 在所有名言中全文搜索 'love'(全文索引)
SELECT id, LEFT(quote, 100) AS excerpt
FROM quotes
WHERE MATCH(quote) AGAINST('love' IN NATURAL LANGUAGE MODE);
```

---

## 🗄️ 数据库设计概览

详见 [doc/数据库设计文档.md](doc/数据库设计文档.md)。

**15 张表分四层:**

- **元数据层** (3): `categories` / `jobs` / `results`
- **维度层** (4): `authors` / `brands` / `news_sources` / `tags`
- **业务层** (6): `books` / `quotes` / `products` / `news` / `jobs_listings` / `generic_items`
- **关联与审计层** (2): `quote_tags`(多对多)/ `price_history`(触发器维护)

**4 个视图:**
- `v_book_summary` / `v_top_authors` / `v_category_stats` / `v_product_summary`

**2 个触发器:**
- `trg_book_price_change` / `trg_product_price_change` — 自动维护价格变更历史

---

## 🔧 支持的 LLM 模型

| 提供商 | 推荐模型 | 说明 |
|--------|---------|------|
| Ollama | qwen2.5:latest (7B) | 本地,免费,显存 ≥6GB |
| Ollama | llama3:8b / qwen2.5:14b | 更强,需更多显存 |
| Sambanova | DeepSeek-R1-Distill-Llama-70B | 云端,推理强 |
| Sambanova | DeepSeek-V3-0324 | 云端,速度快 |
| Sambanova | Qwen3-32B / QwQ-32B | 云端,综合能力好 |

---

## 🌐 推荐测试网站

入门测试这些**专门为爬虫练习搭建**的合法站点:

| 网站 | 类别 | 用途 |
|------|------|------|
| https://books.toscrape.com/ | 图书 | 50 页,1000 本书 |
| https://quotes.toscrape.com/ | 名言 | 10 页,100 条名言 + 标签 |
| https://scrapeme.live/shop/ | 商品 | 宝可梦商品列表 |
| https://realpython.github.io/fake-jobs/ | 招聘 | 100 条假招聘信息 |

> ⚠️ **不要爬淘宝/京东/拼多多/知乎/微博/小红书** — 这些站点有强反爬 + 法律风险,可能导致账号被封或触犯法规。

---

## ❓ 常见问题

**Q: MySQL 连不上?**
A: 检查 `.env` 中的 `DB_PASSWORD` 是否正确;Windows 下确认 MySQL80 服务正在运行(`sc query MySQL80`)。

**Q: 中文显示乱码?**
A: 数据库已用 utf8mb4。如果导入 schema 时报 "Data too long" 错,加 `--default-character-set=utf8mb4` 参数。

**Q: Crawl4AI 抓取超时?**
A: 系统会自动降级到 Selenium。也可以在批量采集页改 method 为 "Selenium"。

**Q: 提取的数据 author/rating 全是 N/A?**
A: 检查目标网页是否真的有这些字段。比如 books.toscrape.com 列表页就没有作者信息,这是网站本身的限制。

**Q: 翻页没生效?**
A: 系统支持 `/page/N/`、`?page=N`、"Next"按钮 三种模式。如果都没识别到,日志会显示 `next_url detected: None`。

**Q: Ollama 模型列表为空?**
A: 确保 Ollama 已运行且至少拉取了一个模型: `ollama pull qwen2.5:latest`。

**Q: SQL 查询页面报"权限不足"?**
A: 你忘了创建只读账号 `ai_scraper_ro`,见安装步骤 5.2。或者直接把 `.env` 的 `DB_RO_USER` 留空,会自动降级用主账号。

**Q: 想重置数据库重新开始?**
A:
```bash
mysql -u root -p --default-character-set=utf8mb4 < db/schema.sql
```
schema.sql 顶部有 `DROP DATABASE IF EXISTS`,会先清空再重建。

---

## 🛠️ 技术栈

| 层 | 技术 |
|---|------|
| Web UI | Streamlit 1.57 |
| 网页抓取 | Crawl4AI 0.8 / Selenium 4.44 / BeautifulSoup |
| LLM 集成 | Ollama / Sambanova / OpenAI SDK |
| 数据库 | MySQL 8.0 + SQLAlchemy 2.0 + PyMySQL |
| 数据处理 | pandas / openpyxl / tabulate |
| 可视化 | Plotly 6.8 |
| 任务调度 | schedule + croniter |
| HTML→Markdown | html2text |
| 配置管理 | python-dotenv |

---

## 📜 许可证

MIT License — 项目本身可自由使用。

> ⚠️ **使用本工具时请遵守目标网站的 `robots.txt` 和服务条款。**
> 工具本身合法,但用户应对采集行为负责。请勿用于:
> - 绕过登录/付费墙采集私有数据
> - 大规模商业爬取(可能违反用户协议或反不正当竞争法)
> - 采集个人隐私信息

---

## 📞 联系方式

- 项目地址: https://github.com/Safeming/DatabaseScraper
- 反馈问题: 提 GitHub Issue

---

## 🙏 致谢

- [Crawl4AI](https://github.com/unclecode/crawl4ai) — AI 驱动的网页爬虫框架
- [Streamlit](https://streamlit.io) — 快速构建数据应用
- [Ollama](https://ollama.com) — 本地 LLM 运行时
- [SQLAlchemy](https://www.sqlalchemy.org) — Python ORM 标杆
