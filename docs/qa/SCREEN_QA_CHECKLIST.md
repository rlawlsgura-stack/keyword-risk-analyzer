# React 화면 QA 준비물 및 체크리스트

브라우저 자동화 대신 사람이 같은 입력으로 React와 Streamlit을 확인할 때 사용한다. 이 문서는 실행 절차를 준비한 것이며, 체크된 테스트 항목도 실제 화면에서 확인하기 전에는 통과로 간주하지 않는다.

## 준비된 OCR 자료

| 파일 | 내용 | 기대값 |
|---|---|---|
| `docs/qa/ocr_korean_sample.png` | 개인정보 없는 검정 글자 한 줄 이미지 | `안티에이징` |
| `docs/qa/ocr_blank_sample.png` | 글자가 없는 흰색 이미지 | 추출 0건 안내 |

지원하지 않는 파일은 사용자가 PDF 하나를 준비해 API에서만 확인한다. React 파일 선택기는 `image/*`만 받도록 되어 있어 일반 브라우저 UI에서 PDF를 선택하는 검증은 불가능하다. 실제 OCR API는 현재 체크아웃에서 한글 샘플과 빈 이미지, PDF를 한 번에 처리했고 결과를 아래에 기록했다.

## 계정과 격리 테스트 데이터

화면의 읽기 검수에는 서로 다른 `member`와 `admin` 역할 계정 2개가 필요하다. 이메일 인증이 완료되고 로그인 가능한 계정을 준비한다. 기존 계정의 비밀번호나 토큰을 조사할 필요가 없으며, 운영 계정 대신 전용 테스트 계정을 만든다. 관리자 역할은 Supabase `app_metadata.role`에 있어야 한다.

저장 동작을 확인하려면 개발/스테이징 React와 API 모두 동일한 **운영과 분리된 Supabase 프로젝트**를 바라보게 한다. 운영 Supabase URL 또는 운영 API가 하나라도 연결되어 있으면 OCR 키워드 저장, 분석 실행, 문의 생성, 후보 상태 변경, 사용자 권한 변경은 하지 않는다. 브라우저 개발자 도구의 네트워크 로그와 화면 캡처에서 Authorization 헤더, 토큰, 비밀번호를 제거한다.

최소 fixture는 격리 프로젝트에만 만든다.

- 키워드 3개: 정확 일치용 `QA정확일치표식`, 부분/글자수 매칭용 `QA부분일치표식`, OCR 연결용 `안티에이징`(격리 fixture에서 코드 B245). 코드·카테고리·위험등급·기준·증빙을 채우고 실제 운영 데이터와 분리한다.
- 조회 0건 확인용으로 카탈로그에 없는 문자열 `QA미등록표식`을 사용한다. 분석이 미매칭 후보를 쌓을 수 있으므로 운영에서 실행하지 않는다.
- 미매칭 후보 1개: `QA후보검토표식`, 초기 상태 pending. 상태 변경 및 삭제는 격리 프로젝트에서만 한다.
- 문의 1개: member 소유의 키워드 문의 스레드 1개. 관리자 답변과 사용자 후속 응답을 확인한다.
- 계정 목록: member와 admin 두 계정. 역할 변경 API는 화면 검수에서 호출하지 않는다. 권한 변경까지 검증하려면 별도 disposable 계정을 추가하고 테스트 종료 후 폐기한다.
- CSV 검수용 report는 fixture 분석으로 만든 데이터만 사용하고, 초기화 기능은 호출하지 않는다.

비밀번호·키는 팀의 비밀관리 도구에서 사용자에게 전달하고 `.env`, 이 문서, 커밋, 캡처에 넣지 않는다. 세션은 브라우저에서 직접 로그인해 유지한다.

## 기능 비교표 — 코드와 기존 QA 자료 기준

이 표는 실제 화면 결과가 아니다. Streamlit 기준은 FIXED327/FIXED329 코드와 `docs/design/08_fixed327_react_parity_baseline.md`, React 기준은 `frontend/src/App.tsx`, `frontend/src/api.ts`, API/서비스 구현을 비교한 정적 검토다.

| 기능 | Streamlit 기준 | React 구현 | 현재 코드 기준 판정 | 실제 화면 확인 |
|---|---|---|---|---|
| 스크립트 분석·정확 일치 | 완전일치, 일부일치, 글자수 모드와 옵션을 제공 | 같은 API 매칭 모드/정규화 옵션을 요청 | 기본 분석 흐름 대응. 상태·기본값·오류 배치 차이 가능 | 필요 |
| 정확/부분/글자수 매칭 | `matching_engine.py`와 Streamlit 설정 기준 | API가 공통 매칭 코드를 실행 | 기능 경로 공유. 동일 fixture의 결과/범위 비교는 미실행 | 필요 |
| 카테고리·위험등급 필터 | 분석 전 다중 필터 | 분석 요청에 category/risk 전달 | 요청 필드 존재. 빈 선택, 조합 결과 화면은 미실행 | 필요 |
| 0건·재시도 | 결과 없음과 별도 저장 실패 처리 | 빈 결과와 분석/후보 수집 오류 재시도 지원 | 저장/재시도 흐름 구현 및 자동 테스트 있음. 실제 네트워크 실패 UI 미실행 | 필요 |
| 자동 스크롤 | FIXED327/FIXED329에 명시적 결과 자동 스크롤 구현을 찾지 못함 | 명시적 `scrollIntoView`/scroll-to-result 구현을 찾지 못함 | 코드상 차이 미발견. 브라우저 포커스/스크롤 동작은 미확인 | 필요 |
| 리포트·CSV | 기간 Top N 및 전체 컬럼 CSV | 동일 API 기간 리포트와 CSV | 사용자 관리자 화면·다운로드 확인 완료, 파싱/집계 대조 완료. Excel 열 표시 추가 검수 필요 | Excel 필요 |
| OCR 추출·분석 | 한국어 이미지 OCR 및 선택형 텍스트 오버레이 | 이미지 업로드, 인식 후보 편집, 분석 입력 복사 | 실제 API OCR은 한글 fixture에서 정확히 통과. UI/오버레이는 미실행 | 필요 |
| OCR 후보 저장 | 키워드 등록 흐름 | 현재 revision 확인 후 후보 저장 | 메모리 저장소 API 검증에서 저장 및 충돌 처리 통과. 실제 격리 DB 저장은 미실행 | 격리 DB에서 필요 |
| 미매칭 후보 | 공유 후보 확인·상태·요청·내보내기 | React 후보 관리 페이지/API | 기존 코드/API 테스트 있음. 역할별 화면 동작 미실행 | 필요 |
| 문의 | 문의와 관리자 답변 | thread/message 기반 답변·후속문의·편집 | API와 UI가 존재하고 자동 테스트 있음. 두 역할 간 실제 대화 미실행 | 필요 |
| 관리자 키워드·사용자·후보 기능 | 관리자 전용 원장/계정/등록요청 관리 | React 관리자 페이지 및 API role 재검사 | 메뉴·API 보호 구현. member의 관리자 API 403은 자동 테스트와 아래 격리 스모크로 확인. 저장 UI 미실행 | 필요 |

React는 Streamlit과 별도의 사이드바/카드/페이지 레이아웃이다. 이것은 현재 코드에서 이미 알려진 시각적 차이다. 기능 누락으로 판단하지 말고 같은 계정·입력·revision으로 동작과 결과를 비교한다. React CSV는 수식 시작 셀에 작은따옴표를 붙여 보호하므로 원본 CSV 셀 값은 Streamlit과 다를 수 있다. 이 차이는 화면 검수에서 별도 기록한다.

## 사용자가 수행할 화면 검수

각 행은 `화면 → 조작 → 기대 결과 → 확인할 증거` 순서다. 초기 읽기 검수는 어떤 저장/삭제/초기화도 하지 않는다. 저장 흐름은 격리 환경이 확인된 후에만 진행한다.

| 화면 | 조작 | 기대 결과 | 확인할 증거 |
|---|---|---|---|
| React 로그인 | 테스트 member로 로그인하고 새로고침 | 계정과 member 역할이 보이고 세션이 유지됨 | URL, 역할 배지, 새로고침 전후 캡처. 인증정보 제외 |
| React 스크립트 분석 | `QA정확일치표식` 포함 문장으로 정확 일치 실행 | 해당 키워드와 상세 기준이 한 번 표시됨 | 입력/모드, 결과 행, 하이라이트 캡처와 응답에서 비밀값 제거한 분석 ID/매치 코드 |
| React 일부일치·글자수 | 준비한 두 번째 fixture를 각각 일부일치와 최소 글자수 경계로 검색 | 각 모드의 기대 fixture만 표시되고 경계값이 설명과 일치 | 모드·최소값·결과 코드 캡처 |
| React 필터·0건 | 카테고리/위험등급을 바꾸고 `QA미등록표식` 실행 | 필터 결과가 바뀌며 미등록 문자열은 명확한 0건 상태를 보임 | 필터 선택, 0건 상태 캡처. 운영 데이터에서 실행 금지 |
| React 분석 재시도·스크롤 | 격리 API를 잠시 차단한 경우에만 실패 후 복구해 재시도; 긴 입력에서 결과 위치 확인 | 입력이 보존되고 재시도 성공, 결과로 이동/포커스 동작은 실제 관찰대로 기록 | 실패/복구 캡처, 동일 입력·analysis ID 여부, 결과 후 스크롤 위치 |
| React OCR | OCR 화면에서 `ocr_korean_sample.png` 업로드 후 OCR 실행 | 추출 영역과 후보에 `안티에이징` 표시 | 파일명, 추출 text, 후보 수/캡처. 개인 이미지 사용 금지 |
| React OCR → 분석 | OCR 후보 분석 버튼을 누르고 분석 화면에서 실행 | 입력에 `안티에이징`이 복사되고 B245 fixture가 연결됨 | 후보/분석 입력/결과 코드 캡처 |
| React OCR 빈 결과·재시도 | `ocr_blank_sample.png`를 실행. OCR API가 준비된 테스트 환경에서만 오류 후 재실행 | 0건 안내가 보이고 실패 시 파일을 다시 실행할 수 있음 | 빈 상태·오류·재시도 성공 캡처 |
| React OCR 후보 저장 | 운영과 분리된 스테이징임을 URL과 API 설정으로 확인한 뒤 후보 내용을 완성해 저장 | 새 테스트 코드가 표시되고 새로고침 후에도 격리 카탈로그에 한 번만 존재 | 저장 전후 테스트 DB 행/리비전. 운영 URL이면 생략하고 차단으로 기록 |
| React 리포트·CSV | 기존 사용자 완료 내역을 참고해 같은 기간과 Top N을 조회하고 CSV 다운로드 | 표와 CSV가 같은 순위·행·열을 보임 | 화면/CSV 파싱 결과 및 Excel의 14개 열. 파일 내용 캡처 시 계정·민감정보 제외 |
| React 일반 사용자 후보·문의 | member로 후보 조회/검색; fixture 문의를 열고 후속응답은 격리 DB에서만 제출 | 공유 후보 상태와 본인 문의만 적절히 표시; 문의 메시지가 연결됨 | 페이지·소유자·메시지 순서 캡처, 저장 전후 fixture 상태 |
| React 규정 검색 | 공개 테스트 문구로 조회하고 출처 링크를 확인 | 응답이 기존 키워드 분석 상태와 분리되고 출처/오류 안내 표시 | 질문/출처 제목 및 URL, 화면 캡처 |
| React 관리자 권한 경계 | member 계정으로 관리자 메뉴가 숨겨진 것을 확인하고, devtools에서 읽기 전용 `GET /api/v1/admin/users`만 호출 | 메뉴 미노출, API 403. 쓰기/삭제/역할변경 요청은 보내지 않음 | 메뉴 캡처와 해당 GET의 HTTP 403. 헤더와 토큰 제거 |
| React 관리자 기능 | admin으로 로그인해 키워드·후보 검토·문의 답변·사용자 관리·분류/정규화 설정을 조회 | 관리 메뉴가 보이고 조회 데이터/페이지 이동/검색 정상 | 각 화면 조회 캡처, API GET 상태와 역할. 변경/삭제 버튼은 누르지 않음 |
| Streamlit 비교 | 같은 브라우저 크기에서 위의 읽기/매칭 시나리오를 반복 | 기능 결과는 합의된 기준과 일치. 레이아웃 차이는 별도 기록 | 두 앱 캡처, 입력/모드/카탈로그 revision/결과 차이 표 |

### 첫 번째 화면 검수 절차

1. 사용자 테스트 환경에서 React preview URL과 Streamlit URL을 확인한다. 둘 다 격리된 같은 fixture API/DB를 향하는지 담당자가 확인한다. 운영 URL 또는 불확실한 DB라면 저장이 필요한 단계는 건너뛴다.
2. 위 테스트 member 계정으로 React에 로그인하고 역할 배지와 새로고침 후 세션을 캡처한다. 비밀번호·토큰은 화면 공유나 캡처에 포함하지 않는다.
3. 이미지 OCR 화면으로 이동해 `docs/qa/ocr_korean_sample.png`를 올리고 OCR 실행을 누른다. 추출 문구가 `안티에이징`과 정확히 같은지 비교하고 파일별 성공/후보 표시를 캡처한다.
4. `후보 분석`으로 분석 입력에 복사하고 정확 일치 옵션으로 실행한다. 결과에 fixture B245가 연결되는지 확인한다. 격리 환경임을 확인하지 못하면 분석 버튼은 누르지 않고 여기서 읽기 검수 결과만 보낸다.
5. 아래 증거 양식에 통과/실패/미검증, 화면, 조작, 관찰 결과를 적어 전달한다. 불일치가 있으면 캡처와 비밀값을 제거한 응답 코드만 첨부한다.

검수 결과 양식:

```text
항목:
환경: (테스트/운영/불명 — 불명이면 저장 단계 미실행)
화면 및 조작:
기대 결과:
실제 결과:
판정: 통과 / 실패 / 미검증 / 차단
증거: 캡처 파일명 또는 HTTP 상태 코드 (토큰/개인정보 제외)
```

## Current progress snapshot (2026-11-06)

Status below is based on the dated browser reports in the repository and the latest
`frontend/QA_STATUS.md` entries. “Partial” means the listed sample passed but the full
workflow or role/edge-case coverage has not. No row implies production readiness.

| # | Workflow | Status and evidence | Remaining |
|---:|---|---|---|
| 1 | Login, session, and roles | Partial — local admin login was used for browser QA; local member/admin API role smoke returned the expected 403/200. User-provided screenshot now shows the local React analysis page after the user reports test-account login. | Account/role identity is not visible in the screenshot. Member navigation hiding, session refresh/expiry and role-specific screen checks remain open. |
| 2 | Exact, partial, and character-count matching | Partial — seven same-catalog React/Streamlit cases matched, including highlights and keyword details (`react_streamlit_parity_20261105.txt`). | Broader inputs, nested matches, and boundary combinations. |
| 3 | Search, filters, and empty states | Partial — empty catalog search, reset and empty messaging were observed (`browser_patch_verification_20261105.txt`). | Populated category/risk/evidence filter combinations and filtered CSV contents. |
| 4 | Analysis retry and result focus/scroll | Open — one option-change run lacked a result area until retry; timing cause is unknown. | Reproduce failure/retry and inspect focus/scroll behavior. |
| 5 | Report and CSV | Partial — report download and CSV parsing/count checks passed. | Excel rendering and the 14-column layout; Excel is not installed in the checked environment. |
| 6 | OCR image extraction | Partial — one image produced 15 recognized text items and 13 candidates (`browser_qa_results_20261105.txt`). | Blank-image and error/retry behavior in the signed-in UI. |
| 7 | OCR candidate review and analysis handoff | Partial — candidate selection/validation and copying selected text to analysis input were observed. | Full follow-through across representative cases and error recovery. |
| 8 | OCR candidate persistence | Sample verified — one synthetic candidate saved successfully and was removed afterward. | Broader classification/error cases; Render behavior remains separate and unverified. |
| 9 | Unmatched candidate selection | Partial — selected all 144, retained selection on page 2, then cleared it (`unmatched_followup_browser_qa_20261105.txt`). | Search/sort changes, processed-status mixtures, concurrent changes, and over 1,000 rows. |
| 10 | Normalization workspace and draft persistence | Partial — two-row save/re-entry/load restored contents, newline, order and selection; empty draft persisted after refresh (`draft_persistence_qa_20261105.txt`). The user also added an unsaved blank row, accepted the load-overwrite confirmation, and reported returning to 0 rows/0 selected. | Broader row-content/selection overwrite cases remain open. The prompt is based on row count, not a dirty-state check, so it also appears when rows have not changed. |
| 11 | Registration requests and review | Open — no registration request, approval, or rejection was submitted. | Member submission and admin review in a safe local fixture. |
| 12 | Keyword inquiries | Partial — Korean notification text and keyword search were checked. | Member create/edit/delete and admin reply/follow-up conversation. |
| 13 | Regulation chat | Open — no signed-in browser result was recorded. | Query, sources, error display, and independence from analysis state. |
| 14 | Keyword, user, and normalization administration | Partial — keyword/normalization views and API role guards were checked. | Full member UI boundary, admin editing workflows, pagination and persistence. |
| 15 | Cross-page Streamlit/React parity | Partial — analysis results were compared on seven same-data cases. Source review confirms `streamlit_cloud/app.py` selects FIXED329; its source differs from the FIXED327 baseline only in the version text. React has counterparts for the top-level functions, with registration review and normalization under admin subpages. | This confirms source routing/scope only. Remaining screen layouts, interactions, filters, exports and role workflows need browser comparison. |

The prior “58-item parity review” phrase in `frontend/QA_STATUS.md` is historical and is
not backed by a canonical 58-row checklist in this repository. Use the 15 workflows above
as the current count until a finer-grained, evidence-linked matrix is approved. The overall
effort is therefore substantial: 3 workflows have no browser evidence yet, 12 have partial
or sample-only evidence, and none closes every criterion in its group. Excel display remains
a blocker. The overwrite confirmation is now covered for the unsaved-blank-row to saved-empty-draft
case; broader replacement cases remain open.
