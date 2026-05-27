# RPA 数据自动化采集工具

基于 LLM + Web Scraping 的智能数据提取系统。输入 URL 和需要的字段，自动抓取网页内容并输出结构化数据。

## 功能特性

- **智能提取** — 用自然语言描述字段，LLM 自动从网页中提取结构化数据
- **双引擎抓取** — Crawl4AI + Selenium，自动降级容错
- **批量采集** — 多 URL 同时提交，后台并行执行
- **自动翻页** — 检测分页链接，支持最多 50 页连续采集
- **定时调度** — 支持 Cron 表达式，周期性自动执行
- **数据入库** — SQLite 持久化存储，自动去重
- **多格式导出** — CSV、JSON、Excel、Markdown、HTML

## 系统架构

```
用户输入 URL + 字段
       ↓
┌─────────────────────────────────┐
│  Streamlit Web UI               │
│  (快速抓取 / 批量采集 / 任务历史) │
└──────────────┬──────────────────┘
               ↓
┌──────────────────────────────────┐
│  Pipeline 流程编排引擎            │
│  抓取 → 清洗 → LLM提取 → 入库    │
└──────────────┬───────────────────┘
               ↓
┌──────────────────────────────────┐
│  数据持久层 (SQLite + Excel)      │
└──────────────────────────────────┘
```

## 环境要求

- Python 3.10+（推荐使用 Conda）
- Google Chrome 浏览器（Selenium 需要）
- Ollama（本地 LLM，可选）或 Sambanova API Key（云端 LLM）

## 安装配置

### 1. 创建 Conda 环境

```bash
conda create -n scraper python=3.10 -y
conda activate scraper
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

Crawl4AI 额外初始化（如遇到 playwright 相关错误）：

```bash
crawl4ai-setup
playwright install
```

### 3. 配置 LLM

**方式一：Ollama（本地运行，免费）**

1. 下载安装：https://ollama.com/download
2. 拉取模型：
```bash
ollama pull qwen2.5:7b
```

**方式二：Sambanova（云端 API）**

1. 注册获取 API Key：https://cloud.sambanova.ai/apis
2. 编辑项目根目录 `.env` 文件：
```
API_KEY=你的密钥
```

### 4. 启动应用

```bash
python -m streamlit run app.py
```

浏览器访问 http://localhost:8501

## 项目结构

```
AI-Scraper/
├── app.py                  # 主页 - 快速抓取（单 URL 交互式）
├── pages/
│   ├── 1_批量采集.py        # 批量 URL 提交 + 翻页 + 调度
│   └── 2_任务历史.py        # 历史记录查看 + 数据导出
├── pipeline.py             # 流程编排（抓取→清洗→提取→入库→导出）
├── scraper.py              # 网页抓取引擎（Crawl4AI + Selenium）
├── generate_response.py    # LLM 调用与 Prompt 管理
├── database.py             # SQLite 数据层（三表设计）
├── pagination.py           # 翻页检测（HTML + URL 模式）
├── scheduler.py            # 定时调度进程（独立运行）
├── sambanova.py            # Sambanova API 封装
├── assets.py               # User-Agent 列表、浏览器配置
├── start_scheduler.bat     # 一键启动调度器（Windows）
├── requirements.txt        # Python 依赖
├── .env                    # API 密钥配置
├── doc/                    # 文档目录
└── exports/                # Excel 导出目录
```

## 使用说明

### 快速抓取（首页）

1. 侧边栏选择 LLM 提供商和模型
2. 输入要提取的字段（如：`title, price, rating`）
3. 输入目标 URL
4. 选择抓取方式（Crawl4AI 或 Selenium）
5. 点击 "Start Scraping"，等待结果

### 批量采集

1. 进入"批量采集"页面
2. 输入多个 URL（每行一个）
3. 填写提取字段
4. 可选：勾选"自动翻页"并设置最大页数
5. 可选：设置定时调度（每 N 小时 / Cron 表达式）
6. 点击"提交任务"，后台自动执行

### 任务历史

- 查看所有任务的执行状态和结果
- 预览提取的数据
- 导出为 Excel / CSV / JSON
- 支持重新执行和删除任务

### 定时调度（可选）

如需使用定时任务功能，另开终端运行：

```bash
python scheduler.py
```

或双击 `start_scheduler.bat`。

> 注：立即执行的任务不需要启动调度器，提交后自动在后台运行。

## 支持的 LLM 模型

| 提供商 | 模型 | 说明 |
|--------|------|------|
| Ollama | qwen2.5:7b, llama3 等 | 本地运行，免费，需要显存 |
| Sambanova | DeepSeek-R1-Distill-Llama-70B | 云端，推理能力强 |
| Sambanova | DeepSeek-V3-0324 | 云端，速度快 |
| Sambanova | Qwen3-32B / QwQ-32B | 云端，综合能力好 |

## 常见问题

**Q: Crawl4AI 抓取超时怎么办？**
A: 系统会自动降级到 Selenium 抓取，无需手动干预。超时时间默认 120 秒。

**Q: 提取的数据格式不对？**
A: 系统内置后处理修复机制（字段分离修复、去重、格式清理）。如仍有问题，尝试在字段描述中更明确地说明。

**Q: 翻页没有生效？**
A: 确保目标网站有标准的分页链接（如 /page/2/、?page=2、"Next" 按钮）。系统支持多种翻页模式自动检测。

**Q: Ollama 模型列表为空？**
A: 确保 Ollama 已安装并正在运行，且已拉取至少一个模型：`ollama pull qwen2.5:7b`

**Q: Windows 下 Chrome 找不到？**
A: 确保已安装 Google Chrome 浏览器。系统会自动通过 webdriver_manager 下载匹配的 ChromeDriver。

## 技术栈

| 组件 | 技术 |
|------|------|
| Web UI | Streamlit |
| 网页抓取 | Crawl4AI、Selenium、BeautifulSoup |
| LLM 集成 | Ollama（本地）、Sambanova/OpenAI API（云端）|
| 数据存储 | SQLite、pandas、openpyxl |
| 任务调度 | schedule、croniter |
| HTML→Markdown | html2text |
