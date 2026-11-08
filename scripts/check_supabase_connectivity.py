"""Fail fast before launching Streamlit if Supabase mode cannot reach Auth."""
import os
import sys
import tomllib
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
from app_config import configure


class PreflightError(RuntimeError):
    pass


def check_supabase_connection(backend, url, key, get=requests.get):
    if backend.strip().lower() != 'supabase':
        return 'Supabase preflight skipped (CSV mode).'
    if not url or not key:
        raise PreflightError('Supabase mode needs SUPABASE_URL and SUPABASE_SECRET_KEY.')
    if not url.startswith('https://'):
        raise PreflightError('SUPABASE_URL must use HTTPS.')

    try:
        response = get(
            url.rstrip('/') + '/auth/v1/health',
            headers={'apikey': key},
            timeout=(5, 8),
        )
    except requests.exceptions.Timeout as exc:
        raise PreflightError('Supabase connection timed out; check outbound HTTPS access.') from exc
    except requests.exceptions.ConnectionError as exc:
        raise PreflightError(
            'Supabase is unreachable; check DNS, firewall, VPN, or outbound HTTPS access.'
        ) from exc
    except requests.RequestException as exc:
        raise PreflightError(
            'Supabase health check failed due to a network or TLS error.'
        ) from exc

    if response.status_code in (401, 403):
        raise PreflightError(
            f'Supabase Auth returned HTTP {response.status_code}; check the project URL and server key.'
        )
    if response.status_code != 200:
        raise PreflightError(f'Supabase Auth health check returned HTTP {response.status_code}.')
    return 'Supabase Auth connectivity: OK (HTTP 200).'


def load_streamlit_secrets():
    path = PROJECT_ROOT / '.streamlit' / 'secrets.toml'
    if not path.exists():
        return {}
    try:
        return tomllib.loads(path.read_text(encoding='utf-8-sig'))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise PreflightError('Could not read .streamlit/secrets.toml; check its TOML syntax.') from exc


def main():
    try:
        configure(load_streamlit_secrets())
        message = check_supabase_connection(
            os.getenv('STORAGE_BACKEND', 'csv'),
            os.getenv('SUPABASE_URL', ''),
            os.getenv('SUPABASE_SECRET_KEY', ''),
        )
    except PreflightError as exc:
        print(f'Startup check failed: {exc}', file=sys.stderr)
        print('Streamlit was not started, so login will not fail later from this connection issue.',
              file=sys.stderr)
        return 1
    print(message)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
