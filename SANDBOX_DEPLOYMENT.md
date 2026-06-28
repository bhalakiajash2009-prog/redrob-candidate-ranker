# Sandbox Deployment Guide

Per submission_spec.docx Section 10.5, your sandbox must:
- Accept a small candidate sample (≤100 candidates) via upload or pre-loaded
- Run the ranker end-to-end and produce a ranked CSV
- Complete within 5 minutes on CPU

`app.py` in this repo is built for exactly this — it's the same engine as
`main.py`, with a file-upload box instead of a CLI flag. Recommended route:
**Streamlit Cloud**, because it's free, deploys directly from your GitHub
repo with no Dockerfile needed, and `app.py` is already Streamlit code.

## Steps (Streamlit Cloud — ~5 minutes)

1. Push this repo to GitHub if you haven't already:
   ```bash
   git init
   git add .
   git commit -m "Redrob hackathon submission"
   git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
   git push -u origin main
   ```
2. Go to https://share.streamlit.io and sign in with GitHub.
3. Click "New app," select your repo, branch `main`, and set the main file
   path to `app.py`.
4. Click "Deploy." It will install `requirements.txt` automatically and
   give you a public URL like `https://your-app-name.streamlit.app`.
5. **Test it yourself before submitting**: open the URL, upload
   `sample_candidates.json` (or any small slice of `candidates.jsonl`), click
   "Run Ranking," and confirm it produces a ranked table and a downloadable
   CSV within a minute or two.
6. Paste that URL into `sandbox_link` in `submission_metadata.yaml`.

## Alternative: Hugging Face Spaces (also free, also no Dockerfile needed)

1. Create a new Space at https://huggingface.co/new-space, SDK = Streamlit.
2. Either connect it to your GitHub repo, or upload `app.py`,
   `src/engine.py`, and `requirements.txt` directly through the Spaces UI.
3. It builds and gives you a public URL automatically.

## If you'd rather not deploy anything publicly

The spec explicitly allows a self-contained Docker recipe in your README
instead, as long as it builds and runs unmodified:

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY . .
RUN pip install -r requirements.txt
EXPOSE 8501
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
```

Test locally first with `docker build -t redrob-ranker . && docker run -p
8501:8501 redrob-ranker`, confirm it works, then document the exact
`docker pull`/`docker run` commands in your README in place of a hosted link.

## Whichever you pick

Test it yourself, end-to-end, before submitting. "Submissions without a
working sandbox link are flagged at Stage 1" per the spec — a broken or
untested sandbox is worse than a slightly slower one that actually works.
