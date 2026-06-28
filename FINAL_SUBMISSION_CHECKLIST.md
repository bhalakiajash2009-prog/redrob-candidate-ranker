# Final Pre-Submission Checklist — Hack2Skill Portal

Per your screenshot, the actual submission form (hack2skill.com) has exactly
these fields for the "Data & AI Challenge: Intelligent Candidate Discovery":

1. **Challenge** — already correctly selected: "Data & AI Challenge:
   Intelligent Candidate Discovery"
2. **GitHub Repository** (required, public access) — paste your repo URL,
   must include `https://`
3. **PPT/deck as PDF** (required, ≤5MB) — outlining what you built, why,
   and how it works
4. **Ranked output file in XLSX format** (not marked required, but provide
   it — it's your actual evidence of a working system)

## What's ready right now in this package

| Field | File | Status |
|---|---|---|
| PPT/deck → PDF | `TAG_Star_Redrob_Submission.pdf` | Built, all 11 slides QA'd (contrast, overflow, content accuracy) |
| Ranked output → XLSX | `TAG_Star_Ranked_Candidates.xlsx` | Generated from the real 100K-candidate run, 0 formula errors |
| GitHub Repository | `redrob_ranker/` folder | You need to push this and paste the URL |

## Before you click Submit

1. **Push the repo to GitHub** (public!) — follow `GIT_COMMIT_SEQUENCE.md`
   for a real, incremental commit history rather than one dump. The portal
   explicitly says "make sure it is set to public access."
2. **Double-check the PDF opens correctly** and is under 5MB.
3. **Double-check the XLSX opens correctly** in Excel/Sheets and is under 5MB.
4. **Fill in `submission_metadata.yaml`** — team name (TAG Star) and team
   leader (Jash Bhalakia) are already filled in; you still need email,
   phone, GitHub URL, sandbox URL (if you deploy one separately), and your
   actual machine specs.
5. Paste the GitHub URL into the form field exactly as shown in your
   screenshot — must start with `https://` or `http://` per the form's own
   note.
6. Upload `TAG_Star_Redrob_Submission.pdf` to the PDF deck field.
7. Upload `TAG_Star_Ranked_Candidates.xlsx` to the ranked-output field.
8. Submit.

## One honest gap to flag

The portal screenshot doesn't show a sandbox-link field directly on this
screen — only GitHub repo, PDF, and XLSX. `submission_spec.docx` Section 10
separately describes a required sandbox link as part of the overall
submission. If the portal asks for it on a later step or a separate form,
`SANDBOX_DEPLOYMENT.md` still has the walkthrough ready. If it never
appears, the GitHub repo itself (with a clean `README.md` and
`reproduce_command`) is your fallback proof of reproducibility — make sure
that repo is genuinely clean and runs end-to-end for someone who isn't you.

## What's already verified, so you're not second-guessing it

- 0 honeypots and 0 hard-disqualified candidates in the actual submitted
  top 100 (self-audit printed at the end of every `main.py` run)
- Runtime on the real 100K pool has ranged 66-104s across repeated test runs in this build process (normal sandbox hardware variance) — consistently well under the 5-minute budget
- `validate_submission.py` passes on the actual generated CSV (kept in the
  repo for Stage 3 reproduction, even though this portal wants XLSX)
- Top 20 manually inspected: 100% genuine AI/ML titles at real, relevant
  companies; the 3 most borderline-looking top-10 candidates individually
  pulled and verified by hand
- Deck reviewed slide-by-slide for icon contrast, layout overflow, and
  content accuracy before finalizing — two real bugs found and fixed in
  the deck-building process itself (an SVG color-rendering bug, a
  6-card-row overflowing the slide edge)

## Stage 5 interview — if you get there

Your strongest, most honest talking point: every threshold in this engine
(the honeypot founding-year cutoff, the hobbyist-trap phrase list, the
non-technical title blacklist, the consulting-firm list) was *calibrated by
mining the actual 100K-candidate dataset*, not guessed from the JD alone —
and that process caught multiple real bugs (a substring-matching false
positive, a 10x performance regression, an SVG rendering bug in the deck
itself) before they could have hurt the submission.

Be ready to explain, in your own words, the five scoring components and the
two trap-defense layers. "I tested it against the real data and this is
what I found" is a much stronger answer than reciting a number back.
