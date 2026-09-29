# Deployment notes

## Docker

```bash
docker build -t lgmt .
docker run --rm lgmt                  # offline demo (mock model, no key needed)
docker run --rm lgmt lgmt demo        # same, explicit
docker run --rm -p 7860:7860 lgmt lgmt-web   # Gradio web demo
```

The image ships the core tool only. For the web UI inside Docker either
accept the hint to install gradio, or extend the image:

```dockerfile
RUN pip install -r requirements-web.txt
```

GitHub Actions builds the image on every push (`.github/workflows/ci.yml`,
`docker-build` job) to verify the Dockerfile stays healthy.

## Hugging Face Spaces

The web demo targets a **Gradio SDK** Space.

1. Create a new Space at https://huggingface.co/new-space with SDK `Gradio`.
2. Upload the contents of `spaces/` as the Space repository:
   - `app.py` — thin wrapper calling `lgmt.webapp.build_app()`
   - `requirements.txt` — installs `gradio` plus LGMT itself
3. In the Space's `requirements.txt`, install LGMT from the public repo,
   e.g. `git+https://github.com/<org>/lgmt.git` (TODO: replace placeholder
   once published). Until then you can upload the whole LGMT repository to
   the Space and use `-e .` from the uploaded copy.
4. No secrets are needed: the Space runs the offline demo out of the box.
   The "Test Your Model" tab asks visitors for their own API key, which is
   used in memory only and never persisted.

Local check before uploading:

```bash
pip install -r requirements-web.txt
python -m lgmt.webapp --port 7860
# open http://localhost:7860 — three tabs: Try Demo / Test Your Model / Browse Report
```
