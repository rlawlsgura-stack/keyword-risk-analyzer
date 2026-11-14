# 사내 규정 원본 파일 Storage 전환

새 문서의 원본은 비공개 `regulation-documents` Supabase Storage 버킷에 저장하고, PostgreSQL에는 파일 경로·해시·추출 본문과 검색 조각을 저장합니다. 파일당 제한은 50 MiB입니다. DB 등록과 문서 버전·승인·검색 로직은 유지합니다.

## 기존 환경에 적용할 때

1. 운영 환경의 DB 백업을 확인하고 `supabase/migrations/20261114115135_regulation_document_storage.sql`을 Supabase에 적용합니다. 이 단계에서 비공개 버킷, 스토리지 경로 컬럼, 이전 원본 정리 대기열 및 구버전 파일 이관 RPC가 만들어집니다.
2. 백엔드를 배포합니다. 새 API는 원본 파일을 Storage에 올리고 나머지 문서 처리는 기존 DB RPC 흐름을 따릅니다.
3. 백엔드의 `SUPABASE_URL`, `SUPABASE_SECRET_KEY`를 환경변수로 지정한 뒤 `python scripts/migrate_regulation_document_files_to_storage.py`를 실행합니다. 이 스크립트는 기존 파일을 한 번에 하나씩 옮기고 SHA-256을 비교한 다음 DB 경로를 갱신합니다. 완료 메시지를 확인하기 전에는 구 `original_bytes` 컬럼을 제거하지 마세요.
4. 관리자에서 문서 목록, 본문 확인, 검색, 승인 및 삭제를 확인합니다.

마이그레이션 SQL 적용과 이관 스크립트 실행은 이 로컬 작업에서는 수행하지 않았습니다. 기존 파일은 위 절차가 실행되기 전까지 PostgreSQL에 남아 있고 새 코드와 호환되도록 컬럼을 유지합니다.

## 용량과 전송 방식

현재 연결된 Supabase 프로젝트는 Free 요금제입니다. Storage의 총 사용량은 플랜 한도 안에 있어야 하며, Free의 Storage 용량 한도는 1 GB입니다. 파일당 50 MiB 설정은 전체 Storage 한도와 별개입니다. 자세한 내용은 [파일 크기 및 Storage 한도](https://supabase.com/docs/guides/storage/uploads/file-limits)를 참고하세요. 프로젝트 요금제·한도는 변경될 수 있으므로 실제 적용 전 대시보드에서 다시 확인해야 합니다.

현재 앱은 브라우저에서 API로 파일을 보낸 다음 API가 Storage에 올립니다. [Supabase가 6 MiB 초과 파일에 권장하는 재개 가능한 TUS 전송](https://supabase.com/docs/guides/storage/uploads/resumable-uploads)으로 변경하지 않았으므로, 연결이 끊기면 업로드를 다시 해야 합니다. 따라서 이 변경은 DB 저장 부담과 파일당 최대 크기를 개선하지만, 큰 파일 업로드의 끊김 복구까지 제공한다고 보장하지 않습니다.
