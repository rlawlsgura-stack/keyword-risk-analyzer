"""Streamlit Community Cloud entrypoint for FIXED291.3."""
from pathlib import Path
import runpy
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
runpy.run_path(str(ROOT / "keyword_app2_fixed291.py"), run_name="__main__")
