import streamlit as st
import pandas as pd
import os
import re
from src.engine import RedrobRankingEngine

REQUIRED_COLUMNS = ["candidate_id", "rank", "score", "reasoning"]
CANDIDATE_ID_PATTERN = re.compile(r"^CAND_[0-9]{7}$")

st.set_page_config(page_title="Redrob Candidate Ranker", layout="wide", page_icon="🎯")

st.title("🎯 Redrob Candidate Ranker")
st.caption(
    "Fully local, rule-based + lexical-concept ranking engine — no hosted LLM calls, "
    "no GPU, no network during ranking. Safe to use as the hackathon sandbox demo: "
    "upload a small candidate sample below and it runs end-to-end on CPU."
)

if "ranker" not in st.session_state:
    st.session_state.ranker = RedrobRankingEngine()

col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("📝 Job Description")
    jd_box = st.text_area(
        "Used for interface compatibility — the actual scoring rubric is the curated "
        "concept vocabulary in src/engine.py, built directly from job_description.docx.",
        value=(
            "Looking for a Senior AI Engineer to join our founding team. Deep technical depth "
            "in modern ML systems - embeddings, retrieval, ranking, LLMs, fine-tuning. "
            "Comfortable with building evaluation frameworks and custom vector scoring "
            "pipelines. Pune/Noida location preference."
        ),
        height=180,
    )

with col2:
    st.subheader("📥 Candidate Sample")
    source_file = st.file_uploader(
        "Upload a candidate pool sample (.jsonl, .jsonl.gz, .json) — the sandbox spec only "
        "requires this to run on a small sample (≤100 candidates).",
        type=["jsonl", "gz", "json"],
    )

run = st.button("⚡ Run Ranking", type="primary")

if run:
    if not source_file:
        st.error("Please upload a candidate sample file first.")
    else:
        suffix = source_file.name.split(".")[-1]
        temp_path = f"_temp_upload.jsonl.gz" if source_file.name.endswith(".gz") else f"_temp_upload.{suffix}"
        with open(temp_path, "wb") as f:
            f.write(source_file.getbuffer())

        status = st.empty()
        status.info("Scoring candidates locally (CPU, no network calls)...")

        try:
            chunks = list(st.session_state.ranker.process_large_scale_dataset(jd_box, temp_path, chunk_size=5000))
            if not chunks:
                st.error("No valid candidates found in the uploaded file.")
            else:
                full_df = pd.concat(chunks, ignore_index=True)
                full_df = full_df[full_df["candidate_id"].notna()].copy()
                full_df["candidate_id"] = full_df["candidate_id"].astype(str)
                full_df = full_df.drop_duplicates(subset="candidate_id", keep="first")
                full_df = full_df.sort_values(by=["score", "candidate_id"], ascending=[False, True]).reset_index(drop=True)

                n = min(100, len(full_df))
                top = full_df.head(n).copy()
                top["rank"] = range(1, n + 1)
                result = top[REQUIRED_COLUMNS]

                status.success(f"Done. Scored {len(full_df)} candidates, showing top {n}.")

                k1, k2, k3 = st.columns(3)
                k1.metric("Candidates scored", f"{len(full_df):,}")
                k2.metric("Shown", n)
                k3.metric("Top score", f"{result['score'].max():.4f}" if n else "—")

                st.dataframe(result, use_container_width=True)

                csv_bytes = result.to_csv(index=False).encode("utf-8")
                st.download_button(
                    "📥 Download CSV",
                    data=csv_bytes,
                    file_name="ranking_sample_output.csv",
                    mime="text/csv",
                )
        except Exception as e:
            st.error(f"Ranking failed: {e}")
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)
