from python:3.13-slim as builder

workdir /app
run useradd -m -s /bin/bash app && chown app:app /app
user app

copy --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin

copy --chown=app:app pyproject.toml uv.lock .
copy --chown=app:app src/ ./src/

run uv sync --frozen --no-dev


from python:3.13-slim as runtime

workdir /app
run useradd -m -s /bin/bash app && chown app:app /app
user app

copy --from=builder --chown=app:app /app/.venv /app/.venv
copy --from=builder --chown=app:app /home/app/.cache /home/app/.cache
copy --chown=app:app src/ ./src/

env PATH="/app/.venv/bin:$PATH"
expose 8090

cmd ["fastapi", "dev", "src/main.py", "--host", "0.0.0.0", "--port", "8090"]
