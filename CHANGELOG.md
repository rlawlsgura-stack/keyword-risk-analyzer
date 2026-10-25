## FIXED284 - Optional keyword selection for new keyword requests

- Allow `????? ????` submissions without selecting an existing keyword.
- Continue requiring an existing keyword selection for the other request types.
- Permit a blank `kwd_no` in Supabase only for new keyword registration requests.

## FIXED283 - New keyword request type

- Add `????? ????` to the keyword inquiry type list.
- Extend the Supabase request type constraint so submissions with the new type are accepted.

## FIXED282 - Per-inquiry feedback and status

- Place one administrator feedback and status form on the selected unanswered inquiry inside its thread card.
- Persist status per user inquiry message and update the request-wide summary together with the reply.
- Save the status, request summary, and administrator reply atomically through an authenticated RLS-enforced RPC.

## FIXED281 - Single-card inquiry threads

- Render each original user inquiry and its replies inside one bordered card.
- Label conversation entries sequentially as Q01, Q01_A1, Q01-R1, Q01_A2; a new inquiry starts a separate card.
- Keep follow-up forms and administrator response targeting attached to the relevant thread.

## FIXED280 - User follow-up inquiry threads

- Users can reply directly to an administrator response within the same numbered inquiry thread.
- Administrators can respond to each user follow-up, with one reply per message enforced by the database.
- Migrated legacy request-row answers into the message history and marked their unknown authorship/time accurately.
- Added requester/admin-specific RLS validation for each reply target.

## FIXED279 ? Admin reply RLS recursion fix

- Supabase logs identified a self-referencing RLS policy as the cause of HTTP 500 on administrator replies.
- Moved reply-target validation into a private, restricted SECURITY DEFINER helper to prevent policy recursion.

## FIXED278 ? Numbered inquiries and one feedback form

- Each user inquiry in a conversation displays a chronological inquiry number.
- The administrator feedback input appears only after selecting an unanswered inquiry number.
- Preserved one-to-one inquiry/reply pairing and request status handling.

## FIXED277 — 문의와 관리자 답변 1:1 연결

- FIXED276을 보존하고 최신 앱 파일을 `keyword_app2_fixed277.py`로 분리했습니다.
- 각 사용자 문의를 개별 항목으로 표시하고, 관리자는 답변할 문의를 지정하도록 변경했습니다.
- 관리자 답변은 대상 사용자 문의 ID에 연결되며 하나의 문의에는 관리자 답변을 하나만 등록할 수 있습니다.
- 사용자의 재문의/댓글은 별도 문의 항목으로 쌓이고 각 항목별로 답변이 표시됩니다.
- 기존 메시지를 사용자 문의와 관리자 답변으로 정리하고, 최초 요청을 대화의 첫 항목으로 추가하는 RLS 마이그레이션을 준비했습니다.

## FIXED276 — 문의 대화 히스토리

- FIXED275를 보존하고 최신 앱 파일을 `keyword_app2_fixed276.py`로 분리했습니다.
- 문의 상세 팝업에 최초 문의, 기존 관리자 답변, 이후의 사용자 댓글과 관리자 피드백을 시간순으로 표시합니다.
- 사용자는 본인 문의에 재문의/댓글을 추가하고, 관리자는 모든 문의에 피드백을 추가할 수 있습니다.
- 새 대화는 별도 append-only 테이블에 저장하고, 소유자/관리자 RLS로 조회·등록을 제한합니다. 기존 문의 상태, 관리자 답변, 삭제 흐름은 유지합니다.
- 기존 Supabase 프로젝트에는 `supabase/keyword_request_messages_setup.sql`을 한 번 적용해야 합니다.

## FIXED275 — 2026-10-25

- FIXED274의 완료 상태를 보존하고 최신 작업 파일을 `keyword_app2_fixed275.py`로 분기했습니다.
- 문의 내역에 처리 상태와 관리자 답변을 관리하고, 접수 상세 팝업에서 수정·삭제할 수 있습니다.
- 하이라이트 미리보기는 내용에 맞는 높이를 유지하고 상세 팝업이 열릴 때만 필요한 공간을 확보합니다.
- 키워드 업로드·삭제 영역과 키워드 입력/관리 레이아웃을 정리하고, 선택 목록 정렬과 컨트롤 크기를 통일했습니다.

## FIXED274 — 백업

- FIXED273을 보존하고 최신 작업 파일을 keyword_app2_fixed274.py로 분기했습니다.

- Added keyword inquiry registration with type and detail fields plus an explicitly named inquiry-history tab.
- Added owner/admin Supabase RLS access and an administrator toggle for optional Resend email alerts. Approval and keyword DB writeback are not implemented.
- Applied the inquiry and notification tables with RLS to the connected Supabase project; deployments remain unchanged.
- Added admin-managed inquiry statuses (`대기`, `검토중`, `처리완료`) and reply text, with owner read-only access and admin-only database updates.
- Display inquiry receipt time as Korean local time in the last column; add status/reply fields to inquiry history. Marking a request complete does not automatically modify keyword records.
- Added a receipt number to the inquiry list and moved status/reply editing into a per-request dialog; administrators can delete requests after explicit confirmation.

## FIXED273 — Auxiliary analysis removed

- Updated the matching and preview help to use numbered, sentence-separated explanations, including the risk-grade color legend.
- Sorted keyword selection lists by their displayed keyword number and other dropdown lists in ascending order.
- Removed the separate Kiwi/embedding candidate-analysis UI and `POST /api/v1/auxiliary-analyses` endpoint from the current app/API.
- Regular partial matching still uses Kiwi through `approved_matching.py`.
- FIXED272 and earlier application files remain as backups; their auxiliary-analysis module is retained for compatibility.

## FIXED272 — 2026-10-23 · 개발 중, 미배포

- 실행 파일: `keyword_app2_fixed272.py`. FIXED271 파일은 수정하지 않고 보존합니다.
- 일부 일치를 `approved_matching.py`의 양쪽 Kiwi 내용어 토큰 전체 비교 + 승인 표현 보완으로 변경합니다.
- 노화방지·항노화 등의 내용어 노화는 입력의 노화와 승인 없이 연결됩니다. 임의 글자 조각 비교는 제외합니다.
- 관리자 공통 분석 규칙에서 키워드별 부분 표현을 승인·삭제합니다. 자동 승인은 없습니다.
- Supabase 사용 시 기존 kra_settings의 approved_partial_expressions_v272 항목에 저장합니다.
  로컬 CSV 모드는 동일 이름의 JSON 파일을 사용합니다. 배포·운영 DB 저장은 이번 작업에서 실행하지 않습니다.
- 등록명 변경 시 기존 승인은 적용하지 않습니다. 반복 위치·키워드 번호·기존 표·CSV·클릭 팝업·집계 계약을 유지합니다.
- 완전 일치, 탐색용 글자 수 매칭, 보조 분석, 기존 FastAPI는 변경하지 않습니다.
- Kiwi 실패 시 일부 일치를 중단하며 기존 조각 검색으로 자동 전환하지 않습니다.
- 실제 사용자 광고 검수 및 운영 배포 전 검증은 별도로 필요합니다.
- 상세 사용법과 제한: `docs/design/08_fixed272_approved_matching.md`.

## FIXED271 — 2026-10-22 · 개발 중, 미배포

- 실행 파일: `keyword_app2_fixed271.py`.
- FIXED270의 문자 기반 매칭과 결과 표·CSV·조회수·하이라이트를 유지합니다.
- 별도 보조 분석 영역에 로컬 Kiwi 형태소 분석과 선택적 임베딩 의미 검색을 추가했습니다.
- 인증된 `POST /api/v1/auxiliary-analyses`를 추가했습니다. 기존 API 경로와 계약 버전 v1은 유지합니다.
- 보조 분석은 기존 검출·통계에 합산하지 않습니다. 임베딩 오류는 Kiwi 결과와 분리합니다.
- 실제 Kiwi 실행 및 회귀 테스트를 확인했습니다. 외부 임베딩은 429 응답으로 실제 검색 품질 검증이 보류되어 있습니다.
- 개발 실행 명령, Render 실행 파일과 테스트·설계서 기준을 FIXED271로 변경했습니다.
- Streamlit Community Cloud의 Main file path는 다음 배포 시 별도로 `keyword_app2_fixed271.py`로 변경해야 합니다.

## FIXED270 — 보조 분석 추가 직전 기준

- 화면 코드: `keyword_app2_fixed270.py`.
- 완전 일치 / 일부 일치 / 글자 수 매칭의 세 선택지와 개별 표기 비교 옵션을 제공합니다.
- 기존 키워드 결과 표·CSV 양식을 유지하며 실제 일치 문구 열은 포함하지 않습니다.
- Kiwi·임베딩 보조 분석 영역을 추가하기 직전의 화면 코드를 보존합니다.

## 버전 보존 범위

두 실행 파일은 `matching_engine.py`, `service.py`, `repository.py` 등 공통 모듈을 공유합니다.
따라서 FIXED270 파일은 화면 코드의 이전 버전이며 전체 시스템·DB의 독립 복원본은 아닙니다.
이 기록만으로 과거 커밋이나 Git 태그를 생성한 것은 아닙니다. 이후 커밋·푸시를 요청받으면
해당 커밋 식별자를 이 이력에 연결해 저장소 전체의 버전을 추적합니다.
버전 구분을 위해 기존 DB 데이터나 사용자 권한은 변경하지 않았습니다.
