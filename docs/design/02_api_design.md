# Keyword Risk Analyzer API 설계서

문서 ID KRA API 001 · API 버전 1.0.0 · 기준일 2026년 10월 22일

## 인터페이스 원칙

FastAPI가 제공하는 HTTP JSON API입니다. 로컬 기본 주소는 `http://127.0.0.1:8000`이며 운영 도메인은 아직 확정하지 않았습니다. 업무 경로는 `/api/v1` 아래에 있고 상태 확인 경로는 루트에 있습니다. 요청과 응답은 UTF 8 JSON으로 처리합니다. 공개 운영에서는 HTTPS를 사용합니다.

API를 통한 키워드 등록 편집 삭제와 관리자 초기화 경로는 없습니다. 해당 기능은 Streamlit 관리자 화면을 이용합니다. 현재 상태는 동기 요청 처리이며 작업 접수 후 202를 반환하는 비동기 API가 아닙니다.

## 인증과 호출 주체

```http
Authorization: Bearer <USER_ACCESS_TOKEN_OR_INTEGRATION_TOKEN>
Content-Type: application/json
```

- Supabase 사용자 access token은 Auth 서버에서 확인하고 `app_metadata.role`이 member 또는 admin인지 검사합니다. 호출 주체는 사용자 UUID입니다.
- 별도 API 연동 토큰은 `API_ACCESS_TOKEN`과 상수 시간 비교를 수행하고 호출 주체를 `integration`으로 설정합니다.
- Supabase 서버 비밀 키 자체를 외부 호출자에게 제공하지 않습니다.
- 관리자 계정도 저장된 분석 조회 시 타인 소유자 검사를 우회하지 않습니다.
- API 자체에 로그인, 토큰 갱신 또는 비밀번호 변경 경로는 없습니다.

## 경로 목록

| ID | 메서드와 경로 | 인증 | 성공 코드 | 기능 |
|---|---|---|---|---|
| API 01 | GET /healthz | 없음 | 200 | 프로세스 상태 |
| API 02 | GET /readyz | 필요 | 200 | DB 스냅샷 접근 가능 여부 |
| API 03 | POST /api/v1/analyses | 필요 | 200 | 분석과 선택적 기록 |
| API 04 | GET /api/v1/analyses/{analysis_id} | 필요 | 200 | 본인 저장 결과 조회 |
| API 05 | GET /api/v1/keywords | 필요 | 200 | 키워드 조회 검색 페이지 |
| API 06 | GET /api/v1/reports/top-keywords | 필요 | 200 | 기간별 공유 Top N |
| DOC 01 | GET /openapi.json | 없음 | 200 | 기본 FastAPI 명세 |

업무 API 5개 작업과 상태 확인 2개 작업이 런타임 OpenAPI에 등록돼 있습니다. 기본 OpenAPI 제공 경로는 별도입니다. `/docs`는 `API_DOCS_ENABLED=true`일 때만 열리고 `/redoc`은 비활성화돼 있습니다. 기본 `/openapi.json`은 현재 설정에서 별도로 비활성화하지 않았습니다.

## API 01과 API 02 상태 확인

`GET /healthz`는 `{"status":"ok"}`를 반환합니다. DB 장애나 잘못된 서버 키가 있어도 프로세스가 실행 중이면 성공할 수 있습니다.

`GET /readyz`는 인증 후 `kra_snapshot`을 호출하고 `{"status":"ready"}`를 반환합니다. 이 호출은 읽기 경로만 검사합니다. 쓰기 권한, Auth 이메일 로그인, SMTP까지 모두 정상임을 보장하는 검사는 아닙니다.

## API 03 분석 실행

### 요청 필드

| 필드 | 형식 | 필수 | 기본값 | 검증과 의미 |
|---|---|---|---|---|
| text | string | 예 | 없음 | 길이 1 이상 20,000 이하 |
| mode | enum | 아니오 | similar | 화면의 완전 일치는 exact, 일부 일치는 partial+최소2, 글자 수 매칭은 partial+설정길이. similar는 기존 변형 규칙 API 호환용 |
| exact_relaxed | boolean | 아니오 | false | 기존 묶음 옵션, deprecated. 명시한 개별 옵션이 우선 |
| strip_bracket_notes | boolean 또는 null | 아니오 | null | exact/partial의 등록명에서 괄호 설명을 제외해 비교 표현 준비 |
| normalize_whitespace | boolean 또는 null | 아니오 | null | 띄어쓰기·줄바꿈 차이 허용 |
| ignore_case | boolean 또는 null | 아니오 | null | 영문 대소문자 무시 |
| normalize_symbols | boolean 또는 null | 아니오 | null | 공통 기호를 공백으로 치환 |
| partial_min_len | integer | 아니오 | 2 | 2 이상 30 이하 |
| similar_reverse_single | boolean | 아니오 | true | deprecated, 기존 similar 전용 단일 토큰 역매칭 |
| similar_reverse_any | boolean | 아니오 | false | deprecated, 기존 similar 전용 문장 역매칭 |
| categories | string array | 아니오 | [] | 최대 100개, 매칭 전 원장 카테고리 필터 |
| risks | string array | 아니오 | [] | 최대 20개, 매칭 전 원장 등급 필터 |
| record | boolean | 아니오 | false | 분석 결과와 집계를 DB에 기록 |
| analysis_id | UUID 또는 null | 아니오 | null | 생략 시 서버에서 새 UUID 생성 |

정의하지 않은 요청 필드는 허용하지 않아 422를 반환합니다. 공백만 있는 text를 거절하는 별도 검증은 없습니다. 필터 항목의 문자열 길이나 실제 원장 값 존재 여부도 별도 검증하지 않습니다. Pydantic의 기본 변환 규칙을 사용하며 모든 필드에 strict 모드를 지정한 것은 아닙니다.

신규 연동은 네 개별 옵션을 모두 명시하는 방식을 권장합니다. boolean은 JSON true/false 또는 null만 허용하며 문자열은 422를 반환합니다. 개별 false도 기존 묶음 true보다 우선합니다. 네 필드가 전부 생략/null이면 기존 검출 경로를 유지하며, 일부만 명시한 경우 나머지는 기존 묶음 옵션과 모드에서 유도합니다. 세부 기본값은 [분석 로직 설계서](05_matching_design.md)의 개별 표기 비교 옵션을 참고합니다.

`mode=exact`에서 B245 `안티에이징(anti-aging)`을 `안티에이징으로`에서도 찾으려면 strip_bracket_notes=true로 지정합니다. 공백과 대소문자 옵션은 별도로 선택합니다. 기호 치환은 공백 치환이므로 피부&보습과 피부보습을 연결하려면 기호·공백 옵션을 모두 켭니다. 조사·어미 허용 목록은 similar 모드에서만 참조하며 exact의 단어 경계를 제한하지 않습니다.

응답 형식과 경로는 유지합니다. 기록 지문은 생략/null인 신규 필드를 제거하고 계산해 기존 기록의 재시도를 보존하며, 명시한 개별 옵션 값은 지문에 포함합니다.

화면과 같은 검사는 mode=exact 또는 partial과 네 개별 옵션을 명시합니다. partial은 등록 표현의 어느 연속된 조각이든 partial_min_len 이상이면 문장 어디서든 찾습니다. 예를 들어 안티에이징 등록 시 에이징 관리가 필요하다는 최소 3글자 O, 4글자 X입니다. 필터는 매칭 전에 적용하고, 개별 옵션 경로에서는 다른 코드의 겹친 결과를 보존하며 같은 코드의 포함된 짧은 조각만 제거합니다. 호환을 위해 mode 생략 시 기존 similar 기본값은 유지합니다.

### 요청 예시

```json
{
  "text": "필러와 필러",
  "mode": "exact",
  "strip_bracket_notes": true,
  "normalize_whitespace": true,
  "ignore_case": true,
  "normalize_symbols": true,
  "categories": ["화장품"],
  "risks": [],
  "record": true,
  "analysis_id": "b96293da-c6fc-44f8-8c1b-ebee5ee89f21"
}
```

### 성공 응답 예시

아래 예시는 필러가 설명용 코드 B118로 등록된 가상 원장 기준입니다. 실제 검출 개수와 등급은 현재 원장에 따라 달라집니다.

```json
{
  "analysis_id": "b96293da-c6fc-44f8-8c1b-ebee5ee89f21",
  "matches": [
    {"term":"필러","start":0,"end":2,"category":"화장품","risk":"1등급(사용금지)","detail":"예시 심의 기준","kwd_no":"B118"},
    {"term":"필러","start":4,"end":6,"category":"화장품","risk":"1등급(사용금지)","detail":"예시 심의 기준","kwd_no":"B118"}
  ],
  "unique_keywords": ["B118"],
  "keyword_revision": 1,
  "offset_unit": "unicode_codepoint",
  "end_exclusive": true,
  "recorded": true
}
```

| 응답 필드 | 형식 | 의미 |
|---|---|---|
| analysis_id | string UUID | 분석 식별자 |
| matches | Match array | 위치별 검출 결과. 같은 키워드가 여러 번 존재 가능 |
| unique_keywords | string array | kwd_no를 중복 제거하고 문자열 정렬한 목록 |
| keyword_revision | integer | 분석에 사용한 원장과 공통 설정 버전 |
| offset_unit | string | 현재 고정 값 unicode_codepoint |
| end_exclusive | boolean | 현재 true |
| recorded | boolean | DB 기록 요청 여부. true 응답은 기록 함수 성공 후 반환 |

`Match`는 term, start, end, category, risk, detail, kwd_no 필드로 구성합니다. kwd_no는 엔진 자료형상 null일 수 있으나 정상 원장은 비어 있지 않은 고유 코드를 사용합니다. 대체어와 증빙 유형은 Match 응답에 포함되지 않으며 키워드 조회 API에서 확인합니다.

### 위치와 하이라이트 규약

start는 0부터 시작하고 end는 마지막 문자 다음 위치입니다. Python에서는 `text[start:end]`로 구간을 얻습니다. JavaScript의 일반 문자열 인덱스는 UTF 16 단위이므로 이모지가 포함된 원문에서는 `Array.from(text).slice(start,end).join('')`처럼 code point 기준으로 변환해야 합니다. 표시 구간이 항상 원장 term 문자열과 동일하다고 가정하면 안 됩니다. 정규화와 겹침 병합으로 원문 표시 구간이 넓어질 수 있습니다.

### 저장과 재시도

`record=false`이면 DB에 분석 결과와 조회수를 기록하지 않습니다. 이 경우 analysis_id를 받더라도 결과 조회 API에서 찾을 수 없습니다. `record=true`이면 검출 결과가 없어도 API는 분석 실행 기록을 남깁니다. 저장 전 원장 revision을 검사합니다.

입력 지문은 analysis_id와 record를 제외한 요청 객체를 키 정렬 JSON으로 직렬화한 SHA 256 값입니다. 동일 ID와 호출 주체 및 지문이면 기존 결과를 반환하고 조회수를 다시 올리지 않습니다. 다른 입력이나 다른 주체가 같은 ID를 사용하면 409입니다. 같은 ID를 생략해 재시도하면 새 분석으로 처리되므로 기록 요청에는 클라이언트가 UUID를 생성해 재사용하는 것을 권장합니다.

동일 입력 지문에는 엔진 버전이나 조회된 공통 설정 값 자체가 들어가지 않습니다. 이미 기록된 ID는 설정이 바뀌어도 이전 결과를 반환합니다. 새 설정으로 재분석하려면 새 analysis_id가 필요합니다.

## API 04 저장된 분석 조회

경로 변수 analysis_id는 UUID입니다. 결과가 있으면 분석 실행의 결과 JSON을 반환합니다. 존재하지 않으면 404입니다. 현재 구현은 타인 ID 조회에도 409를 반환합니다. 소유자가 아닌 경우 404로 숨기는 방식으로 구현된 것은 아닙니다.

## API 05 키워드 조회

| 쿼리 | 형식 | 기본값 | 허용 범위 |
|---|---|---|---|
| offset | integer | 0 | 0 이상 |
| limit | integer | 100 | 1 이상 500 이하 |
| q | string | 빈 문자열 | 최대 200자 |

kwd_no 기준 문자열 안정 정렬 후 키워드명에 q가 포함되는 행을 대소문자 구분 없이 찾습니다. 정규식 검색이 아닙니다. total은 검색 조건에 맞는 전체 개수이고 items에 현재 페이지를 반환합니다.

```json
{
  "total": 1,
  "revision": 1,
  "items": [{"kwd_no":"B118","키워드명":"필러","상품카테고리":"화장품","리스크 등급":"1등급(사용금지)","키워드 조회 수(누적카운트)":"0"}]
}
```

위 items는 축약 예시입니다. 실제 행에는 원장의 13개 컬럼이 포함될 수 있고 값은 문자열입니다. API는 DB에서 전체 스냅샷을 읽은 뒤 Python에서 검색과 페이지 분할을 합니다. 대량 데이터용 DB 페이지 검색으로 구현된 것은 아닙니다.

## API 06 기간별 Top N

days는 기본 7, 범위 1부터 366입니다. limit은 기본 10, 범위 1부터 100입니다. 서버 DB 시각에서 과거 days일 구간의 visible 이벤트를 집계합니다. 같은 건수면 kwd_no 오름차순이며 조회수는 전체 사용자 공유 통계입니다.

```json
{"items":[{"kwd_no":"B118","hit_count":3,"term":"필러"}]}
```

삭제된 원장 항목의 이벤트도 남아 있으므로 term은 null일 수 있습니다. 기간에 해당하는 visible 이벤트가 없으면 items는 빈 배열입니다.

## 오류와 재시도 규약

| HTTP | 발생 조건 | 응답 형태 | 호출자 처리 |
|---|---|---|---|
| 401 | Bearer 누락, 잘못된 토큰, 역할 미지정 | detail 문자열 | 재인증 또는 역할 확인 |
| 404 | 본인 조회 ID가 없음 | detail 문자열 | ID와 record 설정 확인 |
| 409 | ID 지문 소유자 충돌, revision 충돌, DB 중복 제약 | detail 문자열 | 원인에 따라 ID 또는 최신 데이터 확인 |
| 422 | 길이 범위, mode, UUID, 미정의 필드 오류 | detail 오류 배열 | 요청 필드 수정 |
| 503 | Supabase 연결 장애, 키 또는 권한 문제, CSV 모드 | detail 문자열 | 운영 연결과 서버 설정 확인 |
| 500 | 처리하지 못한 예외 | 서버 기본 처리 | 서버 로그 확인 |

```json
{"detail":"Bearer token required"}
```

인증 누락의 401에는 `WWW-Authenticate: Bearer` 헤더가 있습니다. 모든 401이 동일 헤더를 명시하는 것은 아닙니다. DB SQLSTATE 40001과 23505는 ConflictError로 변환합니다. 그 밖의 DB 오류는 구체적인 SQL 메시지 대신 일반 연결 실패 응답이 나갈 수 있습니다. 명시적인 요청 자동 재시도나 Retry After 헤더는 구현하지 않았습니다.

## 운영과 연동 제약

- 별도 CORS 허용 목록과 브라우저 교차 출처 연동 설정이 없습니다.
- 앱 자체의 rate limit, 배치 분석 API, 비동기 큐와 요청별 타임아웃 취소는 없습니다.
- Supabase HTTP 연결 타임아웃은 5초, 읽기 타임아웃은 30초입니다. 여러 호출을 포함한 전체 API 제한 시간과는 다릅니다.
- 현재 라우트에는 response_model이 없어 서버 응답 스키마의 Pydantic 강제 검증이 없습니다.
- `openapi.runtime.json`은 자동 생성 원본입니다. 보충 명세의 응답 구조는 현재 반환 코드에 근거한 문서 규약입니다.

## 기준 소스

`api.py`의 AnalysisRequest, current_actor와 각 라우트, `service.py`의 analyze, `repository.py`의 request, `supabase/schema.sql`의 분석과 통계 RPC를 기준으로 작성했습니다.
