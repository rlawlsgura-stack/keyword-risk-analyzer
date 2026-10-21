# Keyword Risk Analyzer 운영 배포와 검증 설계서

문서 ID KRA OPS 001 · 버전 1.0 · 기준일 2026년 10월 21일

## 운영 범위

공유 업무 데이터는 Supabase에 저장하고 Streamlit과 FastAPI를 독립 프로세스로 실행합니다. 로컬 CSV 모드는 개발과 비교용으로 유지합니다. 공유 운영 중 Supabase 연결에 실패해도 CSV로 자동 전환하지 않습니다. 이 문서는 현재 설정 파일과 운영 절차를 설명하며 문서 작성 자체가 호스팅 배포나 백업 설정을 의미하지 않습니다.

## 런타임과 의존성

| 구성 | 현재 직접 의존 버전 | 역할 |
|---|---|---|
| Python | 로컬 검증 3.14, Render 설정 3.14.0 | 서버 런타임 |
| Streamlit | 1.66.0 | 화면 |
| pandas | 3.0.6 | 원장과 리포트 처리 |
| FastAPI | 0.152.0 | 별도 API |
| uvicorn | 0.54.0 | API 실행 |
| requests | 2.34.2 | Supabase HTTP |
| openpyxl | 3.1.5 | Excel 읽기 |
| xlsxwriter | 3.2.9 | Excel 생성 |

직접 의존성은 requirements.txt, 개발용 항목은 requirements-dev.txt, 고정된 설치 집합은 requirements.lock.txt에 있습니다. 로컬 Windows 검증과 Linux 배포 검증은 구분합니다. 현재 문서는 Linux 공개 배포의 완료를 보장하지 않습니다.

## 환경 변수 사전

| 이름 | 기본 또는 예시 형식 | 사용처 | 비밀 여부 |
|---|---|---|---|
| STORAGE_BACKEND | csv 또는 supabase | 두 서버 | 아니오 |
| SUPABASE_URL | https://PROJECT.supabase.co | 두 서버 | 아니오 |
| SUPABASE_SECRET_KEY | 서버 키 자리표시자 | 두 서버 | 비밀 |
| API_ACCESS_TOKEN | 연동용 임의 토큰 자리표시자 | API | 비밀 |
| API_DOCS_ENABLED | false | API 문서 UI | 아니오 |
| ADMIN_USER | 로컬 관리자 이름 | CSV 개발 모드 | 내부 설정 |
| ADMIN_PASSWORD | 로컬 관리자 비밀번호 자리표시자 | CSV 개발 모드 | 비밀 |
| APP_ADMIN_EMAIL | 최초 계정 생성 시 보관한 이메일 | 운영자가 확인하는 초기 자료 | 개인정보 |
| APP_ADMIN_INITIAL_PASSWORD | 초기 비밀번호 자리표시자 | 초기 자료, 앱 인증 코드에서 읽지 않음 | 비밀 |
| PYTHON_VERSION | 3.14.0 | Render 런타임 설정 | 아니오 |

프로세스 환경 변수가 우선이고 로컬 `.env`는 없는 값만 채웁니다. Streamlit Secrets도 이미 설정된 환경 값을 덮어쓰지 않습니다. 따라서 `.env`에 빈 키가 있으면 Secrets의 같은 이름이 덮어쓰지 못할 수 있습니다. 운영에서는 한 가지 주 설정 방식을 정하고 중복된 빈 값을 제거합니다.

초기 관리자 자료의 APP_ADMIN_INITIAL_PASSWORD는 실제 앱이 비밀번호를 비교하는 설정값이 아닙니다. Supabase Auth에 저장된 계정 자격 증명이 기준입니다. 이 로컬 값을 바꾸는 것만으로 계정 비밀번호가 변경되지 않습니다. 서버 키와 API 토큰 또한 서로 목적이 다릅니다.

## 로컬 실행 절차

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
Copy-Item .env.example .env
```

기존 `.env`가 있으면 복사로 덮어쓰지 않습니다. 필요한 값을 직접 설정하고 두 터미널에서 실행합니다.

```powershell
.\.venv\Scripts\python.exe -m streamlit run keyword_app2_fixed270.py
.\.venv\Scripts\python.exe -m uvicorn api:app --host 127.0.0.1 --port 8000
```

Streamlit은 localhost 8501, API는 localhost 8000을 기본으로 사용합니다. 실제 포트 점유와 실행 옵션에 따라 달라질 수 있습니다. 설정을 변경한 뒤 프로세스를 다시 시작해야 환경 값이 확실하게 반영됩니다.

## 호스팅 배포 설계

render.yaml에는 keyword-risk-ui와 keyword-risk-api Web Service가 정의돼 있습니다. 두 서비스 모두 requirements.lock.txt로 설치하며 `$PORT`에 바인딩합니다. UI 상태 확인은 `/_stcore/health`, API는 `/healthz`입니다. DB 접근까지 확인할 때는 인증된 `/readyz`를 별도로 호출합니다.

설정에는 starter 플랜이 들어 있습니다. 실제 배포 시 비용과 프로젝트 운영 정책을 확인해야 하며 이 문서에 현재 요금이나 무료 운영 보장을 포함하지 않습니다. 서버 비밀 키는 플랫폼 환경 변수에 입력하고 Git에 넣지 않습니다. Community Cloud에서는 UI에 Secrets 예제를 사용할 수 있지만 별도 API 호스팅은 따로 필요합니다.

공개 API의 도메인, 프록시, rate limit, 접근 로그 보존 기간과 IP 제한은 현재 앱 코드에서 확정하지 않았습니다. 사내 공개 범위와 연동처를 정한 뒤 인프라 설정으로 보완할 항목입니다.

## 설치와 이관 순서

1. 신규 프로젝트라면 테이블과 함수가 충돌하지 않는지 확인합니다.
2. supabase/schema.sql을 한 번 적용합니다. 기존 설치에 반복 실행하지 않습니다.
3. 초기화 수정 전 설치라면 supabase/fix_reset_counts.sql을 적용합니다.
4. 서버 환경과 Auth 계정의 app_metadata.role을 지정합니다.
5. 원본 CSV를 보관하고 import_to_supabase.py로 초기 데이터를 이관합니다.
6. 행 수, 13개 컬럼, 숫자 조회수와 로그 import_key를 비교합니다.
7. UI와 API를 시작하고 역할별 접근과 기록 없는 분석을 확인합니다.

기존 데이터가 다르면 이관 스크립트는 중단합니다. 운영 변경 후 초기 CSV로 재이관하면 안 됩니다. kwd_no 변경과 삭제는 과거 이벤트 해석에 영향을 줄 수 있으므로 원장 코드 재사용을 피합니다.

## 장애 대응

| 증상 | 확인 순서 | 처리 |
|---|---|---|
| 앱이 키 누락 안내 | 저장 모드, URL, 서버 키 존재 여부 | 설정 수정 후 서버 재시작 |
| 로그인 실패 | Auth 계정과 비밀번호, 연결 상태 | 사용자 계정 확인 |
| 로그인 후 권한 없음 | app_metadata.role | 승인된 계정에 member 또는 admin 지정 |
| API 401 | Bearer 헤더, access token 만료, 연동 토큰 | 올바른 토큰 사용과 재인증 |
| API 409 | analysis_id 중복 입력, 소유자, revision | 원인별 새 분석 ID 또는 최신 데이터 |
| DB 쓰기 503 또는 400 | 키 권한, 설치 함수, DB 로그 | 실제 SQL 오류와 함수 배포 상태 확인 |
| UPDATE requires a WHERE clause | 초기화 함수의 WHERE 조건 | 수정 SQL 적용, safeupdate 유지 |
| 리포트가 바로 안 변함 | 기간, visible, 30초 캐시, 누적과 주간 구분 | 새로 불러오기 후 지표 확인 |
| 전체 초기화 뒤 주간 표 유지 | 이벤트 보존 여부 | 정상 의미, 주간 제외는 별도 동작 |

기존 public.keywords의 RLS 미설정과 기존 함수의 search_path 경고는 앱 전용 테이블과 구분해 담당자가 검토해야 합니다. 이 문서가 기존 테이블 사용처의 권한을 자동 변경하지 않습니다.

## 백업과 복구 계획

현재 코드에는 자동 백업, 복구 실행 또는 변경 감사 기능이 없습니다. 앱의 원장 CSV 다운로드는 분석 실행 기록과 전체 이벤트를 포함하는 DB 전체 백업이 아닙니다. Supabase 백업 정책과 복구 가능 시점은 운영자가 프로젝트에서 확인해야 합니다.

개선 제안으로 원장 덮어쓰기 전 변경 승인과 백업, DB 전체 복구 훈련, 계정과 서버 키의 갱신 절차, 원장 편집 이력을 운영 정책에 추가합니다. 목표 복구 시간과 허용 데이터 손실량은 아직 합의하지 않았으므로 임의 수치를 보장하지 않습니다.

## 자동 테스트 범위

| 테스트 | 검증 내용 | 운영 데이터 변경 |
|---|---|---|
| test_service_preserves_all_engine_modes_and_post_filters | 세 모드 직접 엔진과 공통 서비스 결과 | 없음 |
| test_recording_is_opt_in_and_same_id_is_idempotent | record 기본값, ID 재시도와 충돌 | 메모리 가짜 저장소 |
| test_api_auth_validation_and_private_results | 인증, 길이, mode, 조회 소유자, 페이지 범위 | 가짜 저장소 |
| test_snapshot_keeps_more_than_1000_rows_and_extra_columns | 1,431행과 추가 컬럼 유지 | 가짜 응답 |
| test_secret_keys_are_not_sent_as_bearer_tokens | 새 서버 키의 헤더 형식 | 가짜 HTTP |
| test_existing_streamlit_csv_screen_and_member_analysis | 기존 CSV 화면과 분석, 비관리자 차단 | 임시 CSV |
| test_cloud_requires_login_before_data_access | 로그인 전 DB 조회 차단 | 가짜 연결 |
| test_cloud_member_uses_transaction_and_cannot_reset | member 분석과 초기화 차단 | 가짜 저장소 |
| test_user_management_rechecks_admin_and_prevents_self_demotion | 역할 관리 권한 재검증, 자기 권한 해제 차단 | 가짜 HTTP |
| test_user_management_rest_uses_server_key_and_updates_only_app_role | Auth Admin 헤더와 역할 변경 요청 | 가짜 HTTP |
| test_admin_can_assign_missing_role_from_screen | 관리자 역할 지정 GUI | 가짜 저장소 |
| test_admin_common_rules_save_and_apply_on_next_analysis | 관리자 폼 저장, 쉼표 보존과 다음 분석 적용 | 가짜 저장소 |
| test_captured_results_keep_positions_duplicates_and_overlap_rules | 이전 커밋에서 캡처한 27개 사례 비교 | 없음 |
| test_common_rules_preserve_run_options_and_empty_list_fallback | 설정 스냅샷 불변성과 기존 빈 목록 처리 | 가짜 저장소 |
| test_live_reset | 실제 HTTP 누적 초기화와 원장 보존 | 실제 초기화, 명시적 opt in 필요 |

기본 테스트는 14개를 실행하고 live reset 1개는 건너뜁니다. tests/database.sql은 격리된 트랜잭션과 테스트 스키마에서 동작, 중복 집계, 소유자 검사와 초기화 의미를 확인한 뒤 ROLLBACK하는 용도입니다. 운영 원장에 그대로 실행하지 않습니다.

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m pip check
```

## 수동 인수 검수 항목

| ID | 시나리오 | 기대 결과 | 상태 |
|---|---|---|---|
| AT 01 | 미인증 사용자 앱 진입 | 원장 조회 전 로그인 | 자동 테스트 포함 |
| AT 02 | member가 초기화 시도 | 서버와 버튼에서 차단 | 자동 테스트 포함 |
| AT 03 | admin이 업로드 덮어쓰기 | 검증과 revision 검사 후 원장 변경 | 추가 수동 검수 |
| AT 04 | 두 관리자가 같은 원장을 편집 | 오래된 revision의 저장 거절 | DB 함수 검증, 실제 동시 화면 검수 추가 |
| AT 05 | 같은 API ID와 입력 재전송 | 한 번만 집계 | 자동 및 DB 검증 |
| AT 06 | 잘못된 ID 소유자로 조회 | 결과 미반환, 현재 409 | 자동 테스트 포함 |
| AT 07 | 이모지와 정규화 문장 하이라이트 | 원문 범위 일치 | 추가 회귀 사례 필요 |
| AT 08 | Top N 동점과 경계 시각 | 합의된 정렬과 기간 결과 | UI와 API 차이 확인 필요 |
| AT 09 | 누적 초기화 성공 | 0과 빈 마지막 일시, 로그 유지 | 실제 HTTP 검증 이력 있음 |
| AT 10 | 주간 초기화 | 최근 이벤트 제외, 누적 유지 | DB 함수 검증, 실제 UI 검수 추가 |
| AT 11 | 서버 재시작과 세션 만료 | 재인증 또는 안전한 갱신 | 추가 수동 검수 |
| AT 12 | Linux 호스팅 배포 | 로그인, 읽기, 쓰기, 로그아웃 | 배포 후 검수 필요 |

## 성능 검수와 변경 관리

540자 예시를 단일 실행했을 때 정확 일치 약 1.10초와 유사 약 0.72초가 관찰된 이력이 있으나 현재 하드웨어의 SLA나 동시 처리량으로 사용하지 않습니다. 길이별, 모드별, 키워드 수별로 여러 번 측정하고 p50과 p95, CPU와 메모리, DB 호출 시간을 함께 기록해야 합니다. 아직 부하 테스트 완료 수치와 동시 사용자 보장은 없습니다.

코드 변경 시 매칭 회귀와 권한 테스트를 먼저 수행하고 DB 변경은 SQL 이력과 함께 배포합니다. safeupdate 오류는 SQL Editor 직접 호출만 성공해도 HTTP 세션에서는 실패할 수 있음을 보여준 사례입니다. DB 함수와 실제 서버 호출을 모두 확인합니다.

## 기준 소스

`app_config.py`, `.env.example`, `.streamlit/secrets.toml.example`, `render.yaml`, requirements 파일, README와 tests를 확인했습니다. 환경 변수의 실제 값과 사용자 계정 정보는 문서에 포함하지 않았습니다.
