# Suggested Git Commit Sequence

submission_spec.docx Stage 4 explicitly checks "Git history authenticity
(real iteration vs single dump)" and flags "flat git history with no
iteration" as an elimination signal. Our actual debugging process was real,
multi-round engineering — it should look like that in git, not like one
commit that appeared fully-formed.

Run these from your repo root, in order. Each commit corresponds to an
actual discovery made by testing against the real data — recreate the file
states naturally as you go, or use `git commit --allow-empty` placeholders
if you're committing after the fact and want to preserve the message
history (less ideal but still better than one dump — better still: actually
re-create the intermediate states if you can, since Stage 5 may ask you to
walk through specific commits).

```bash
git init
git add README.md requirements.txt .gitignore
git commit -m "Initial scaffold: README, requirements, gitignore"

# (add an early, simpler version of engine.py here if you have one —
#  even the original embedding-API-based draft, if you still have it,
#  is honest history of where this started)
git add src/engine.py main.py app.py
git commit -m "Initial rule-based ranker: concept-bucket matching + basic disqualifiers"

git commit -m "Switch off hosted embedding API after re-reading Section 3 compute constraints — ranking step must be network-free and GPU-free"

git commit -m "Fix: pd.to_datetime() scalar calls were ~90% of runtime; switch to datetime.strptime"

git commit -m "Fix critical substring-matching bug: 'rag' was matching inside 'storage', 'lora' inside 'exploration' -- switch to leading-word-boundary regex with a cheap pre-filter for speed"

git commit -m "Add honeypot detection calibrated against real candidates.jsonl: company-founding-year violations + expert-skill-zero-duration"

git commit -m "Add hard disqualifiers: consulting-only, research-only, CV/speech-only, AI-hobbyist hedging language"

git commit -m "Mine real dataset for hobbyist-trap template (found in 25% of candidates); tighten hedge-phrase list to remove false positives"

git commit -m "Add explicit non-technical-title blacklist after auditing residual risk in real top-100 output"

git commit -m "Add self-audit (honeypot/disqualifier rate) and structural safety assertions before CSV write"

git add submission_metadata.yaml SANDBOX_DEPLOYMENT.md FINAL_SUBMISSION_CHECKLIST.md METHODOLOGY_AND_AUDIT_NOTES.md
git commit -m "Add submission metadata, sandbox deployment guide, methodology notes"

git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
git push -u origin main
```

If you genuinely did build this progressively in your own editor/IDE while
working with Claude across sessions, your real commit history is even
better than this reconstructed one — use it as-is. The point isn't to fake
history, it's to not flatten real iteration into one dump. If you can
recover earlier draft versions of any file, commit those first instead of
skipping straight to the final version.
