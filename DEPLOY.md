# Deployment notes

## Docker

```bash
docker build -t lgmt .
docker run --rm -v $(pwd)/demo_output:/app/demo_output lgmt   # offline demo (mock model, no key needed)
docker run --rm lgmt lgmt list-mrs                            # list all 20 built-in MRs
docker run --rm -p 7860:7860 lgmt lgmt-web                    # Built-in Web Studio on http://localhost:7860
```

The built-in **LGMT Web Studio** (`lgmt web` / `lgmt-web`) uses Python's
standard-library HTTP server and requires **zero extra dependencies** —
it works out of the box inside the core Docker image and after a standard
`pip install -e .`.

GitHub Actions builds the image on every push (`.github/workflows/ci.yml`,
`docker-build` job) to verify the Dockerfile stays healthy.

## Local Web Studio vs. Hugging Face Spaces

### 1. Built-in Zero-Dependency Web Studio (Default)

```bash
lgmt web --port 7860
# or: python -m lgmt.webapp --port 7860
# open http://localhost:7860 — three tabs:
#   1. Quick Demo (Offline)
#   2. Benchmark Your Model
#   3. Test Custom Cases
```

### 2. Hugging Face Spaces (Gradio Adapter)

For hosting on a Hugging Face **Gradio SDK** Space, `lgmt.webapp.build_app()`
provides a Gradio Blocks wrapper around the same three workflows:

1. Create a new Space at https://huggingface.co/new-space with SDK `Gradio`.
2. Upload the contents of `spaces/` as the Space repository:
   - `app.py` — thin wrapper calling `lgmt.webapp.build_app().launch()`
   - `requirements.txt` — installs `gradio` plus LGMT itself
3. No secrets are needed: the Space pre-loads the offline demo report out
   of the box, and tabs 2–3 accept visitors' own API keys in memory only.

To test the Gradio wrapper locally:

```bash
pip install -r requirements-web.txt
lgmt web --gradio --port 7860
```
