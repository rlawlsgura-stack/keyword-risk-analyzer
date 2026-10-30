## FIXED310 - Sort unmatched candidates from table headers

- Remove the separate unmatched-expression sort selector and add a sortable registration timestamp column to the candidate table.

## FIXED309 - Reload stale repository sort signature

- Detect and evict a cached repository module that predates the unmatched-term sort argument, avoiding Streamlit Cloud reload failures.

## FIXED308 - Sort unmatched candidates by registration order

- Add a list sort control for frequency or registration time; registration order uses the earliest collection timestamp across the full search result before pagination.

## FIXED307 - Restore login after page refresh

- Persist only the Supabase refresh token in the current browser tab's session storage and restore the authenticated session after a page reload.
- Clear the stored token on logout and refresh the access token five minutes before expiration (the default access-token lifetime remains about one hour).

## FIXED306 - Request administrator registration of normalized candidates

- Rename the candidate normalization action to `선택후보군 정규화 작업`.
- Add a member-facing DB registration request action that submits selected, classified recommendations through the existing keyword request workflow; it does not write directly to the keyword database.

## FIXED305 - Use row selection without a duplicate checkbox column

- Remove the extra candidate checkbox column and use Streamlit table row selection for analysis.
- Keep single-expression editing and selected-row removal available; these only affect the current review session.

## FIXED304 - Rename candidate checkbox to selection

- Label the narrow unmatched-candidate checkbox column "선택".

## FIXED303 - Keep the analysis checkbox column narrow

- Set the unmatched-candidate analysis checkbox column to Streamlit's small width.

## FIXED302 - Select and edit unmatched candidates

- Add checkboxes to choose which current-page unmatched candidates to analyze.
- Allow candidate expression edits and row removal from the review table without changing shared aggregate statistics.

## FIXED301 - Edit and delete each numbered inquiry

- Add owner-only edit and confirmed deletion controls to every numbered user inquiry and follow-up. Deletion removes only that inquiry and its connected replies.
- Display receipt number, keyword number, and keyword name as individually labeled fields.
- Create the initial inquiry when a request is registered so it can use the same per-inquiry controls.

## FIXED300 - Edit and delete own keyword requests

- Allow signed-in request owners to edit the inquiry type and detail, and delete their existing requests after confirmation.
- Enforce ownership in the database, synchronize the initial inquiry text, and preserve administrator answers and workflow status when editing.

## Backend - Direct Law.go.kr search provider (2026-10-28)

- Move law, administrative-rule, precedent, and article requests into `legislation_source.py`; keep question handling and DB/LLM comparison in `regulation_assistant.py`.
- Remove the remote MCP service requirement and its FastMCP dependency; configure the Law.go.kr `OC` key on the authenticated API service as `LEGISLATION_API_KEY`.
- Keep the provider boundary so a future MCP client can reuse the search operations without changing the question flow.

## Backend - Law.go.kr request validation header (2026-10-29)

- Send a `Referer` header with direct Law.go.kr API requests; allow an optional `LEGISLATION_REFERER` override for deployments that register a different domain.
- Preserve upstream HTTP status and a short redacted response excerpt so rejected requests can be diagnosed without exposing the OC key or request URL.
- Redact `OC` credentials embedded in Law.go.kr detail links before showing search results.

## FIXED299 - Reorder report and legal review tabs

- Place `심의 Chat-bot` before `분석리포트` in the main navigation.
- Correct the page title and sidebar version label to `FIXED299`.

## FIXED298 - Rename legal review chat

- Rename the legal-evidence chat tab and heading to `심의 Chat-bot`.
- Keep the user-facing name neutral because the LLM explanation stage is optional and disabled by default.

## FIXED297 - Evidence-first regulation assistant

- Add an optional chat tab for law/precedent lookup from selected OCR candidates or text, and exact DB keyword lookup from a legal article.
- Route Streamlit Cloud requests through the authenticated FastAPI service for official legal-source retrieval.
- Keep LLM explanations disabled by default; when enabled, require source IDs and verbatim quotes and route uncertain/conflicting results to administrator review.

## FIXED296 - OCR button label and upload spacing

- Rename the Korean OCR action to `OCR ?? ??`.
- Use equal vertical padding inside the OCR upload box.

## FIXED295 - OCR upload alignment and candidate numbering

- Vertically center the upload button in the empty OCR dropzone while preserving the responsive multi-image layout.
- Add a `NO.` column to unmatched candidate search results, numbered continuously across pages; local results start at 1.

## FIXED294 - Responsive OCR upload and button layout

- Let multi-image attachment cards wrap and expand inside the uploader across viewport sizes; scope the add-files button style so it cannot stretch file cards.
- Move the Korean OCR run button above the image preview pager controls.

## FIXED293 - Diagnose Cloud unmatched-candidate lookup failures

- Keep shared statistics global across accounts and logout; current production data contains 38 terms, 205 occurrences and 171 term-analysis observations.
- Discard stale repository-module cache entries before running the Cloud app, and log lookup exceptions with safe page diagnostics.
- Reload auxiliary-analysis code revisions so older cached helpers accept the uncapped `limit=None` used by shared collection.

## FIXED292 - Numbered application release

- Create `keyword_app2_fixed292.py` as the next numbered application version.
- Keep `streamlit_cloud/app.py` as the stable Cloud entrypoint and point it to the new app file.
- Adopt whole-number release labels (`FIXED291`, `FIXED292`) for numbered app versions.

## FIXED291.7 - Version metadata

- Bump the displayed local and Community Cloud app version after FIXED291.6.

## FIXED291.6 - Handle missing unmatched-expression counts

- Treat a missing occurrence count as one expression and skip malformed candidate rows instead of aborting the shared aggregation.

## FIXED291.4 - Persistent shared unmatched-expression statistics

- Persist expressions, occurrence/analysis counts and collection times in Supabase for all approved accounts, without account or source-document storage.
- Collect text analyses and original OCR lines at or above 60% confidence automatically; preserve OCR repetitions and avoid collecting again on preview.
- Keep anonymous completed-event IDs for idempotent retries, including after permanent deletion; serialize collection and deletion transactions.
- Add paginated shared lookup, search, full CSV export, pending-save retry and administrator-only confirmed permanent deletion.
- Preserve accumulated statistics when review inputs are reset. CSV mode remains session-local development only.

## FIXED291.3 - Collect unmatched terms from OCR preview

- Collect unmatched terms during the automatic analysis started by the OCR highlight-preview button, without another click on the text-analysis button.
- Respect the candidate-collection checkbox and avoid collecting again on ordinary rerenders.

## FIXED291.2 - Immediate OCR text selection

- Refresh the image preview immediately after OCR results are saved so text can be selected without leaving the OCR tab.
- Reuse the stored OCR results during the refresh; do not run the model twice.

## FIXED291.1 - OCR overlay refresh on deployment

- Reload older OCR helper revisions even when their public function names still match.
- Version the OCR component and widget key so existing browser sessions mount the corrected selection overlay.
- Verify header selection on tall advertisement previews inside Shadow DOM and display FIXED291.1 in the sidebar and browser title.

## FIXED291 - OCR upload layout alignment

- Fit selectable OCR text to each detected box, including resized previews, and prevent image width from collapsing under CSS size containment.
- Match the OCR upload dropzone and empty-state panel widths and heights for admin and user accounts.
- Keep the uploader button at its standard size and use a compact responsive 62px panel layout.
- Point local and Community Cloud entrypoints to FIXED291.

## FIXED290 - OCR approval and unmatched-term review

- Analyze only OCR rows checked in the approval column when opening highlight preview.
- Collect unmatched terms in a temporary session list, normalize on request, and register selected recommendations only after administrator approval.
- Add a dedicated unmatched-candidate tab and align keyword-management typography.
- Point local and Community Cloud entrypoints to FIXED290.

## FIXED289 - OCR text selection bounds

- Normalize OCR text bounding-box width and height by the source image dimensions so browser text selection stays within recognized text.
- Preserve FIXED288 and point the Streamlit Community Cloud entrypoint to FIXED289.

## FIXED288 - Cloud OCR runtime stabilization

- Build on FIXED287 and point the Community Cloud entrypoint to FIXED288.
- Use lightweight PaddleOCR models on Cloud to reduce startup resource use.
- Install required GL runtime libraries from packages.txt.

## FIXED287 - OCR state persistence and navigation labels

- Preserve uploaded OCR images, extracted candidates, table edits, and approval selections across main-tab navigation until reset or save.
- Rename the app title and tab labels, and align the visible tabs in the requested order.

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
