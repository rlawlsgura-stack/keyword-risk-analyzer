"""Move legacy regulation originals from Postgres bytea to private Supabase Storage."""
import base64
import hashlib
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from repository import SupabaseRepository


def main():
    repository = SupabaseRepository()
    moved = 0
    while True:
        rows = repository.rpc('list_regulation_document_originals', p_limit=1) or []
        if not rows:
            break
        row = rows[0]
        encoded = ''.join(str(row['original_base64']).split())
        payload = base64.b64decode(encoded, validate=True)
        digest = hashlib.sha256(payload).hexdigest()
        if digest != row['content_sha256']:
            raise RuntimeError(f"Original file hash mismatch for {row['id']}")
        path = 'originals/' + secrets.token_hex(24)
        repository.upload_regulation_original(path, payload, row['mime_type'])
        updated = repository.rpc('finish_regulation_document_original_migration',
                                 p_id=row['id'], p_storage_path=path,
                                 p_content_sha256=digest)
        if not updated:
            # Keep the unreferenced object for manual cleanup; a timeout can make
            # the database commit outcome ambiguous, so deleting here is unsafe.
            raise RuntimeError(f"Document changed during migration: {row['id']}")
        moved += 1
        print(f'Migrated {row["id"]}')
    print(f'Completed: {moved} original file(s) migrated')


if __name__ == '__main__':
    main()
