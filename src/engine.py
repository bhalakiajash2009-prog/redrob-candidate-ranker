"""
Redrob Hackathon — Candidate Ranking Engine
============================================

DESIGN PRINCIPLE (read this before touching anything):
The ranking step makes ZERO network calls and uses ZERO GPU. Per
submission_spec.docx Section 3: "You CANNOT, during the ranking step:
Call hosted LLM APIs. Use GPUs." This engine is a rule-based + lexical
ranker over precomputed structured features, exactly what the spec asks
for: "a small ranker over precomputed features... or compact local models."

Everything here is deterministic and explainable: every score component
traces back to a concrete field in the candidate JSON, and the reasoning
string for each candidate is built from facts that are actually true of
that candidate (never invented skills, never a fixed template).

No external dependencies beyond pandas / numpy (already required upstream).
No model weights to download, no Ollama, no API keys, nothing that can
fail to reproduce in an air-gapped Docker sandbox.
"""

import re
import math
from datetime import datetime, date
from typing import Dict, Any, Generator, List, Tuple, Optional

import numpy as np
import pandas as pd

TODAY = date.today()


def _parse_date(value) -> Optional[date]:
    """Fast scalar date parsing. pd.to_datetime() per-scalar is ~100x slower
    than this at 100K-row scale because of its format-guessing machinery —
    confirmed via profiling. All dates in this dataset are ISO 'YYYY-MM-DD'."""
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d").date()
    except ValueError:
        return None

# ============================================================================
# 1. CONCEPT VOCABULARY — derived directly from job_description.docx
#    "Things you absolutely need" / "would like" / "explicitly do NOT want"
# ============================================================================

MUST_HAVE_CONCEPTS: Dict[str, List[str]] = {
    "embeddings_retrieval": [
        "embedding", "sentence-transformer", "sentence transformer", "bge",
        "e5 embedding", "dense retrieval", "vector search", "semantic search",
        "text embedding", "openai embedding",
    ],
    "vector_db_hybrid_search": [
        "pinecone", "weaviate", "qdrant", "milvus", "opensearch",
        "elasticsearch", "faiss", "vector database", "vector store",
        "hybrid search", "bm25", "hnsw", "ann index", "approximate nearest neighbor",
    ],
    "ranking_recsys": [
        "ranking system", "recommendation system", "recommender system",
        "search ranking", "relevance ranking", "click-through", "ctr prediction",
        "personalization", "feed ranking", "learning to rank", "ltr",
        "query understanding", "search relevance", "matching system",
    ],
    "llm_systems": [
        "large language model", "llm", "fine-tun", "finetun",
        "lora", "qlora", "peft", "prompt engineering", "rag",
        "retrieval augmented generation", "re-ranking", "reranking",
    ],
    "eval_frameworks": [
        "ndcg", "mrr", "map@", "mean average precision", "a/b test",
        "ab test", "offline evaluation", "online evaluation",
        "evaluation framework", "precision@", "recall@", "offline-to-online",
    ],
    "production_ml": [
        # Deliberately AI/ML-specific compounds, NOT generic business words.
        # An earlier version used bare "production", "scale", "shipped to",
        # "real users" — these matched almost any white-collar job description
        # (a Civil Engineer or Marketing Manager naturally uses "production"
        # and "scale") and were a major contributor to non-technical roles
        # ranking too high. Verified by direct inspection of real output.
        "ml in production", "model serving", "production machine learning",
        "deployed model to production", "production-grade ml", "served ml models",
        "real-time inference", "model deployment pipeline", "mlops",
        "ml infrastructure", "inference latency", "model serving infrastructure",
    ],
}
MUST_HAVE_WEIGHT = 1.0

NICE_TO_HAVE_CONCEPTS: Dict[str, List[str]] = {
    "fine_tuning_deep": ["lora", "qlora", "peft", "distillation", "quantization"],
    "ltr_models": ["xgboost", "learning to rank", "neural ranking", "gbdt ranker"],
    "hr_tech_domain": ["recruiting platform", "hr-tech", "hr tech", "talent platform",
                        "ats integration", "hiring marketplace", "job platform"],
    "distributed_systems": ["distributed system", "kafka", "spark", "kubernetes",
                             "large-scale inference", "model serving"],
    "open_source": ["open-source", "open source", "github contribution",
                     "published paper", "conference talk", "oss maintainer"],
}
NICE_TO_HAVE_WEIGHT = 0.4

# Concepts whose ABSENCE (alongside CV/speech/robotics dominance) matters
NLP_IR_CONCEPTS = [
    "nlp", "natural language processing", "search engine", "information retrieval",
    "ranking system", "recommendation system", "llm", "embedding", "search relevance",
]
CV_SPEECH_ROBOTICS_CONCEPTS = [
    "computer vision", "image classification", "object detection",
    "speech recognition", "robotics", "autonomous driving", "slam",
]
LANGCHAIN_WRAPPER_CONCEPTS = ["langchain", "openai api", "gpt wrapper", "chatgpt api"]
PRE_LLM_ML_CONCEPTS = [
    "machine learning", "recommendation system", "search ranking", "retrieval system",
    "nlp", "computer vision", "data pipeline", "ml model", "model training",
]
RESEARCH_ONLY_CONCEPTS = ["research scientist", "postdoc", "phd candidate",
                           "research fellow", "academic researcher", "research lab"]
PRODUCTION_SIGNAL_CONCEPTS = ["production", "deployed", "shipped", "engineer",
                               "platform", "users", "scale"]
CONSULTING_FIRMS = ["tcs", "tata consultancy", "infosys", "wipro", "accenture",
                     "cognizant", "capgemini", "hcl", "tech mahindra", "mindtree", "mphasis"]

# Hedging/enthusiast language that distinguishes "I took a course about this"
# from "I built this in production." Per JD's explicit "framework enthusiast"
# trap type. IMPORTANT: each phrase below is a compound, AI-specific phrase —
# generic hedges like "excited about" or "side project" alone are deliberately
# excluded; an earlier version using bare generic hedges flagged ~50% of the
# entire dataset (verified by direct count), which is a false-positive rate
# far too high to be a real signal. Tightening to AI-specific compounds
# brought the count down to a defensible, realistic range.
HOBBYIST_HEDGE_PHRASES = [
    "ai enthusiast", "experimenting with langchain", "experimenting with the openai api",
    "experimenting with openai", "online courses on rag", "taking online courses on",
    "technical depth in ai is limited", "exploring how ai", "exploring how llms",
    "exploring how genai", "growing my ai capabilities", "side projects with langchain",
    "side project with langchain", "ai side project", "ai side projects",
    # Found by mining the real dataset: this exact disclaimer sentence covers
    # 25,000 of 100,000 candidates (25%) — by far the dominant hobbyist-trap
    # template, completely missed until checked against real data.
    "self-learner level", "haven't done it in a professional capacity",
    "professional capacity yet", "played with the openai",
]
AI_RELEVANT_TITLE_KEYWORDS = [
    "machine learning", "ml engineer", "ai engineer", "data scientist",
    "nlp", "search", "ranking", "recommendation", "applied scientist",
    "research scientist", "deep learning", "computer vision",
]

# Generic role-label phrases used to detect deliberately scrambled
# title/description pairs (e.g. a "Business Analyst" role whose description
# is actually about content writing, or vice versa) — a corroborating
# honeypot-adjacent signal, not a standalone one (some overlap is normal
# for hybrid roles).
ROLE_LABEL_PHRASES = [
    "business analyst", "content writing", "hr manager", "mechanical engineer",
    "operations management", "software engineer", "data scientist",
    "marketing manager", "sales executive", "recruiter", "graphic designer",
    "customer support", "project manager", "product manager",
]

TIER1_CITIES = ["bangalore", "bengaluru", "hyderabad", "mumbai", "delhi",
                "gurugram", "gurgaon", "ncr", "chennai"]
TARGET_CITIES = ["pune", "noida"]

# Exact, confirmed-fixed vocabulary of non-technical current_title strings.
# The full 100K-candidate pool uses exactly 47 distinct current_title values
# total (verified by direct enumeration) — there are no hybrid/ambiguous
# variants like "Senior Civil Engineer," just this clean fixed set, so an
# EXACT match here carries no risk of catching a legitimate hybrid title.
# This exists as a hard backstop independent of keyword/concept matching:
# verified against the real pool that 634 candidates with one of these exact
# titles still scored >0.3 through genuine (non-buggy) buzzword-stuffed
# skills/descriptions even after the substring-matching fix — keyword density
# in the body text should never outrank what the person's actual current job
# is, per the JD's explicit instruction not to rank on keyword density alone.
NON_TECHNICAL_TITLES = {
    "business analyst", "hr manager", "mechanical engineer", "accountant",
    "project manager", "customer support", "operations manager", "content writer",
    "sales executive", "civil engineer", "graphic designer", "marketing manager",
}

# ============================================================================
# COMPANY FOUNDING YEARS — mined directly from candidates.jsonl (63 distinct
# companies appear across the whole pool; these are REAL, named companies,
# not anonymized). This operationalizes the exact honeypot example given in
# submission_spec.docx Section 7: "8 years of experience at a company
# founded 3 years ago." Verified against the real dataset: a -1y buffer on
# this single check alone flags 93 candidates — almost exactly the spec's
# "~80 honeypots" — so this is treated as a standalone, sufficient signal
# rather than something needing corroboration.
# Companies like "Wayne Enterprises", "Hooli", "Pied Piper", "Stark
# Industries" etc. are clearly fictional filler labels used across the bulk
# of the pool (~31K mentions each, near-uniform) and are deliberately
# excluded here — they're noise-population placeholders, not honeypot signal.
# ============================================================================

COMPANY_FOUNDING_YEAR: Dict[str, int] = {
    "zomato": 2008, "flipkart": 2007, "swiggy": 2014, "razorpay": 2014, "cred": 2018,
    "meesho": 2015, "nykaa": 2012, "inmobi": 2007, "zoho": 1996, "ola": 2010,
    "vedantu": 2014, "byju's": 2011, "byjus": 2011, "policybazaar": 2008, "paytm": 2010,
    "freshworks": 2010, "upgrad": 2015, "pharmeasy": 2015, "phonepe": 2015, "dream11": 2008,
    "unacademy": 2010, "genpact ai": 1997, "genpact": 1997, "glance": 2019, "rephrase.ai": 2019,
    "sarvam ai": 2023, "aganitha": 2015, "niramai": 2016, "saarthi.ai": 2018, "krutrim": 2023,
    "wysa": 2015, "mad street den": 2013, "haptik": 2013, "verloop.io": 2016, "observe.ai": 2017,
    "yellow.ai": 2016, "locobuzz": 2014, "google": 1998, "netflix": 1997, "amazon": 1994,
    "meta": 2004, "salesforce": 1999, "microsoft": 1975, "uber": 2009, "infosys": 1981,
    "wipro": 1945, "tcs": 1968, "capgemini": 1967, "accenture": 1989, "hcl": 1976,
    "mindtree": 1999, "cognizant": 1994, "tech mahindra": 1986, "mphasis": 1998,
}
FOUNDING_YEAR_BUFFER = 1  # years of slack (pre-launch stealth mode etc.)

# Fictional filler labels used as generic noise-population placeholders across
# ~31K rows each (verified by direct company-frequency count on the real pool —
# near-uniform distribution, not concentrated in any one trap category). These
# have no real-world founding year and must NEVER be treated as a structural
# honeypot signal. They are explicitly excluded from COMPANY_FOUNDING_YEAR
# (not just absent by omission) and the assertion below guards against any
# future edit accidentally adding one of them to the real lookup table.
FICTIONAL_FILLER_COMPANIES = {
    "wayne enterprises", "hooli", "pied piper", "stark industries",
    "globex inc", "initech", "dunder mifflin", "acme corp",
}
assert FICTIONAL_FILLER_COMPANIES.isdisjoint(COMPANY_FOUNDING_YEAR.keys()), \
    "A fictional filler company must never appear in the real founding-year lookup table."


def _norm(text: str) -> str:
    if not isinstance(text, str):
        return ""
    return re.sub(r"\s+", " ", text.lower())


_TERM_PATTERN_CACHE: Dict[str, "re.Pattern"] = {}


def _matched_terms(text: str, terms: List[str]) -> List[str]:
    """Leading-word-boundary matching, NOT naive substring matching.

    CRITICAL BUG FOUND AND FIXED: naive `term in text` substring checks match
    inside unrelated words — "rag" matches inside "storage" and "leveraging",
    "lora" matches inside "exploration", "ltr" risks matching inside other
    words too. This was confirmed to be the actual root cause of non-technical
    candidates (Civil Engineer, Marketing Manager, Mechanical Engineer) wrongly
    climbing the rankings: their text was never matching real AI/ML concepts,
    it was matching word fragments.

    Using a regex with a LEADING \\b (word boundary) before the term — but
    deliberately NOT a trailing one — blocks all such mid-word false matches
    (there's no boundary on either side of "rag" inside "sto|rage") while still
    correctly matching plural/inflected forms ("embedding" still matches inside
    "embeddings", since there IS a leading boundary before the plural form too).
    """
    matched = []
    for t in terms:
        t_clean = t.strip()
        if not t_clean:
            continue
        if t_clean not in text:
            continue  # cheap C-level pre-filter: skip regex entirely if not even a substring
        pattern = _TERM_PATTERN_CACHE.get(t_clean)
        if pattern is None:
            pattern = re.compile(r"\b" + re.escape(t_clean))
            _TERM_PATTERN_CACHE[t_clean] = pattern
        if pattern.search(text):
            matched.append(t_clean)
    return matched


def concept_bucket_score(text: str, concept_dict: Dict[str, List[str]]) -> Tuple[float, List[str]]:
    """Returns (fraction_of_buckets_hit, list of bucket names hit) — capped contribution
    per bucket so one buzzword-stuffed bucket can't dominate the score."""
    hit_buckets = []
    for bucket, terms in concept_dict.items():
        if _matched_terms(text, terms):
            hit_buckets.append(bucket)
    score = len(hit_buckets) / max(len(concept_dict), 1)
    return score, hit_buckets


# ============================================================================
# 2. STRUCTURAL HONEYPOT DETECTION
#    Per submission_spec.docx Section 7: "subtly impossible profiles"
#    e.g. expert proficiency with 0 months used, overlapping employment.
#    These are LOGICAL contradictions in the structured data, not semantic
#    mismatches — a text/embedding similarity score cannot catch these.
# ============================================================================

def detect_honeypot(candidate: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """Two STRONG signals (each sufficient alone — verified against the real
    100K-candidate pool to land close to the spec's stated "~80 honeypots"):
      1. A career_history entry starts before the company's real founding year.
      2. A majority of listed skills are "expert" with ~0 months of use.

    Plus weaker structural contradictions that require 2+ to corroborate
    (single-signal use of these produced too many false positives against
    the real data — e.g. signup-after-last-active fires on ~7.5% of the
    entire pool and is almost certainly generator noise, not a honeypot
    marker, so it is NOT used as a standalone signal here).
    """
    strong_reasons = []
    weak_reasons = []
    profile = candidate.get("profile", {}) or {}
    career = candidate.get("career_history", []) or []
    skills = candidate.get("skills", []) or []
    signals = candidate.get("redrob_signals", {}) or {}

    # STRONG (1): career entry predates the company's real founding year.
    # Fictional filler companies are explicitly skipped (not just absent from
    # the lookup table) — they have no real founding year and must never be
    # treated as a structural honeypot signal.
    for c in career:
        comp = _norm(c.get("company", "")).strip()
        if comp in FICTIONAL_FILLER_COMPANIES:
            continue
        founding_year = COMPANY_FOUNDING_YEAR.get(comp)
        if founding_year is None:
            continue
        sd = _parse_date(c.get("start_date"))
        if sd and sd.year < founding_year - FOUNDING_YEAR_BUFFER:
            strong_reasons.append(
                f"claims to have joined {c.get('company')} in {sd.year}, "
                f"{founding_year - sd.year} years before it was founded ({founding_year})"
            )
            break

    # STRONG (2): majority of skills are "expert" with ~0 months of use
    if len(skills) >= 5:
        expert_zero = [s for s in skills if s.get("proficiency") == "expert" and (s.get("duration_months") or 0) <= 1]
        if len(expert_zero) / len(skills) >= 0.6:
            strong_reasons.append(
                f"{len(expert_zero)}/{len(skills)} skills rated 'expert' with ~0 months of use"
            )

    if strong_reasons:
        return True, strong_reasons

    # WEAK / corroborating signals — need 2+ together
    total_months = sum((c.get("duration_months") or 0) for c in career)
    yoe_months = float(profile.get("years_of_experience", 0)) * 12
    if yoe_months > 0 and total_months > yoe_months * 1.6 + 12:
        weak_reasons.append("career history duration far exceeds stated years of experience")

    parsed = []
    for c in career:
        sd = _parse_date(c.get("start_date"))
        ed = _parse_date(c.get("end_date")) if c.get("end_date") else TODAY
        if sd:
            parsed.append((sd, ed))
    parsed.sort()
    for i in range(len(parsed) - 1):
        _, end_i = parsed[i]
        start_next, _ = parsed[i + 1]
        if end_i and start_next and (start_next - end_i).days < -45:
            weak_reasons.append("overlapping employment dates across roles")
            break

    for c in career:
        sd = _parse_date(c.get("start_date"))
        ed = _parse_date(c.get("end_date")) if c.get("end_date") else None
        if sd and ed and ed < sd:
            weak_reasons.append("a role's end date precedes its start date")
            break

    for c in career:
        if c.get("is_current") and c.get("end_date"):
            weak_reasons.append("marked as current role but has an end date")
            break

    # Scrambled title/description pairing: description's own text strongly
    # asserts a DIFFERENT role label than the entry's stated title (e.g. a
    # "Business Analyst" entry whose description opens with "Content writing
    # and SEO strategy..."). Corroborating signal only — some overlap between
    # adjacent role labels is normal for hybrid jobs.
    for c in career:
        title_norm = _norm(c.get("title", ""))
        desc_norm = _norm(c.get("description", ""))
        mismatch_found = False
        for label in ROLE_LABEL_PHRASES:
            if label in desc_norm and label not in title_norm and not any(
                    w in title_norm for w in label.split()):
                weak_reasons.append(f"role titled '{c.get('title')}' has a description centered on '{label}'")
                mismatch_found = True
                break
        if mismatch_found:
            break

    return (len(weak_reasons) >= 2), weak_reasons


# ============================================================================
# 3. HARD DISQUALIFIERS — per job_description.docx "disqualifiers we apply"
# ============================================================================

def detect_hard_disqualifiers(candidate: Dict[str, Any]) -> Tuple[bool, List[str]]:
    reasons = []
    profile = candidate.get("profile", {}) or {}
    career = candidate.get("career_history", []) or []

    # Non-technical current title — checked first, cheap, exact-match against
    # the dataset's confirmed fixed vocabulary (see NON_TECHNICAL_TITLES above).
    # This is a hard backstop: a Marketing Manager or Civil Engineer is not a
    # Senior AI Engineer candidate no matter how buzzword-dense their skills
    # list is. Short-circuits before any of the more expensive text scans below.
    current_title_exact = _norm(profile.get("current_title", "")).strip()
    if current_title_exact in NON_TECHNICAL_TITLES:
        reasons.append(f"current title '{profile.get('current_title','')}' is a non-technical role, "
                        f"not an engineering/ML position — disqualified regardless of keyword overlap elsewhere")
        return True, reasons

    full_text = _norm(" ".join([
        profile.get("current_title", ""), profile.get("summary", ""),
        " ".join(c.get("title", "") + " " + c.get("description", "") + " " + c.get("industry", "")
                 for c in career),
    ]))
    companies = [_norm(c.get("company", "")) for c in career]

    # Pure research-only career: research vocabulary present, zero production signal anywhere
    if _matched_terms(full_text, RESEARCH_ONLY_CONCEPTS) and not _matched_terms(full_text, PRODUCTION_SIGNAL_CONCEPTS):
        reasons.append("career history shows research-only roles with no production deployment experience")

    # Consulting-only career (no product company ever)
    if companies and all(any(f in comp for f in CONSULTING_FIRMS) for comp in companies):
        reasons.append("entire career history is at services/consulting firms with no product-company experience")

    # Recent LangChain-wrapper-only AI experience, no earlier pre-LLM ML production history
    sorted_career = sorted(career, key=lambda c: c.get("start_date") or "", reverse=True)
    if sorted_career:
        most_recent = sorted_career[0]
        recent_text = _norm(most_recent.get("description", ""))
        months_ago = None
        sd = _parse_date(most_recent.get("start_date"))
        if sd:
            months_ago = (TODAY - sd).days / 30.44
        older_text = _norm(" ".join(c.get("description", "") for c in sorted_career[1:]))
        if (_matched_terms(recent_text, LANGCHAIN_WRAPPER_CONCEPTS)
                and months_ago is not None and months_ago <= 12
                and not _matched_terms(older_text, PRE_LLM_ML_CONCEPTS)):
            reasons.append("AI experience is limited to a recent LangChain/API-wrapper role with no earlier ML production history")

    # CV / speech / robotics-only without any NLP/IR exposure
    if _matched_terms(full_text, CV_SPEECH_ROBOTICS_CONCEPTS) and not _matched_terms(full_text, NLP_IR_CONCEPTS):
        reasons.append("background is computer vision/speech/robotics with no NLP or information-retrieval exposure")

    # AI hobbyist: current title has no AI/ML signal, AI vocabulary only shows up
    # wrapped in hedging language ("online course", "side project", "AI enthusiast"),
    # not claims of production work. Per JD's explicit "framework enthusiast" trap.
    current_title_norm = _norm(profile.get("current_title", ""))
    hedge_hits = _matched_terms(full_text, HOBBYIST_HEDGE_PHRASES)
    if (not any(k in current_title_norm for k in AI_RELEVANT_TITLE_KEYWORDS)
            and len(hedge_hits) >= 1):
        reasons.append(
            f"AI vocabulary appears only via hedging/hobbyist language ({', '.join(hedge_hits[:2])}) "
            f"while the current role ('{profile.get('current_title','')}') is unrelated to AI/ML"
        )

    return (len(reasons) > 0), reasons


# ============================================================================
# 4. SOFT MODIFIERS — title-chasing, architecture-drift (multiplicative, not fatal)
# ============================================================================

def soft_career_modifier(candidate: Dict[str, Any]) -> Tuple[float, List[str]]:
    notes = []
    multiplier = 1.0
    profile = candidate.get("profile", {}) or {}
    career = candidate.get("career_history", []) or []

    non_current = [c for c in career if not c.get("is_current")]
    if len(career) >= 3 and non_current:
        avg_tenure = np.mean([c.get("duration_months") or 0 for c in non_current])
        if avg_tenure < 18:
            multiplier *= 0.7
            notes.append(f"average tenure of {avg_tenure:.0f} months across roles suggests frequent job-hopping")

    title = _norm(profile.get("current_title", ""))
    desc = _norm(" ".join(c.get("description", "") for c in career if c.get("is_current")))
    if any(t in title for t in ["architect", "director", " vp", "head of"]) and not any(
            k in desc for k in ["implemented", "built", "wrote", "hands-on", "coded", "shipped"]):
        multiplier *= 0.85
        notes.append("current title suggests architecture/leadership drift away from hands-on coding")

    return multiplier, notes


# ============================================================================
# 5. EXPERIENCE FIT — trapezoidal credit centered on the JD's 5-9y band,
#    "ideal" sweet spot at 6-8y, gentle (not harsh) taper outside per JD:
#    "we'll seriously consider candidates outside the band if other signals are strong"
# ============================================================================

def experience_fit(years: float) -> float:
    if years <= 0:
        return 0.0
    if 6 <= years <= 8:
        return 1.0
    if 5 <= years < 6:
        return 0.9 + (years - 5) * 0.1
    if 8 < years <= 9:
        return 1.0 - (years - 8) * 0.1
    if years < 5:
        return max(0.3, 0.3 + years * 0.12)
    # years > 9
    return max(0.55, 0.9 - (years - 9) * 0.05)


# ============================================================================
# 6. LOCATION + LOGISTICS FIT — per JD "On location, comp, and logistics"
# ============================================================================

def location_fit(profile: Dict[str, Any], signals: Dict[str, Any]) -> Tuple[float, str]:
    loc = _norm(profile.get("location", ""))
    country = _norm(profile.get("country", ""))
    willing = bool(signals.get("willing_to_relocate", False))

    if any(c in loc for c in TARGET_CITIES):
        return 1.0, "based in Pune/Noida (target location)"
    if "india" in country or country == "":
        if any(c in loc for c in TIER1_CITIES):
            return 0.8 if willing else 0.65, "in a Tier-1 Indian city welcomed by the JD"
        if willing:
            return 0.55, "in India, open to relocation"
        return 0.35, "in India but not flagged as willing to relocate"
    # Outside India
    if willing:
        return 0.3, "outside India but open to relocation (JD: case-by-case, no visa sponsorship)"
    return 0.1, "outside India and not flagged as willing to relocate (JD does not sponsor visas)"


def notice_fit(signals: Dict[str, Any]) -> Tuple[float, str]:
    days = signals.get("notice_period_days")
    if days is None:
        return 0.5, "notice period unknown"
    if days <= 30:
        return 1.0, f"{days}-day notice period (within the JD's preferred window)"
    if days <= 60:
        return 0.6, f"{days}-day notice period (workable but above the JD's preference)"
    return 0.3, f"{days}-day notice period (long relative to JD preference)"


# ============================================================================
# 7. BEHAVIORAL MULTIPLIER — per redrob_signals_doc + JD's explicit instruction
#    to meaningfully down-weight inactive/unresponsive candidates, not just
#    nudge the score by a fraction of a point.
# ============================================================================

def behavioral_multiplier(signals: Dict[str, Any]) -> Tuple[float, List[str]]:
    notes = []
    m = 1.0

    last_active = _parse_date(signals.get("last_active_date"))
    days_inactive = (TODAY - last_active).days if last_active else 9999

    if days_inactive <= 30:
        recency = 1.0
    elif days_inactive <= 90:
        recency = 0.9
    elif days_inactive <= 180:
        recency = 0.75
        notes.append(f"inactive for ~{days_inactive} days")
    else:
        recency = 0.5
        notes.append(f"inactive for over {days_inactive} days")
    m *= recency

    rate = float(signals.get("recruiter_response_rate", 0.0) or 0.0)
    responsiveness = 0.7 + 0.3 * rate
    m *= responsiveness
    if rate < 0.15:
        notes.append(f"low recruiter response rate ({rate:.0%})")

    if not signals.get("open_to_work_flag", False):
        m *= 0.85

    completeness = float(signals.get("profile_completeness_score", 50.0) or 50.0) / 100.0
    m *= (0.85 + 0.15 * completeness)

    return float(np.clip(m, 0.35, 1.05)), notes


# ============================================================================
# 8. MAIN ENGINE
# ============================================================================

def pick_named_skills(skills: List[Dict[str, Any]], max_n: int = 2) -> List[str]:
    """Pick real, credible skill names straight from the candidate's own data —
    per submission_spec.docx Stage 4 review, reasoning should reference "named
    skills" from the profile. Pulling these directly (never inventing a skill)
    also satisfies the "no hallucination" check in the same rubric.
    Prefers skills with real depth (advanced/expert + meaningful duration) over
    beginner/zero-duration ones, so honeypot-style "expert at 0 months" entries
    don't get cited as if they were credible."""
    credible = [s for s in skills
                if s.get("proficiency") in ("advanced", "expert")
                and (s.get("duration_months") or 0) >= 6]
    credible.sort(key=lambda s: (s.get("duration_months") or 0), reverse=True)
    return [s.get("name", "") for s in credible[:max_n] if s.get("name")]


class RedrobRankingEngine:
    """Stateless, network-free, GPU-free ranking engine."""

    def __init__(self):
        pass

    def _candidate_text(self, candidate: Dict[str, Any]) -> str:
        profile = candidate.get("profile", {}) or {}
        career = candidate.get("career_history", []) or []
        skills = candidate.get("skills", []) or []
        parts = [
            profile.get("current_title", ""),
            profile.get("headline", ""),
            profile.get("summary", ""),
            " ".join(f"{c.get('title','')} {c.get('description','')} {c.get('industry','')}" for c in career),
            " ".join(s.get("name", "") for s in skills),
        ]
        return _norm(" ".join(parts))

    def score_candidate(self, candidate: Dict[str, Any]) -> Dict[str, Any]:
        candidate_id = candidate.get("candidate_id")
        profile = candidate.get("profile", {}) or {}
        signals = candidate.get("redrob_signals", {}) or {}
        years = float(profile.get("years_of_experience", 0.0) or 0.0)

        is_honeypot, honeypot_reasons = detect_honeypot(candidate)
        if is_honeypot:
            return {
                "candidate_id": candidate_id, "score": 0.02,
                "reasoning": ("Flagged for internally inconsistent profile data ("
                              + "; ".join(honeypot_reasons[:2]) + ") — excluded from consideration."),
            }

        is_disqualified, dq_reasons = detect_hard_disqualifiers(candidate)
        text = self._candidate_text(candidate)

        must_score, must_hits = concept_bucket_score(text, MUST_HAVE_CONCEPTS)
        nice_score, nice_hits = concept_bucket_score(text, NICE_TO_HAVE_CONCEPTS)
        semantic_fit = float(np.clip(MUST_HAVE_WEIGHT * must_score + NICE_TO_HAVE_WEIGHT * nice_score, 0, 1))

        exp_fit = experience_fit(years)
        loc_score, loc_note = location_fit(profile, signals)
        notice_score, notice_note = notice_fit(signals)

        career_mult, career_notes = soft_career_modifier(candidate)
        behav_mult, behav_notes = behavioral_multiplier(signals)
        named_skills = pick_named_skills(candidate.get("skills", []) or [])

        base = (0.55 * semantic_fit) + (0.25 * exp_fit) + (0.12 * loc_score) + (0.08 * notice_score)
        score = base * career_mult * behav_mult

        if is_disqualified:
            score = min(score, 0.12)

        score = float(np.clip(score, 0.0, 1.0))

        reasoning = self._build_reasoning(
            profile, years, must_hits, exp_fit, loc_note, notice_note,
            career_notes, behav_notes, is_disqualified, dq_reasons, named_skills,
        )

        return {"candidate_id": candidate_id, "score": round(score, 4), "reasoning": reasoning}

    @staticmethod
    def _build_reasoning(profile, years, must_hits, exp_fit, loc_note, notice_note,
                          career_notes, behav_notes, is_disqualified, dq_reasons, named_skills) -> str:
        title = profile.get("current_title", "Unknown title")
        company = profile.get("current_company", "Unknown company")

        if is_disqualified:
            return f"{title} at {company}, {years:.1f}y experience — {dq_reasons[0]}; ranked low despite any surface keyword overlap."

        bucket_label = {
            "embeddings_retrieval": "embeddings/retrieval", "vector_db_hybrid_search": "vector DB/hybrid search",
            "ranking_recsys": "ranking/recsys", "llm_systems": "LLM systems",
            "eval_frameworks": "eval frameworks", "production_ml": "production ML",
        }
        hits_text = ", ".join(bucket_label.get(h, h) for h in must_hits[:3]) if must_hits else "limited direct overlap with the core stack"
        skills_text = f" (notably {', '.join(named_skills)})" if named_skills else ""

        fit_phrase = "a strong fit for the 5-9y target band" if exp_fit >= 0.9 else (
            "outside the JD's ideal band but not disqualifying" if exp_fit >= 0.5 else "well outside the experience range the JD targets")

        sentence1 = f"{title} at {company} ({years:.1f}y experience, {fit_phrase}); profile shows {hits_text}{skills_text}."

        flags = []
        flags.append(loc_note)
        flags.append(notice_note)
        flags.extend(career_notes)
        flags.extend(behav_notes)
        sentence2 = "; ".join(f for f in flags if f) + "."
        return f"{sentence1} {sentence2}"

    def process_large_scale_dataset(self, jd_text: str, data_path: str, chunk_size: int = 5000
                                     ) -> Generator[pd.DataFrame, None, None]:
        """Chunked, streaming, network-free scoring. jd_text is accepted for interface
        compatibility / future extensibility but the concept vocabulary above is the
        actual scoring rubric (curated directly from job_description.docx).

        Handles BOTH input shapes found in the hackathon bundle:
          - candidates.jsonl / candidates.jsonl.gz  -> one JSON object per line
          - sample_candidates.json                  -> a single pretty-printed JSON array

        IMPORTANT: pd.read_json(..., lines=True, chunksize=N) returns a LAZY
        reader — it does not parse anything (and therefore cannot raise) until
        you actually iterate it. A naive try/except around the call site never
        catches a format mismatch; the crash happens one level up, inside the
        for-loop, which is exactly the 'Expected object or value' error seen
        when a JSON array was fed in. Fixed here by sniffing the first
        non-whitespace byte of the (possibly gzipped) file BEFORE deciding
        which parser to use.
        """
        import gzip
        import json as _json

        opener = gzip.open if data_path.endswith(".gz") else open

        first_char = None
        with opener(data_path, "rt", encoding="utf-8") as f:
            while True:
                ch = f.read(1)
                if not ch:
                    break
                if not ch.isspace():
                    first_char = ch
                    break

        if first_char is None:
            return  # empty file, nothing to yield

        if first_char == "[":
            # Pretty-printed JSON array (e.g. sample_candidates.json)
            with opener(data_path, "rt", encoding="utf-8") as f:
                data = _json.load(f)
            for i in range(0, len(data), chunk_size):
                scored = self._score_chunk(pd.DataFrame(data[i:i + chunk_size]))
                if scored is not None:
                    yield scored
        else:
            # JSON-Lines (the real candidates.jsonl[.gz]) — use pandas' fast C parser
            reader = pd.read_json(data_path, lines=True, chunksize=chunk_size)
            for chunk in reader:
                scored = self._score_chunk(chunk)
                if scored is not None:
                    yield scored

    def _score_chunk(self, chunk: pd.DataFrame):
        results = []
        for candidate in chunk.to_dict("records"):
            if not candidate.get("profile") or not isinstance(candidate.get("profile"), dict):
                continue
            if not candidate.get("candidate_id"):
                continue
            results.append(self.score_candidate(candidate))
        return pd.DataFrame(results) if results else None
