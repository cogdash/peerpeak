#!/bin/env bash
ROOT_DIR=$PWD
set -euo pipefail

echo "Генерация для ach-classifier..."
uv run --directory ach-classifier python -m grpc_tools.protoc \
  -I"$ROOT_DIR/proto" \
  --python_out="$ROOT_DIR/ach-classifier/src" \
  --grpc_python_out="$ROOT_DIR/ach-classifier/src" \
  "$ROOT_DIR/proto/classifier.proto"

echo "Генерация для backend..."
uv run --directory backend python -m grpc_tools.protoc \
  -I"$ROOT_DIR/proto" \
  --python_out="$ROOT_DIR/backend/src" \
  --grpc_python_out="$ROOT_DIR/backend/src" \
  "$ROOT_DIR/proto/classifier.proto"

echo "Готово!"


