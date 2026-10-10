# LGMT all-in-one image.
#
#   docker build -t lgmt .
#   docker run --rm lgmt                  # offline demo (mock model, no key needed)
#   docker run --rm lgmt lgmt demo        # same, explicit
#   docker run --rm -p 7860:7860 lgmt lgmt-web   # Gradio web demo
#     (the web UI additionally needs gradio: docker run ... lgmt-web
#      will tell you, or build with requirements-web.txt installed)

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install the package first so layers cache independently of data.
COPY pyproject.toml ./
COPY lgmt ./lgmt
RUN pip install .

# Source test cases (for `lgmt build-mgs`) and demo assets.
COPY data ./data
COPY docker-entrypoint.sh /usr/local/bin/lgmt-entrypoint
RUN chmod +x /usr/local/bin/lgmt-entrypoint

ENTRYPOINT ["lgmt-entrypoint"]
CMD ["lgmt", "demo"]
