import os
import re
import csv
import random
import string
import shutil
import logging
import subprocess
import validators
import pandas as pd
import streamlit as st
from typing import List
from datetime import datetime
from scraper import get_url_md
from urllib.parse import urlparse
from generate_response import generate_response, generate_response2, classify_website, adapt_fields_for_page
from categories import CATEGORY_TEMPLATES, get_category_info
from database import init_db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

init_db()

def random_string(length=8):
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))


def parse_llm_csv(response: str) -> pd.DataFrame:
    """
    Parses a string containing CSV content (possibly mixed with unwanted text)
    into a cleaned pandas DataFrame.

    - Detects the header (first line with a comma, or first non-empty line).
    - Normalizes each data row to the number of columns in the header.
    - Ignores non-CSV lines after the header.
    """
    # Remove markdown code block markers
    response = re.sub(r'```(?:csv|CSV)?\s*\n?', '', response)
    response = re.sub(r'```\s*$', '', response, flags=re.MULTILINE)

    lines = [line.strip() for line in response.splitlines() if line.strip()]

    if not lines:
        return pd.DataFrame()

    # Find the header: first line that contains a comma (unquoted)
    header_line = None
    for line in lines:
        stripped = line.strip('"').strip("'")
        if ',' in stripped:
            header_line = stripped
            break

    if not header_line:
        header_line = lines[0]

    header = next(csv.reader([header_line]))
    num_columns = len(header)

    # Find where header was in original lines
    header_idx = 0
    for i, line in enumerate(lines):
        stripped = line.strip('"').strip("'")
        if stripped == header_line:
            header_idx = i
            break

    data_rows: List[List[str]] = []

    for line in lines[header_idx + 1:]:
        if num_columns > 1 and ',' not in line:
            continue  # skip likely non-CSV content
        row = next(csv.reader([line]))
        # Normalize row length
        if len(row) > num_columns:
            row = row[:num_columns]
        elif len(row) < num_columns:
            row += [None] * (num_columns - len(row))
        data_rows.append(row)

    return pd.DataFrame(data_rows, columns=header)


# Generate a safe file name from the URL
def generate_filename_from_url(url: str, fallback: str) -> str:
    if url:
        try:
            parsed_url = urlparse(url)
            netloc = parsed_url.netloc or "download"
            
            # Remove 'www.' and domain suffixes
            base = netloc.replace("www.", "")
            base = re.split(r'\.[a-z]+$', base)[0]  # Remove final .com, .net, etc.

            # Get path and clean it
            path = parsed_url.path.strip("/").replace("/", "_")
            name = f"{base}_{path}" if path else base

            # Remove unsafe characters
            name = re.sub(r'[^a-zA-Z0-9_-]', '', name)
            return f"{name}_data"
        except Exception:
            pass
    return f"{fallback}"


def llm_response_to_df(response, url=None, load=False):
    """Parses LLM response containing CSV-like content and displays it as a DataFrame with download options."""
    try:
        if not load:
            df = parse_llm_csv(response)
            if df.empty:
                raise ValueError("⚠️ No valid content to convert to DataFrame.")

        else :
            df = pd.DataFrame.from_dict(response)        

        # Show DataFrame
        st.dataframe(df)

        if not load:
            # Save to session state
            st.session_state.messages.append({
                "role": "assistant",
                "content": response,
                "df": df.to_dict(),
                "url": url
            })

        # Generate timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_name = generate_filename_from_url(url, fallback=timestamp)


        with st.expander("DownLoad the Data : ") :
            st.download_button("📥 Download CSV", df.to_csv(index=False), file_name=f"{file_name}.csv", mime="text/csv", key=f"csv_{random_string(10)}")
            st.download_button("📥 Download JSON", df.to_json(orient="records", indent=2), file_name=f"{file_name}.json", mime="application/json", key=f"json_{random_string(10)}")
            st.download_button("📥 Download Markdown", df.to_markdown(index=False), file_name=f"{file_name}.md", mime="text/markdown", key=f"md_{random_string(10)}")
            st.download_button("📥 Download Text", df.to_string(index=False), file_name=f"{file_name}.txt", mime="text/plain", key=f"text_{random_string(10)}")
            st.download_button("📥 Download HTML", df.to_html(index=False, escape=False), file_name=f"{file_name}.html", mime="text/html", key=f"html_{random_string(10)}")

        # ─── 一键存入数据库 (load=True 时也渲染,确保重跑后按钮还在) ───
        _render_save_to_db(df, url)

    except Exception as e:
        # Save error to session and show on screen
        if not load:
            st.session_state.messages.append({
                "role": "assistant",
                "content": response,
                "error": f"❌ Failed to parse CSV output: {e}"
            })

        st.error(f"❌ Failed to parse CSV output: {e}")


def _render_save_to_db(df, url):
    """渲染"存入数据库"折叠区:让用户选类别,把当前 df 入库到 MySQL 对应专属表。"""
    import hashlib
    from categories import CATEGORY_TEMPLATES, get_category_info
    from database import create_job, add_result, update_result, update_job_status, store_extracted_rows

    # 用 url + 行数 + 第一行内容 算稳定 key,避免 Streamlit 重跑时按钮失效
    sig = f"{url or 'no-url'}|{len(df)}|{str(df.iloc[0].to_dict()) if len(df) else ''}"
    sig_hash = hashlib.md5(sig.encode("utf-8")).hexdigest()[:10]

    with st.expander("💾 存入数据库"):
        st.caption("把当前结果按类别保存到 MySQL,books/quotes/products 等会进入对应专属表。")

        cat_options = [(k, v["name_zh"]) for k, v in CATEGORY_TEMPLATES.items()]
        cat_labels = [f"{name} ({code})" for code, name in cat_options]

        # 默认从 session 取上次智能识别的类别
        default_idx = 0
        last_cat = st.session_state.get("last_category")
        if last_cat:
            for i, (code, _) in enumerate(cat_options):
                if code == last_cat:
                    default_idx = i
                    break

        col1, col2 = st.columns([2, 1])
        chosen = col1.selectbox(
            "选择类别",
            cat_labels,
            index=default_idx,
            key=f"cat_sel_{sig_hash}",
            help="智能识别已自动设定;手动模式可在此处选择",
        )
        category_code = cat_options[cat_labels.index(chosen)][0]

        info = get_category_info(category_code)
        col2.markdown(f"**字段**:`{info['fields']}`")

        # 已经入库过的标记(避免重复入库)
        saved_flag_key = f"saved_{sig_hash}"
        if st.session_state.get(saved_flag_key):
            st.info(f"✅ 此结果已保存(Job ID: {st.session_state[saved_flag_key]}),可在数据浏览页查看。")
            return

        save_btn = st.button("💾 保存到数据库", key=f"save_{sig_hash}")
        if save_btn:
            try:
                rows = df.to_dict(orient="records")
                job_id = create_job(
                    name=f"快速抓取-{category_code}",
                    urls=[url] if url else [],
                    query=info["fields"],
                    method="Crawl4AI",
                    llm_provider="Ollama",
                    llm_model="manual",
                    follow_pagination=False,
                    pipeline_config={"source": "app.py 主页"},
                    category_code=category_code,
                )
                update_job_status(job_id, "running")
                result_id = add_result(job_id, url or "(no url)", page_number=1)
                inserted = store_extracted_rows(job_id, result_id, rows, category=category_code)
                update_result(result_id, status="stored", row_count=inserted)
                update_job_status(job_id, "completed")

                if inserted > 0:
                    st.session_state[saved_flag_key] = job_id
                    st.success(f"✅ 已入库 {inserted} 行到 **{info['name_zh']}** 类别(Job ID: {job_id})")
                    st.caption("到 [数据浏览] 或 [统计仪表盘] 页查看")
                else:
                    st.warning(
                        "⚠️ 入库 0 行。可能字段名不匹配(如 LLM 输出 'name' 但 books 类期望 'title'),"
                        "或核心字段(如 title)为空。下载 CSV 检查后改用其他类别试试。"
                    )
            except Exception as e:
                st.error(f"❌ 入库失败: {e}")
                import traceback
                with st.expander("详细错误"):
                    st.code(traceback.format_exc())


def get_available_models():
    """Fetches the installed Ollama models, excluding 'NAME' and models containing 'embed'."""
    try:
        ollama_cmd = shutil.which("ollama")
        if not ollama_cmd:
            common_paths = [
                os.path.expandvars(r"%LOCALAPPDATA%\Programs\Ollama\ollama.exe"),
                r"C:\Program Files\Ollama\ollama.exe",
                r"C:\Users\admin\AppData\Local\Programs\Ollama\ollama.exe",
            ]
            for p in common_paths:
                if os.path.isfile(p):
                    ollama_cmd = p
                    break
        if not ollama_cmd:
            ollama_cmd = "ollama"

        result = subprocess.run([ollama_cmd, "list"], capture_output=True, text=True, check=True)
        models = [
            line.split(" ")[0] for line in result.stdout.strip().split("\n")
            if line and "NAME" not in line and "embed" not in line.lower()
        ]
        return models
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        logger.warning(f"Error fetching Ollama models: {e}")
        return []

def remove_tags(text): 
    return re.sub(r"^.*?</think>", "", text, flags=re.DOTALL).strip()

# Fetch available models
available_models = get_available_models()

from ui_theme import apply_theme, page_header
apply_theme(page_title="AI-Scraper", page_icon="▣")

page_header(
    eyebrow="quick / scrape",
    title="AI-Scraper",
    subtitle="输入一个 URL,AI 自动识别网站类型并提取结构化数据。批量任务请去『批量采集』页。",
    active_stage="scrape",
)

with st.sidebar:
    st.header("Settings :")

    # User selects the model Provider
    llm_provider = st.selectbox("Select LLM Provider:", ['Sambanova', 'Ollama'], index=0)

    if llm_provider == 'Ollama' :
        if available_models:
            selected_model = st.selectbox("Select an Ollama model:", available_models, index=0)
        else:
            st.warning("No Ollama models found. Run `ollama pull <model_name>` first.")
            selected_model = None

    else :
        llm_name = st.selectbox("Enter LLM Name:", ['DeepSeek-R1-Distill-Llama-70B', 'DeepSeek-V3-0324', 'DeepSeek-R1', 'Qwen3-32B', 'QwQ-32B'], index=0)
        # api_key = st.text_input("Enter Sambanova API Key", type="password", value=os.getenv("API_KEY"))

    # 提取模式：智能识别 vs 手动指定
    extract_mode = st.radio(
        "提取模式",
        ["🤖 智能识别（AI 自动选字段）", "✏️ 手动指定字段"],
        index=0,
        help="智能识别：AI 自动判断网站类型并选择默认字段，提交后可在结果中查看；手动指定：自己填写要提取的字段"
    )

    if extract_mode.startswith("🤖"):
        query = ""
        st.caption("AI 将自动识别网站类型并选择字段，无需手动输入")
        with st.expander("支持的网站类别"):
            for key, val in CATEGORY_TEMPLATES.items():
                st.markdown(f"- **{val['name_zh']}** ({key}) — `{val['fields']}`")
    else:
        query = st.text_area("What do you want to Extract (fields):", height=80)

    url = st.text_area("Enter the URL:", height=75)
    method = st.selectbox("Select Scraping Method:", ["Crawl4AI", "Selenium"])
    start_button = st.button("Start Scraping")

    if st.button("Clear Chat"):
        st.session_state.messages = []
        st.rerun()

    with st.expander("Scraping explanation"):
        st.info("""
##### There're 2 method to scrap the page: 
    - Crawl4AI : AI driven Scrapping but Slower.
    - Selenium : Simple Scraping but Faster.
""")


# Initialize variables
results = []

if "messages" not in st.session_state:
    st.session_state.messages = []

MAX_MESSAGES = 40

# Display chat history
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        if "df" in message:
            llm_response_to_df(message["df"], url=message.get("url", None), load=True)
        elif 'error' in message:
            st.error(message["error"])
            with st.expander("See LLM Response"): 
                st.code(message["content"], language='markdown')
        else : 
            st.markdown(message["content"])

# Stop if max messages are reached
if len(st.session_state.messages) >= MAX_MESSAGES:
    st.info("Notice: The maximum message limit has been reached. Clear the chat to continue.")
    st.session_state.messages = st.session_state.messages[-20:]
else:
    if start_button:
        url = url.strip()
        query = query.strip()
        is_smart_mode = extract_mode.startswith("🤖")

        if not is_smart_mode and not query:
            st.error("请输入要提取的字段，或切换到智能识别模式。")
        elif not is_smart_mode and len(query) > 500:
            st.error("Query is too long. Please keep it under 500 characters.")
        elif not url:
            st.error("Please enter the target URL.")
        elif len(url) > 2000:
            st.error("URL is too long. Please check the URL.")
        elif not validators.url(url):
            st.error("Please enter a valid URL (must start with http:// or https://).")
        else:
            user_msg = (query if query else "[智能识别模式]") + f"\n -> From : {url}"
            st.session_state.messages.append({"role": "user", "content": user_msg})
            with st.chat_message("user"):
                st.markdown(user_msg)

            # Scraping Process
            with st.chat_message("assistant"):
                try:
                    with st.spinner("Processing..."):
                        try:

                            with st.spinner("Scraping data..."):
                                scraped_data = get_url_md(url, method)

                                logger.info(f"Data scraped successfully from {url}")

                                st.markdown(f"-> Scraping Data from {url}:")
                                with st.expander("Scraped data Sample"):
                                    st.code(scraped_data[:1000], language='markdown')

                        except Exception as e:
                            st.session_state.messages.append({"role": "assistant", "content": f"Error: {e}"})
                            st.rerun()

                        # 智能识别：AI 分类网站并选择默认字段
                        if is_smart_mode:
                            with st.spinner("🤖 AI 正在识别网站类型..."):
                                model_for_classify = selected_model if llm_provider == "Ollama" else llm_name
                                category, default_fields = classify_website(
                                    scraped_data,
                                    llm_provider=llm_provider,
                                    llm_model=model_for_classify
                                )
                                cat_info = get_category_info(category)

                            # 仅在 general/forum 或字段过少时才适配,避免破坏已设计好的模板
                            ADAPT_CATEGORIES = {"general", "forum"}
                            if category in ADAPT_CATEGORIES or len(default_fields.split(",")) < 3:
                                with st.spinner("🤖 AI 正在适配页面字段..."):
                                    adapted_fields = adapt_fields_for_page(
                                        scraped_data, category, default_fields,
                                        llm_provider=llm_provider, llm_model=model_for_classify
                                    )
                            else:
                                adapted_fields = default_fields

                            if adapted_fields != default_fields:
                                st.success(
                                    f"✅ 识别为 **{cat_info['name_zh']}** ({category}) — "
                                    f"默认字段: `{default_fields}` → 适配后: `{adapted_fields}`"
                                )
                            else:
                                st.success(
                                    f"✅ 识别为 **{cat_info['name_zh']}** ({category}) — "
                                    f"使用字段: `{adapted_fields}`"
                                )
                            query = adapted_fields
                            # 把识别到的类别存入 session,让"存入数据库"按钮默认选中此类
                            st.session_state.last_category = category

                        try :

                            with st.spinner("Extracting Data as CSV..."):
                                llm_response = ""
                                response = ""

                                if llm_provider == 'Ollama' :
                                    llm_response = generate_response(selected_model, query, scraped_data)

                                    with st.expander("See LLM Response"): 
                                        st.code(llm_response[:1000], language='markdown')
                                        
                                    response = remove_tags(llm_response)

                                else : 
                                    llm_response = generate_response2(query, scraped_data, llm_name)
                                    response = remove_tags(llm_response)
                                    # Scraped URL : '{url}' | LLM Name: {llm_name}
                                    with st.expander("See LLM Response"): 
                                        st.code(llm_response[:1000], language='markdown')

                                llm_response_to_df(remove_tags(llm_response), url)

                        except Exception as e:
                            st.session_state.messages.append({"role": "assistant", "content": llm_response, 'error': f"Error: {e}"})
                            st.rerun()

                except Exception as e:
                    st.session_state.messages.append({"role": "assistant", "content": f"Error: {e}"})
                    st.rerun()
    else:
        pass
