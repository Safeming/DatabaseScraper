import os
import streamlit as st
import pandas as pd
from database import (
    init_db, list_jobs, get_job, get_results_for_job,
    get_job_dataframe, export_to_excel, delete_job, update_job_status
)

init_db()

st.set_page_config(page_title="任务历史", page_icon="📋")

st.markdown("""
<style>
    [data-testid="stToolbar"] {display: none !important;}
    .stDeployButton {display: none !important;}
    #MainMenu {display: none !important;}
    header {visibility: hidden !important;}
</style>
""", unsafe_allow_html=True)

st.markdown("### 任务历史")
st.markdown("查看所有采集任务的执行记录和数据")
st.markdown("---")

# ─── Filters ───
col1, col2 = st.columns(2)
with col1:
    status_filter = st.selectbox("状态筛选", ["全部", "completed", "failed", "running", "pending"])
with col2:
    limit = st.number_input("显示条数", min_value=5, max_value=200, value=20)

if status_filter == "全部":
    jobs = list_jobs(limit=limit)
else:
    jobs = list_jobs(status=status_filter, limit=limit)

if not jobs:
    st.info("暂无任务记录")
else:
    job_df = pd.DataFrame(jobs)[["id", "name", "status", "method", "created_at", "completed_at"]]
    job_df.columns = ["ID", "任务名", "状态", "方式", "创建时间", "完成时间"]
    st.dataframe(job_df, width="stretch")

    # ─── Job Detail ───
    st.markdown("---")
    st.markdown("#### 任务详情")

    selected_id = st.number_input("输入任务 ID 查看详情", min_value=1, value=jobs[0]["id"])
    job = get_job(selected_id)

    if job:
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("状态", job["status"])
        with col2:
            st.metric("抓取方式", job["method"])
        with col3:
            st.metric("LLM", f"{job['llm_provider']}/{job['llm_model']}")

        if job.get("schedule_cron"):
            st.info(f"定时调度: {job['schedule_cron']}")

        # Results per page
        results = get_results_for_job(selected_id)
        if results:
            st.markdown("**各页抓取结果：**")
            res_df = pd.DataFrame(results)[["url", "page_number", "status", "row_count", "error_message"]]
            res_df.columns = ["URL", "页码", "状态", "提取行数", "错误"]
            st.dataframe(res_df, width="stretch")

        # Data preview
        df = get_job_dataframe(selected_id)
        if not df.empty:
            st.markdown(f"**数据预览（共 {len(df)} 行）：**")
            st.dataframe(df, width="stretch")

            # Download buttons
            col1, col2, col3 = st.columns(3)
            with col1:
                st.download_button(
                    "下载 CSV",
                    df.to_csv(index=False),
                    file_name=f"job_{selected_id}.csv",
                    mime="text/csv"
                )
            with col2:
                st.download_button(
                    "下载 JSON",
                    df.to_json(orient="records", indent=2, force_ascii=False),
                    file_name=f"job_{selected_id}.json",
                    mime="application/json"
                )
            with col3:
                export_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "exports")
                os.makedirs(export_dir, exist_ok=True)
                excel_path = os.path.join(export_dir, f"job_{selected_id}.xlsx")
                if st.button("导出 Excel"):
                    export_to_excel(selected_id, excel_path)
                    st.success(f"已导出: {excel_path}")
        else:
            st.warning("该任务暂无提取数据")

        # Actions
        st.markdown("---")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("重新执行"):
                update_job_status(selected_id, "pending")
                st.success("任务已重新加入队列")
                st.rerun()
        with col2:
            if st.button("删除任务", type="secondary"):
                delete_job(selected_id)
                st.success("任务已删除")
                st.rerun()
    else:
        st.warning(f"未找到 ID 为 {selected_id} 的任务")
