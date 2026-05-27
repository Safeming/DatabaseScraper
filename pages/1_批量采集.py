import streamlit as st
import shutil
import subprocess
import os
import threading
from database import init_db, create_job, list_jobs, get_results_for_job, get_job
from pipeline import execute_pipeline

init_db()

st.set_page_config(page_title="批量采集", page_icon="📦")

st.markdown("""
<style>
    [data-testid="stToolbar"] {display: none !important;}
    .stDeployButton {display: none !important;}
    #MainMenu {display: none !important;}
    header {visibility: hidden !important;}
</style>
""", unsafe_allow_html=True)

st.markdown("### 批量采集")
st.markdown("支持多 URL 输入、自动翻页、定时调度")
st.markdown("---")


def get_ollama_models():
    ollama_cmd = shutil.which("ollama")
    if not ollama_cmd:
        for p in [
            os.path.expandvars(r"%LOCALAPPDATA%\Programs\Ollama\ollama.exe"),
            r"C:\Users\admin\AppData\Local\Programs\Ollama\ollama.exe",
        ]:
            if os.path.isfile(p):
                ollama_cmd = p
                break
    if not ollama_cmd:
        return []
    try:
        result = subprocess.run(
            [ollama_cmd, "list"], capture_output=True, text=True, check=True
        )
        return [
            line.split(" ")[0] for line in result.stdout.strip().split("\n")
            if line and "NAME" not in line and "embed" not in line.lower()
        ]
    except Exception:
        return []


with st.form("batch_form"):
    job_name = st.text_input("任务名称", value="批量采集任务")

    urls_text = st.text_area(
        "目标 URL（每行一个）",
        height=120,
        placeholder="https://example.com/page1\nhttps://example.com/page2"
    )

    query = st.text_area(
        "提取字段",
        height=60,
        placeholder="title, price, description"
    )

    col1, col2 = st.columns(2)
    with col1:
        method = st.selectbox("抓取方式", ["Crawl4AI", "Selenium"])
        llm_provider = st.selectbox("LLM 提供商", ["Ollama", "Sambanova"])

    with col2:
        follow_pagination = st.checkbox("自动翻页", value=False)
        max_pages = st.number_input("最大翻页数", min_value=1, max_value=50, value=5)

    if llm_provider == "Ollama":
        models = get_ollama_models()
        llm_model = st.selectbox("Ollama 模型", models if models else ["未检测到模型"])
    else:
        llm_model = st.selectbox("Sambanova 模型", [
            "DeepSeek-R1-Distill-Llama-70B", "DeepSeek-V3-0324",
            "DeepSeek-R1", "Qwen3-32B", "QwQ-32B"
        ])

    schedule_option = st.selectbox("调度方式", [
        "立即执行", "每1小时", "每6小时", "每12小时", "每24小时", "自定义 Cron"
    ])

    custom_cron = None
    if schedule_option == "自定义 Cron":
        custom_cron = st.text_input("Cron 表达式", placeholder="0 */6 * * *")

    export_excel = st.checkbox("完成后自动导出 Excel", value=True)

    submitted = st.form_submit_button("提交任务")

if submitted:
    urls = [u.strip() for u in urls_text.strip().split("\n") if u.strip()]

    if not urls:
        st.error("请输入至少一个 URL")
    elif not query.strip():
        st.error("请输入提取字段")
    else:
        cron_map = {
            "立即执行": None,
            "每1小时": "0 */1 * * *",
            "每6小时": "0 */6 * * *",
            "每12小时": "0 */12 * * *",
            "每24小时": "0 0 * * *",
            "自定义 Cron": custom_cron,
        }
        schedule_cron = cron_map.get(schedule_option)

        pipeline_config = {
            "clean": {"remove_links": False},
            "store": {"export_excel": export_excel},
        }

        job_id = create_job(
            name=job_name,
            urls=urls,
            query=query.strip(),
            method=method,
            llm_provider=llm_provider,
            llm_model=llm_model,
            follow_pagination=follow_pagination,
            max_pages=max_pages,
            schedule_cron=schedule_cron,
            pipeline_config=pipeline_config,
        )

        st.success(f"任务已提交！Job ID: {job_id}")
        if schedule_cron:
            st.info(f"定时任务已设置: {schedule_cron}，需要运行 scheduler.py 来执行定时任务。")
        else:
            st.info("任务正在后台执行，请稍候刷新查看结果...")
            job = get_job(job_id)
            thread = threading.Thread(target=execute_pipeline, args=(job,), daemon=True)
            thread.start()

# ─── 活跃任务状态 ───
st.markdown("---")
st.markdown("#### 活跃任务")

active_jobs = list_jobs(status="running") + list_jobs(status="pending")

if not active_jobs:
    st.info("当前没有活跃任务")
else:
    for job in active_jobs:
        results = get_results_for_job(job["id"])
        done = sum(1 for r in results if r["status"] in ("stored", "failed"))
        total = len(results) if results else "?"

        status_emoji = "🔄" if job["status"] == "running" else "⏳"
        st.markdown(
            f"{status_emoji} **{job['name']}** (#{job['id']}) — "
            f"状态: {job['status']} — 进度: {done}/{total} 页"
        )

if st.button("刷新状态"):
    st.rerun()
