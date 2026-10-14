#!/bin/sh
set -eu
base=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
cd "$base"
exec "$base/.runtime/ai-venv/bin/python" -m uvicorn standalone_lab:app --app-dir experiments/qa_space --host 127.0.0.1 --port 5174
