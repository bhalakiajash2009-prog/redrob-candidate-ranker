# Redrob Hackathon — Candidate Ranking Engine

A fully local, rule-based + lexical-concept ranker for the Intelligent
Candidate Discovery & Ranking Challenge. No hosted LLM/embedding API calls,
no GPU, no network access during ranking — verified end-to-end against the
real 100,000-candidate pool.

## Quickstart

```bash
pip install -r requirements.txt
python main.py --candidates ./data/candidates.jsonl --out ./submission.csv
python validate_submission.py ./submission.csv
python export_xlsx.py --csv ./submission.csv --out ./ranked_candidates.xlsx
```

Runtime: 66-104s across repeated runs of the full 100,000-candidate pool
(CPU only, no GPU, no network), measured — not estimated — across multiple
runs on commodity hardware, with normal run-to-run variance. Well inside
the 5-minute / 16GB / CPU-only / no-network compute constraint in
`submission_spec.docx` Section 3.

## Architecture

```
main.py          CLI entrypoint — streams candidates.jsonl[.gz] in chunks,
                 scores, sorts, self-audits, writes the top-100 CSV.
app.py           Streamlit demo / sandbox — same engine, small-sample upload.
src/engine.py    The ranking engine itself. Single source of truth for all
                 scoring logic, concept vocabularies, and trap detection.
```

## How it scores a candidate

Five components combine into a single 0-1 score:

1. **Semantic fit (55%)** — lexical match against a curated AI/ML concept
   vocabulary (embeddings/retrieval, vector DB & hybrid search, ranking &
   recsys, LLM systems, eval frameworks, production ML), read from the
   candidate's full career history — not just their current title — so a
   plain-language candidate who actually built relevant systems scores
   correctly even without buzzwords.
2. **Experience fit (25%)** — a trapezoidal curve centered on the JD's
   stated 5-9y band, peaking at 6-8y, with a gentle (not punitive) taper
   outside it.
3. **Location fit (12%)** — Pune/Noida prioritized per the JD, with
   graduated credit for Tier-1 Indian cities and relocation willingness.
4. **Notice-period fit (8%)** — sub-30-day preferred per the JD.
5. **Behavioral multiplier** — a multiplicative (not additive) modifier on
   recruiter responsiveness, platform activity recency, and profile
   completeness, so a perfect-on-paper but inactive/unresponsive candidate
   is meaningfully down-weighted rather than nudged by a fraction of a point.

## Trap defense

Two independent layers sit on top of the base score, both calibrated against
the real dataset (not guessed):

**Honeypots → score capped at 0.02.** Two standalone-sufficient signals:
- A career-history entry predates the named company's real founding year
  (e.g. joining Krutrim or Sarvam AI before they existed). Verified: this
  single check flags candidates almost exactly matching the spec's stated
  "~80 honeypots." Fictional filler companies (Wayne Enterprises, Hooli,
  etc.) are explicitly excluded from this check — they have no real
  founding year and are noise-population placeholders, not honeypot signal.
- A majority of listed skills rated "expert" with ~0 months of use.

Weaker structural contradictions (overlapping employment, invalid
chronologies, scrambled title/description pairs) require 2+ together to
corroborate, since any single one alone produced too many false positives
against real data.

**Hard disqualifiers → score capped at 0.12.** An exact-match non-technical
title blacklist (verified against the dataset's confirmed 47-value title
vocabulary), pure-research-only careers, consulting-only careers, recent
LangChain-wrapper-only "AI experience" with no earlier ML production
history, CV/speech/robotics-only backgrounds with no NLP exposure, and an
AI-hobbyist detector that catches candidates whose AI vocabulary appears
only via hedging language ("I've been keeping up with AI/ML at a
self-learner level... but I haven't done it in a professional capacity
yet" — found by mining the real dataset, this exact sentence covers 25% of
all 100,000 candidates).

## Reasoning quality

Every reasoning string is built compositionally from facts true of that
specific candidate — title, company, years of experience, matched concept
buckets, real skill names pulled verbatim from their own skills array,
location, notice period, and any flags raised. No fixed templates, no
invented skills.

## Self-audit

`main.py` prints honeypot and disqualifier counts for the full pool and the
submitted top 100 before writing the CSV, and hard-fails if the top-100
honeypot rate would exceed the spec's 10% disqualification threshold.

## Compute environment

CPU only. No GPU. No network calls during ranking (verified by code
inspection — there is no `requests`, `urllib`, or any HTTP client import
anywhere in the ranking path). See `submission_metadata.yaml` for the
specific machine this was run and timed on.
