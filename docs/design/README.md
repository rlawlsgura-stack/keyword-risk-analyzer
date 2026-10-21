# Keyword Risk Analyzer 설계 문서 안내

문서 버전 1.0 · 작성 기준 2026년 10월 21일 한국 시간

규정 검색 도입 제안은 2026년 10월 22일 **화장품·식품·건강기능식품 / 외부 AI API 전송 허용**으로 범위를 확정해 갱신했습니다.

이 문서 묶음은 현재 Streamlit 화면과 FastAPI 코드, Supabase에 설치된 `kra_` 테이블과 함수를 기준으로 작성한 구현 기준 설계서입니다. 개발자 인수인계, 외부 시스템 연동, 운영 설정과 기능 검수에 사용합니다. 계획만 있는 기능은 구현 완료 기능과 구분했습니다.

## 문서 구성

| 문서 | 주요 독자 | 내용 |
|---|---|---|
| [시스템 설계서](01_system_design.md) | 기획자와 개발자 | 범위, 기능 요구사항, 아키텍처, 권한과 모듈 |
| [API 설계서](02_api_design.md) | 연동 개발자 | 인증, 6개 경로, 요청과 응답, 오류와 재시도 |
| [화면 설계서](03_screen_design.md) | 기획자와 화면 개발자 | 화면 ID, 배치, 입력, 이벤트, 권한과 예외 |
| [Supabase 설계서](04_supabase_design.md) | 백엔드와 DB 담당자 | ERD, 5개 테이블, 원장 13개 컬럼, RPC 10개 |
| [분석 로직 설계서](05_matching_design.md) | 분석 로직 담당자 | 매칭 모드, 정규화, 겹침 처리, 집계 규칙 |
| [운영 배포와 검증 설계서](06_operations_test_plan.md) | 운영자와 검수자 | 환경 설정, 배포, 이관, 장애 처리, 테스트 |
| [법령·가이드라인 RAG 도입 설계](07_regulation_rag_design.md) | 기획·심의·개발 담당자 | **제안 단계**: 공식 근거 수집, 적용일, 검색, 후속 AI 검토, 배포와 평가 순서 |

`design_book.html`은 위 문서를 한 파일로 열람하고 인쇄할 수 있는 통합본입니다. 외부 스크립트나 폰트를 내려받지 않습니다. `assets`의 SVG는 구성도와 화면 배치도이며, 실제 브라우저 캡처가 아닙니다.

`openapi.runtime.json`은 현재 FastAPI가 생성한 원본입니다. `openapi.json`은 여기에 문서용 응답 스키마와 오류 설명을 보충한 연동 명세입니다. 응답 모델이 실제 서버에서 강제 검증되는 것은 아닙니다.

`reference/regulation_openapi.proposed.json`은 아직 구현하지 않은 규정 검색 API 초안입니다.
`reference/regulation_sources.json`은 공식 게시 정보만 확인한 출처 후보이며 본문 적재·법률 검수 완료 목록이 아닙니다.
`reference/regulation_eval_cases.jsonl`의 26문항은 모두 검수 전 draft입니다.
저장소의 `scripts/evaluate_regulation_retrieval.py`는 향후 승인된 관련성 정답과 실제 검색 결과를 비교하는 오프라인 도구입니다.
전체와 제품군별 검색 지표를 계산하고 범위 검사·생성 모델 안전성 문항은 관련성 점수와 분리합니다.
모델 실행이나 법률 판단은 수행하지 않으며, 검수된 정답이 없을 때 정확도를 계산하지 않습니다.
외부 AI API 연동은 사용자 요청으로 보류했습니다. 초기 공식 조문 3개의 HTML·텍스트 수집본과 출처·해시는
저장소의 `data/regulations`에 보관했으며, RAG DB 적재와 별도 API 서버 배포는 아직 수행하지 않았습니다.

## 사실과 변경 제안의 구분

- **구현**: 코드 또는 DB 메타데이터에서 확인한 현재 동작입니다.
- **관찰**: 문서 작성 시점의 데이터 수와 설치 상태이며 운영 중 달라질 수 있습니다.
- **개선 제안**: 현재 구현 범위에 포함되지 않습니다. 새 작업으로 검토해야 합니다.
- 예제 데이터는 설명용입니다. 실제 계정, 비밀번호, 서버 키와 연동 토큰을 수록하지 않습니다.

## 관찰된 설치 상태

| 항목 | 관찰 값 |
|---|---|
| 업무 저장소 | Supabase 프로젝트 `qmhdwfqcihpfjfvcjcwa` |
| 프로젝트 리전 | Singapore |
| 키워드 | 1,431건 |
| 조회 이벤트 | 9,045건 |
| 분석 실행 기록 | 4건 |
| 키워드와 공통 설정 revision | 1 |
| 원장 컬럼 | 13개 |
| 앱 전용 테이블 RLS | 5개 모두 활성화 |
| 서버 함수 권한 방식 | SECURITY INVOKER 및 서버 전용 EXECUTE |

DB 조회 날짜는 서버 UTC로 2026년 10월 20일이었으며, 문서 작성일은 한국 시간 2026년 10월 21일입니다. 위 수량은 이번 문서 작성 중 읽기 전용 조회로 확인했으며 실시간 지표는 아닙니다.

## 원본과 갱신 방법

기준 소스는 `keyword_app2_fixed270.py`, `api.py`, `service.py`, `repository.py`, `matching_engine.py`, `app_config.py`, `supabase/schema.sql`, `supabase/fix_reset_counts.sql`, `render.yaml`, `tests`입니다. 원본 코드와 설계서가 다르면 코드와 실제 DB를 먼저 확인하고 문서를 갱신합니다.

```powershell
.\.venv\Scripts\python.exe scripts/build_design_docs.py
```

이 명령은 문서와 OpenAPI 산출물만 생성합니다. 계정 생성, DB 이관, 조회수 초기화나 배포를 실행하지 않습니다. 스냅샷 수량은 자동 실시간 조회가 아니라 위 관찰 기록입니다.
`source_manifest.json`의 소스 해시는 운영체제와 Git 개행 변환에 관계없이 비교하도록 UTF-8·LF로 정규화해 계산합니다.
