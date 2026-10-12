from python:3.13-slim as builder

workdir /app
run useradd -m -s /bin/bash app && chown app:app /app
user app

copy --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin

copy --chown=app:app ./backend/pyproject.toml ./backend/uv.lock .

run uv sync --frozen --no-dev

copy proto/ ./proto/
run mkdir -p out && uv run -m grpc_tools.protoc \
  -Iproto \
  --python_out=out \
  --grpc_python_out=out \
  proto/classifier.proto

from python:3.13-slim as runtime

workdir /app
run useradd -m -s /bin/bash app && chown app:app /app
user app

copy --from=builder --chown=app:app /app/.venv /app/.venv
copy --from=builder --chown=app:app /home/app/.cache /home/app/.cache
copy --from=builder --chown=app:app /app/out/* /app/src/
copy --chown=app:app ./backend/src/ ./src/

env PATH="/app/.venv/bin:$PATH"
expose 8090

cmd ["fastapi", "dev", "src/main.py", "--host", "0.0.0.0", "--port", "8090"]
