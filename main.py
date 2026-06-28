"""
Redrob Hackathon — Ranking CLI

Reproduce with:
    python main.py --candidates ./data/candidates.jsonl.gz --out ./your_participant_id.csv

Runs fully offline: no hosted LLM calls, no GPU, no network. Matches
submission_spec.docx Section 3 compute constraints by construction —
there is no code path here that touches a network socket.
"""

import argparse
import os
import re
import sys
import time

import pandas as pd

from src.engine import RedrobRankingEngine

REQUIRED_COLUMNS = ["candidate_id", "rank", "score", "reasoning"]
CANDIDATE_ID_PATTERN = re.compile(r"^CAND_[0-9]{7}$")


def parse_args():
    p = argparse.ArgumentParser(description="Redrob hackathon candidate ranker")
    p.add_argument("--candidates", default="data/candidates.jsonl.gz",
                    help="Path to candidates.jsonl or candidates.jsonl.gz")
    p.add_argument("--out", default="submission.csv",
                    help="Output CSV path. RENAME to your registered participant ID before final upload "
                         "(validate_submission.py checks the filename stem).")
    p.add_argument("--jd-file", default=None,
                    help="Optional path to a job description text file (defaults to the bundled JD).")
    p.add_argument("--chunk-size", type=int, default=5000)
    return p.parse_args()


DEFAULT_JD = """
Looking for a Senior AI Engineer to join our founding team. Deep technical depth in modern
ML systems - embeddings, retrieval, ranking, LLMs, fine-tuning. Comfortable with building
evaluation frameworks and custom vector scoring pipelines. Pune/Noida location preference.
"""


def main():
    args = parse_args()
    start_time = time.time()

    if not os.path.exists(args.candidates):
        print(f"[ERROR] Candidate dataset not found at '{args.candidates}'.")
        sys.exit(1)

    jd_text = DEFAULT_JD
    if args.jd_file:
        with open(args.jd_file, "r", encoding="utf-8") as f:
            jd_text = f.read()

    print(f"[INFO] Ranking '{args.candidates}' (CPU-only, no network, no GPU)...")
    ranker = RedrobRankingEngine()

    chunks = []
    for i, chunk_df in enumerate(ranker.process_large_scale_dataset(jd_text, args.candidates, chunk_size=args.chunk_size)):
        chunks.append(chunk_df)
        print(f"  chunk {i + 1}: {len(chunk_df)} candidates scored")

    if not chunks:
        print("[ERROR] No valid candidates were scored. Check the input file.")
        sys.exit(1)

    full_df = pd.concat(chunks, ignore_index=True)

    # ---- Safety checks before we ever write a CSV ----
    before = len(full_df)
    full_df = full_df[full_df["candidate_id"].notna()].copy()
    full_df["candidate_id"] = full_df["candidate_id"].astype(str)
    full_df = full_df[full_df["candidate_id"].str.match(CANDIDATE_ID_PATTERN)]
    full_df = full_df.drop_duplicates(subset="candidate_id", keep="first")
    dropped = before - len(full_df)
    if dropped:
        print(f"[WARN] Dropped {dropped} rows with missing/invalid/duplicate candidate_id.")

    full_df = full_df.sort_values(by=["score", "candidate_id"], ascending=[False, True]).reset_index(drop=True)

    if len(full_df) < 100:
        print(f"[ERROR] Only {len(full_df)} valid-scored candidates available; need >= 100 for a top-100 submission.")
        sys.exit(1)

    top100 = full_df.head(100).copy()
    top100["rank"] = range(1, len(top100) + 1)
    submission = top100[REQUIRED_COLUMNS]

    # ---- Self-audit: honeypot / disqualifier rate, printed for transparency ----
    # The spec uses honeypot rate in the top 100 as a Stage 3 disqualification
    # filter (>10% = disqualified). We check it ourselves before submitting.
    n_honeypot_pool = int((full_df["score"] == 0.02).sum())
    n_honeypot_top100 = int((top100["score"] == 0.02).sum())
    n_disqualified_top100 = int(top100["reasoning"].str.contains("ranked low despite", na=False).sum())
    print("\n[SELF-AUDIT]")
    print(f"  Honeypots detected in full pool : {n_honeypot_pool}")
    print(f"  Honeypots in submitted top 100   : {n_honeypot_top100}  (must be <= 10 to avoid disqualification)")
    print(f"  Hard-disqualified in top 100     : {n_disqualified_top100}  (should be 0)")
    if n_honeypot_top100 > 10:
        print("  [ERROR] Honeypot rate in top 100 exceeds the 10% disqualification threshold!")
        sys.exit(1)

    # ---- Final structural assertions matching validate_submission.py ----
    assert len(submission) == 100, "submission must have exactly 100 rows"
    assert submission["candidate_id"].is_unique, "duplicate candidate_id in submission"
    assert sorted(submission["rank"].tolist()) == list(range(1, 101)), "ranks must be exactly 1..100"
    assert submission["candidate_id"].str.match(CANDIDATE_ID_PATTERN).all(), "candidate_id format violation"

    submission.to_csv(args.out, index=False)

    elapsed = time.time() - start_time
    print("\n--------------------------------------------------------------")
    print(f"[DONE] Wrote {args.out} ({len(submission)} rows) in {elapsed:.1f}s")
    print("Reminder: rename the output file to your registered participant ID")
    print("before uploading (e.g. team_xxx.csv), and run validate_submission.py.")
    print("--------------------------------------------------------------")


if __name__ == "__main__":
    main()
