#!/bin/sh
set -eu
base=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
cd "$base/ai-engine"
python_bin="$base/.runtime/ai-venv/bin/python"
if [ ! -x "$python_bin" ]; then python_bin=python3; fi
exec "$python_bin" - <<'PY'
from pathlib import Path
import os,sys
p=Path('.env')
if p.exists():
 for line in p.read_text().splitlines():
  if line.strip() and not line.lstrip().startswith('#'):
   key,value=line.split('=',1)
   if key.startswith('XUNXU_'):os.environ.setdefault(key,value)
os.execv(sys.executable,[sys.executable,'-m','uvicorn','main:app','--host','127.0.0.1','--port','8001'])
PY
