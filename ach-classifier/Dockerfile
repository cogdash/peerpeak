from python:3.13-slim as builder

workdir /app

run useradd -m -s /bin/bash app && chown app:app /app
user app

env HF_HOME=/home/app/.cache/huggingface

copy --chown=app:app pyproject.toml uv.lock ./
copy --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin

run uv sync --frozen --no-dev

run .venv/bin/python -c "\
from transformers import pipeline; \
pipeline('zero-shot-classification', model='MoritzLaurer/mDeBERTa-v3-base-mnli-xnli')\
"

from python:3.13-slim as runtime

workdir /app
run useradd -m -s /bin/bash app && chown app:app /app

env HF_HOME=/home/app/.cache/huggingface
env PATH="/app/.venv/bin:$PATH"

copy --from=builder --chown=app:app /app/.venv /app/.venv
copy --from=builder --chown=app:app /home/app/.cache /home/app/.cache
copy --chown=app:app src/ ./src/

user app

expose 8000

cmd ["fastapi", "dev", "src/main.py", "--host", "0.0.0.0", "--port", "8000"]
