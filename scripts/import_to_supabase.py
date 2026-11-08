"""One-time, restartable import. Run from the project root after schema setup."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pandas as pd
from app_config import configure, cloud_enabled
from repository import COUNT_COL, SupabaseRepository


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--directory', type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    configure()
    if not cloud_enabled():
        parser.error('Set STORAGE_BACKEND=supabase before importing')
    repository = SupabaseRepository()
    df = pd.read_csv(args.directory / 'keywords_db.csv', dtype=str,
                     encoding='utf-8-sig').fillna('')
    if COUNT_COL in df:
        # Match the database's numeric representation, including blank -> zero.
        df[COUNT_COL] = pd.to_numeric(df[COUNT_COL].replace('', '0'), errors='raise').astype('int64').astype(str)
    current = repository.load_keywords()
    if current.empty:
        repository.save_keywords(df, current.attrs['revision'])
    else:
        # Never overwrite an existing shared database during an import retry.
        expected = df.sort_values('kwd_no').reset_index(drop=True)
        actual = current.reindex(columns=df.columns).sort_values('kwd_no').reset_index(drop=True)
        if not actual.equals(expected):
            raise RuntimeError('Supabase already contains different data; import stopped')
    log_count = 0
    path = args.directory / 'keywords_hits_log.csv'
    if path.exists():
        logs = pd.read_csv(path, dtype=str, encoding='utf-8-sig').fillna('')
        rows = []
        for index, row in logs.iterrows():
            timestamp = pd.Timestamp(row['ts'])
            timestamp = timestamp.tz_localize('Asia/Seoul') if timestamp.tzinfo is None else timestamp
            if pd.isna(timestamp):
                raise ValueError(f'Invalid log timestamp at row {index + 2}')
            identity = json.dumps([int(index), row['ts'], row['kwd_no']], ensure_ascii=False)
            rows.append({'kwd_no': row['kwd_no'], 'ts': timestamp.isoformat(),
                         'import_key': hashlib.sha256(identity.encode()).hexdigest()})
        for start in range(0, len(rows), 500):
            repository.request('POST', '/rest/v1/kra_hits?on_conflict=import_key',
                               rows[start:start + 500], prefer='resolution=ignore-duplicates')
        log_count = len(logs)
    for name in ('dropdown_config', 'ko_suffix_whitelist', 'ignored_special_symbols'):
        path = args.directory / (name + '.json')
        if path.exists() and repository.load_setting(name, None) is None:
            repository.save_setting(name, json.loads(path.read_text(encoding='utf-8-sig')))
    saved = repository.load_keywords()
    print(f'Imported keywords: {len(saved)}; source log rows: {log_count}')


if __name__ == '__main__':
    main()
