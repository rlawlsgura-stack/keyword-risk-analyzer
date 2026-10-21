"""Shared environment settings for Streamlit, API and import commands."""
import os
from pathlib import Path


def configure(secrets=None):
    """Load simple KEY=value files without overriding process environment."""
    path = Path(__file__).with_name('.env')
    if path.exists():
        for line in path.read_text(encoding='utf-8-sig').splitlines():
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ.setdefault(key.strip(), value.strip().strip('\"\''))
    if secrets:
        for key, value in secrets.items():
            if isinstance(value, (str, int, bool)):
                os.environ.setdefault(key, str(value))


def cloud_enabled():
    backend = os.getenv('STORAGE_BACKEND', 'csv').lower()
    if backend not in {'csv', 'supabase'}:
        raise ValueError('STORAGE_BACKEND must be csv or supabase')
    return backend == 'supabase'
