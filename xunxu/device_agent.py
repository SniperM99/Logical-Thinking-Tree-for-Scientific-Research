"""Compatibility entrypoint; standalone reusable worker lives in device-agent/."""
from pathlib import Path
import runpy
if __name__=='__main__':runpy.run_path(str(Path(__file__).resolve().parent.parent/'device-agent'/'agent.py'),run_name='__main__')
