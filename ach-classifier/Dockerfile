from python:3.13-slim as builder

workdir /app

run useradd -m -s /bin/bash app && chown app:app /app
user app

env HF_HOME=/home/app/.cache/huggingface

copy --chown=app:app ./ach-classifier/pyproject.toml ./ach-classifier/uv.lock ./
copy --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin

run uv sync --frozen --no-dev

copy proto/ ./proto/
run mkdir -p out && uv run -m grpc_tools.protoc \
  -Iproto \
  --python_out=out \
  --grpc_python_out=out \
  proto/classifier.proto

run .venv/bin/python -c "\
from transformers import pipeline; \
pipeline('zero-shot-classification', model='MoritzLaurer/mDeBERTa-v3-base-mnli-xnli')\
"

from python:3.13-slim as runtime

workdir /app
run useradd -m -s /bin/bash app && chown app:app /app

env HF_HOME=/home/app/.cache/huggingface
env PATH="/app/.venv/bin:$PATH"

copy --from=builder --chown=app:app /home/app/.cache /home/app/.cache

copy --chown=app:app ./ach-classifier/src/ ./src/
copy --from=builder --chown=app:app /app/.venv /app/.venv
copy --from=builder --chown=app:app /app/out/* /app/src/

user app

expose 50051

cmd ["python", "src/main.py"]
