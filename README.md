# Keyword Risk Analyzer

## 설계 문서

[통합 설계서 HTML](docs/design/design_book.html), [개별 설계서 안내](docs/design/README.md),
[설계 문서 ZIP](docs/keyword_risk_analyzer_design_v1.zip)을 제공합니다.
시스템, API, 화면, Supabase, 매칭 로직, 운영 배포와 검증을 현재 구현 기준으로 정리했습니다.

[법령·가이드라인 RAG 도입 설계](docs/design/07_regulation_rag_design.md)는 별도 **제안 단계** 문서입니다.
기존 키워드 검사에 공식 근거 검색을 추가하고, 검색 품질 확인 후 선택적으로 AI 검토를 도입하는 구성을 설명합니다.
아직 운영 앱에 규정 검색·LLM 판정 기능이 연결된 것은 아닙니다.
2026-10-22 확정한 1차 범위는 **국내 화장품·식품·건강기능식품**이며 **외부 AI API 전송 허용**을 반영했습니다.
관리형 임베딩·생성 API를 우선 평가하고 BGE-M3와 검색 품질·비용을 비교하는 계획입니다.
외부 AI API 연동은 사용자 요청에 따라 보류했습니다. [공식 원문 수집본 안내](data/regulations/README.md)에
초기 수집 자료의 출처와 검수 상태를 기록했습니다. RAG용 DB 적재·별도 API 배포는 아직 수행하지 않았습니다.


기존 Streamlit 화면과 별도 FastAPI가 같은 Python 분석 엔진과 Supabase 저장소를 사용합니다.
Streamlit은 API 서버를 거치지 않고 공통 모듈을 직접 호출하므로 API 서버가 중단돼도 화면을 독립적으로 운영할 수 있습니다.

```text
Streamlit ──┐
            ├─ service.py / matching_engine.py ─ repository.py ─ Supabase
FastAPI ────┘
```

## 현재 구축 상태

- 연결 프로젝트: `qmhdwfqcihpfjfvcjcwa` (Singapore).
- `supabase/schema.sql`이 해당 프로젝트에 `keyword_risk_server_storage` migration으로 적용됐습니다.
- 조회수 초기화의 안전한 갱신 조건은 `fix_keyword_count_reset_safeupdate` migration으로 반영했습니다. 기존 별도 설치에는 `supabase/fix_reset_counts.sql`을 적용합니다.
- 로컬 키워드 1,431개·13개 컬럼과 조회 로그 9,037건을 `kra_` 테이블에 복사했습니다.
- 빈 누적 조회수 21건은 숫자 `0`으로 정규화했습니다. 나머지 원장 필드는 보존합니다.
- 로컬 CSV, 기존 `public.keywords`, 다른 앱의 테이블과 권한은 변경하지 않았습니다.
- 서버 비밀 키와 사용할 계정의 역할 지정은 운영자가 관리합니다. 화면은 Streamlit Community Cloud 사용을 기준으로 합니다.
- `render.yaml`은 별도 서버 배포 예시입니다. RAG 모델 서버와 규정 검색 API의 추가 배포는 아직 수행하지 않았습니다.

## 설치와 실행

현재 Windows/Python 3.14 환경에서 검증했습니다. Linux 호스팅에서의 최종 동작은 배포 후 확인해야 합니다.

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
Copy-Item .env.example .env
```

`.env`에서 다음 값을 설정합니다. 비밀 키는 채팅이나 Git에 올리지 않습니다.

```dotenv
STORAGE_BACKEND=supabase
SUPABASE_URL=https://qmhdwfqcihpfjfvcjcwa.supabase.co
SUPABASE_SECRET_KEY=실제_서버_비밀_키
API_ACCESS_TOKEN=별도로_생성한_연동용_토큰
API_DOCS_ENABLED=false
```

`SUPABASE_SECRET_KEY`는 Supabase Dashboard의 Project Settings → API Keys에서 확인합니다.
`sb_secret_...` 또는 기존 `service_role` 키를 사용합니다. publishable/anon 키는 이 서버 저장소용 키로 사용할 수 없습니다.
로컬에서는 `.env`, 배포 서버에서는 환경 변수를 사용합니다. 프로세스 환경 변수가 파일보다 우선합니다.
Streamlit Community Cloud에서는 `.streamlit/secrets.toml.example` 내용을 앱 Secrets에 설정할 수 있습니다.

서로 다른 터미널에서 두 프로세스를 실행합니다.

```powershell
# Streamlit: http://localhost:8501
.\.venv\Scripts\python.exe -m streamlit run keyword_app2_fixed270.py
```

```powershell
# API: http://localhost:8000
.\.venv\Scripts\python.exe -m uvicorn api:app --host 127.0.0.1 --port 8000
```

`STORAGE_BACKEND=csv`는 기존 CSV를 사용하는 로컬 개발 모드입니다.
CSV 모드에서 API의 업무 엔드포인트는 503을 반환합니다. 공유 운영 시 CSV로 자동 전환하지 않습니다.
CSV 모드의 관리자 로그인은 기존 `ADMIN_USER`·`ADMIN_PASSWORD` 설정을 사용합니다.

## 계정과 권한

Supabase Auth에 사내 사용자 계정을 생성하거나 초대하고, 사용자 `app_metadata.role`을 `member` 또는 `admin`으로 지정합니다.
사용자가 수정할 수 있는 `user_metadata`는 권한 판단에 사용하지 않습니다.
관리자가 SQL Editor에서 정확한 사용자 UUID를 확인한 뒤 다음처럼 설정할 수 있습니다.

```sql
-- 실제 사용자 UUID로 바꿔 실행합니다. 다른 app_metadata 값은 유지합니다.
update auth.users
set raw_app_meta_data = coalesce(raw_app_meta_data, '{}'::jsonb)
    || '{"role":"admin"}'::jsonb
where id = '실제-사용자-UUID'::uuid;
```

- `member`: 분석, 키워드 읽기, 본인 API 분석 결과, 공유 통계 조회.
- `admin`: member 권한 + 키워드 편집·업로드·삭제, 공통 설정 저장, 조회수 초기화.
- 일반 사용자에게는 분석하기·리포트 탭만 표시하고, 키워드 관리 탭은 관리자에게만 표시합니다.
- 리포트의 조회수 초기화 영역(제목·확인 체크박스·실행 버튼)은 관리자에게만 표시합니다.
- 연동용 `API_ACCESS_TOKEN`: 분석·키워드·공유 통계 API만 허용합니다. 관리자 쓰기 권한은 없습니다.
- 연동용 토큰을 공유하는 프로그램들은 같은 연동 주체로 취급됩니다.

### 사용자 역할을 화면에서 변경하기

Supabase 모드에서 관리자 계정으로 로그인하면 **사용자 관리** 탭이 표시됩니다.
**사용자 목록 불러오기 / 새로고침** → 이메일 선택 → 일반 사용자(`member`) 또는 관리자(`admin`) 선택
→ 변경 확인 체크 → **역할 저장** 순서로 이용합니다. 목록은 페이지당 최대 50개이며,
권한이 아직 없는 기존 계정에도 역할을 부여할 수 있습니다. 계정 생성은 Supabase Authentication → Users에서 수행합니다.

서버가 목록 조회와 저장마다 Auth에서 관리자 역할을 재검증합니다. 자신의 관리자 권한 해제는 차단하고,
저장 전 대상 계정의 역할이 목록과 다르면 새로고침을 요청합니다. Auth Admin API로
`app_metadata.role`만 갱신하여 다른 메타데이터는 유지합니다. 일반 사용자와 CSV 모드에는 이 탭이 표시되지 않습니다.
대상 사용자는 변경 후 로그아웃하고 다시 로그인하세요. 이 기능에는 새 테이블, SQL 설치, 별도 API 배포가 필요하지 않습니다.

### 검사 방식과 공통 분석 규칙

분석하기 탭에서는 **키워드 찾는 방식**(등록 표현 / 단어·변형 규칙 / 키워드 일부),
이번 분석의 표기 차이 허용 옵션과 **적용 중인 규칙 요약**을 제공합니다.
기존 검사 모드와 초기값, 합성어·겹침·중복 검출 동작은 유지합니다. 화면 표시 이름만 바꾸며 API의
`exact` / `similar` / `partial`과 요청·응답 형식은 유지합니다.

관리자는 **키워드 관리 → 공통 분석 규칙 — 모든 사용자에게 적용**에서
**키워드 뒤에 붙는 말 허용 목록**과 **띄어쓰기·기호 처리 규칙**을 편집합니다.
입력 후 각 저장 버튼을 눌러야 공통 적용됩니다. 기호는 한 줄에 하나씩 입력하며 쉼표도 그대로 저장할 수 있습니다.
기호 목록을 비우면 기존 기본값으로 돌아갑니다. 동작하지 않던 자동 접미사 후보 안내는 화면에서 제거했습니다.

Streamlit과 API는 공통 규칙을 읽어 이번 분석 옵션과 함께 변경 불가 `MatchingConfig`로 전달합니다.
엔진은 비교 준비, 모드별 검출, 겹침 정리와 위치 정렬로 분리되어 있습니다.
합성어 허용 범위 변경과 기존 중복 결과 제거는 후속 동작 변경 작업으로 남겨두었습니다.

Streamlit은 로그인 전 데이터를 읽지 않고, 매 실행 시 Auth 서버에서 사용자와 역할을 확인합니다.
API도 Supabase 사용자 access token을 Auth 서버에서 검증합니다. 서명 검증 없이 JWT 내용을 신뢰하지 않습니다.

`kra_` 테이블은 RLS를 켜고 `anon`·`authenticated`의 직접 접근을 차단했습니다.
데이터 접근은 서버 비밀 키로만 실행합니다. 이 키는 RLS를 우회하므로 Streamlit/API의 권한 검사와 분석 소유자 검사가 접근 경계입니다.
직접 클라이언트 접근을 허용하는 RLS 정책은 의도적으로 만들지 않았습니다.

기존 `public.keywords`에는 RLS가 꺼져 있다는 보안 진단이 남아 있습니다.
기존 사용처의 정책을 확인하기 전까지 이 작업에서 권한을 변경하지 않았습니다.
다음은 기존 테이블 담당자가 접근 정책과 함께 검토할 SQL이며, 새 `kra_` 테이블 설치 과정에서는 실행하지 않습니다.

```sql
alter table public.keywords enable row level security;
-- 필요한 접근 범위에 맞는 GRANT와 RLS 정책을 함께 정의해야 합니다.
```

[Supabase RLS 문서](https://supabase.com/docs/guides/database/postgres/row-level-security)

## 별도 API

법령 근거 검색의 제안용 계약은 [regulation_openapi.proposed.json](docs/design/reference/regulation_openapi.proposed.json)에
분리했습니다. 현재 런타임 OpenAPI와 아래 운영 경로에는 포함되지 않습니다.

`/healthz`를 제외한 아래 엔드포인트는 `Authorization: Bearer TOKEN`이 필요합니다.
TOKEN에는 Supabase 사용자 access token 또는 서버에 설정한 `API_ACCESS_TOKEN`을 넣습니다.
Supabase 서버 비밀 키를 외부 API 호출자에게 전달하지 않습니다.

| 메서드 | 경로 | 기능 |
|---|---|---|
| GET | `/healthz` | 프로세스 상태 |
| GET | `/readyz` | 인증 및 DB 연결 확인 |
| POST | `/api/v1/analyses` | 분석 실행, 선택적 집계 저장 |
| GET | `/api/v1/analyses/{analysis_id}` | 본인에게 저장된 분석 결과 |
| GET | `/api/v1/keywords?offset=0&limit=100&q=필러` | 키워드 검색·페이지 조회 |
| GET | `/api/v1/reports/top-keywords?days=7&limit=10` | 기간별 공유 통계 |

키워드 쓰기는 기존 Streamlit 관리자 화면에서 수행합니다. 별도 쓰기 API는 추가하지 않았습니다.
`API_DOCS_ENABLED=true`이면 `/docs`에서 API를 확인할 수 있습니다.

```powershell
$headers = @{ Authorization = "Bearer $env:API_ACCESS_TOKEN" }
$body = @{
    text = '필러와 안티에이징이 포함된 문장입니다.'
    mode = 'exact'
    exact_relaxed = $true
    record = $true
    analysis_id = 'b96293da-c6fc-44f8-8c1b-ebee5ee89f21'
} | ConvertTo-Json
Invoke-RestMethod -Uri 'http://localhost:8000/api/v1/analyses' `
    -Method Post -Headers $headers -ContentType 'application/json; charset=utf-8' `
    -Body ([System.Text.Encoding]::UTF8.GetBytes($body))
```

`.env`는 앱 프로세스가 읽습니다. 위 PowerShell 예제의 `$env:API_ACCESS_TOKEN`은 호출 터미널에도 별도로 설정해야 합니다.

- `mode`: `exact` / `similar` / `partial`.
- 분석 입력은 최대 20,000자입니다.
- `record` 기본값은 `false`입니다. `true`일 때 분석 결과·키워드별 집계·로그를 한 트랜잭션으로 저장합니다.
- 재시도에는 같은 `analysis_id`를 사용합니다. 같은 ID·사용자·입력이면 저장된 결과를 반환하고 중복 집계하지 않습니다.
- 새로운 분석에는 새로운 UUID를 사용합니다. 같은 ID를 다른 입력에 사용하면 409입니다.
- `categories`, `risks`는 기존 화면과 동일하게 매칭 후 적용합니다.
- `start`·`end`는 원문의 Unicode code point 기준이며 `end`는 끝 다음 위치입니다.
- 원문 전체는 DB에 저장하지 않습니다. 입력 지문과 검출 결과를 저장합니다.
- 키워드·공통 설정 버전이 분석 도중 변경되면 저장 시 409입니다. 최신 데이터로 다시 분석해야 합니다.
- 동기 Python 분석 엔진을 사용하며, 동시 처리량은 실제 서버에서 부하 측정 후 조정해야 합니다.

## 저장 구조와 기존 동작

| 테이블 | 역할 |
|---|---|
| `kra_keywords` | kwd_no, 원장 컬럼 JSONB, 숫자 조회수, 마지막 출력일자 |
| `kra_state` | 원장 컬럼 순서, 키워드·설정 변경 버전 |
| `kra_settings` | 드롭다운, 조사·어미 추가분, 무시 기호 |
| `kra_runs` | 분석 ID, 호출 주체, 입력 지문, 결과 |
| `kra_hits` | 분석별 키워드 이벤트와 기존 CSV 로그 |

원장 전체는 단일 JSON 스냅샷 RPC로 읽어 기본 1,000행 반환 제한을 피합니다.
관리자 저장은 버전이 일치할 때만 원자적으로 반영하고 기존 행의 조회수는 보존합니다.
클라우드 표 편집에서는 kwd_no·집계 컬럼을 잠급니다. 신규 등록과 삭제는 전용 화면을 사용합니다.
기존 로그는 분석 ID를 추측해 합치지 않고 개별 로그로 보존합니다.

한 분석에서 같은 키워드가 반복 검출돼도 조회수는 한 번만 증가합니다.
누적 초기화는 로그를 유지하고 누적 조회수·마지막 일시만 초기화합니다.
주간 초기화는 최근 7일 이벤트를 리포트에서 제외하고 누적 조회수는 유지합니다.
주간 초기화 후에도 API 중복 요청 검사를 위해 원래 이벤트는 보존합니다.
시각은 DB에서 timestamptz로 저장하고 화면·기존 CSV 일시는 Asia/Seoul 기준으로 처리합니다.
주간 리포트 캐시는 30초 후 갱신되며, 현재 화면에서 분석·초기화하면 즉시 무효화합니다.

다른 Supabase 프로젝트에 설치할 때만 `supabase/schema.sql`을 먼저 적용하고 다음 명령을 실행합니다.
이미 설치된 프로젝트에 schema.sql을 다시 실행하지 않습니다.

```powershell
.\.venv\Scripts\python.exe scripts/import_to_supabase.py
```

이관 스크립트는 기존 데이터가 다르면 중단하고, 동일한 로그는 import_key로 중복 삽입을 막습니다.
기존 데이터가 운영 중 변경된 뒤에는 초기 이관을 다시 실행하지 않습니다.

## 배포

`render.yaml`은 Streamlit과 API를 별도 Render Web Service로 배포하는 설정입니다.
상시 실행을 위해 `starter` 플랜을 명시했으며, 실제 배포 시 비용이 발생할 수 있습니다. 이 작업에서는 호스팅 서비스를 생성하지 않았습니다.
두 서비스에 동일한 Supabase URL·서버 키를 설정하고, API 서비스에만 별도 연동 토큰을 설정합니다.
실제 공개 접속은 HTTPS를 사용합니다. API에는 브라우저용 CORS를 열지 않았습니다.

배포 후 `/healthz`, 인증이 필요한 `/readyz`, 일반 계정 분석, 관리자 저장, 로그아웃을 확인합니다.
통계와 원장 원본은 Supabase에 있으므로 앱 서버의 로컬 파일 보존에 의존하지 않습니다.

## 검증

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m pip check
```

`tests/test_integration.py`는 세 매칭 모드의 엔진 결과 보존, API 인증·입력 제한·소유자 검사,
집계 재시도, 1,431행 조회, 서버 키 헤더, CSV 화면 분석, 클라우드 로그인과 일반 사용자 분석을 확인합니다.
사용자 관리의 일반 사용자 접근 차단, 저장 시 관리자 재검증, 자신의 권한 해제 차단,
미지정 계정의 GUI 역할 부여와 Auth Admin 요청 형식도 검증합니다.
화면 테스트는 임시 CSV 또는 가짜 저장소를 사용합니다. 실제 CSV 조회수와 로그를 변경하지 않습니다.

`tests/test_matching_regression.py`는 리팩터링 전 커밋 `2d17555`에서 캡처한 27개 사례를
`tests/fixtures/matching_baseline.json`과 비교합니다. 기존 인수 방식과 설정 스냅샷 방식 모두에서
검출 위치, 중복과 겹침 결과를 보존하는지 검사합니다. 관리자 규칙 저장·다음 분석 적용,
일반 사용자의 편집 기능 미노출, 쉼표 저장과 여러 글자 기호 저장 차단도 검증합니다.

`tests/database.sql`은 새 스키마와 함께 트랜잭션 안에서 실행한 뒤 ROLLBACK하는 DB 검증입니다.
설치된 운영 데이터에 직접 실행하지 않습니다. 클라이언트 권한 차단, 버전 충돌,
조회수 보존, 중복 집계 방지, 초기화 의미, 1,000행 초과 스냅샷을 검증했습니다.

`tests/test_live_reset.py`는 실제 HTTP 경로로 초기화를 검증합니다. 일반 테스트에서는 건너뛰며,
`KRA_TEST_LIVE_RESET=1`을 지정할 때만 실행합니다. 실행하면 실제 DB 누적 조회수와 마지막 출력일자가 초기화됩니다.
