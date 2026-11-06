# React transition QA status

## 2026-11-05: follow-up unmatched-review parity patch

- Follow-up to `react_parity_fixes.patch`; prepared in the separate checkout, not applied to the
  user's Windows working tree or its running browser.
- Added search-wide selection of requestable candidates using all server-filtered result pages,
  plus candidate-selection reset. Existing selections in other searches and cross-page selections
  are preserved; permanent-delete selections remain separate. Count changes, duplicate rows, and
  incomplete pagination reject the new selection rather than applying a partial result. Search,
  sort, account, or page changes invalidate an in-flight selection. The API has no transactional
  candidate snapshot, so unchanged-count concurrent mutations cannot all be detected.
- Added a blank first/last recommendation row, insertion above/below exactly one selected row,
  and removal of selected workspace rows. The empty workspace remains available so users can
  save removal of the final row. These controls never delete persisted candidates or catalog rows.
  Existing draft-save and registration-request APIs are reused; saved row order/IDs are preserved.
- Added replacement confirmation for generating new recommendations or loading saved rows over
  an existing workspace. Empty manual rows have distinct accessible field labels.
- Automated checks: frontend tests total nine (six API tests, three row-editing tests), plus
  TypeScript/Vite production build and `git diff --check`. No dependencies were added.
- Still unverified: this patch's browser interactions and live draft save/reload, registration
  submission, and general-member behavior. No database writes or role changes were performed.
  Drag-fill, recommendation-table column tools/CSV/fullscreen, and the remaining tab-parity gaps
  are not completed by this patch.

## 2026-11-05: local empty-database regressions and list-filter restoration

- Reviewed GitHub `main` at `0186543b866302e87d1af1ddd7c74843c5fd08a6` in a separate checkout.
  This checkout is not the Windows directory serving the connected local browser.
- Fixed `/api/v1/keywords` raising an exception when a nonempty search query was used
  against an empty catalog. The same endpoint serves inquiry-keyword searches.
- Fixed administrator normalization settings raising an exception when no saved symbol
  settings existed; it now returns the matching engine's default symbols without saving them.
- Restored the keyword list and its three classification filters directly on the analysis
  page for both members and administrators. The existing catalog page shares the same UI.
  Added filter reset, repeat-query refresh, an explicit empty state, and filtered CSV export
  across all result pages while retaining the separate full-catalog CSV export.
- Checks: five read-only FastAPI tests pass (empty search/filters, nonempty literal search,
  normalization defaults, stored settings, member-role rejection); three frontend API tests
  pass (filtered pagination, unfiltered empty catalog, revision conflict). TypeScript/Vite
  production build and whitespace checks pass. Tests use stubs and no live database.
- Not verified: further UI interactions/screens, live DB-backed inquiry/settings reads,
  filter reset interaction, downloaded CSV contents in Excel, or the remaining tab-parity
  gaps. No database values, user roles, production deployment, or Windows files were changed
  by this checkout. These fixes do not complete the full parity review; use
  `docs/qa/SCREEN_QA_CHECKLIST.md` for the current itemized progress snapshot.

## Completed

- [x] React production build (`npm run build`) succeeds.
- [x] Render React and API services are live; API health, CORS, and the React API paths were checked against the deployed OpenAPI document.
- [x] Password recovery email and reset link completed successfully against the live Supabase project.
- [x] Signed-in text analysis matched the sample terms `필러` (B118) and `안티에이징` (B245), recorded the run, and showed each keyword's details.
- [x] The live seven-day Top 10 database function included B245 at rank 2 with 47 hits and B118 at rank 3 with 43 hits when checked on 2026-11-02. Counts change as new analyses are recorded.
- [x] Admin API role checks were reviewed in the API implementation.
- [x] CSV exports prefix formula-leading values as text; the React preview deployment's JavaScript bundle contains this guard.
- [x] Confirmed production data is available for the catalog, unmatched-candidate review, and inquiry screens: 1,431 keywords, 571 candidates (564 pending, 7 ignored), and 3 inquiry threads with 6 messages on 2026-11-03.
- [x] React report supports arbitrary inclusive date ranges in Korea Standard Time; the FastAPI endpoint and service-role-only Supabase RPC were deployed and the RPC returned Top 10 results (2026-11-03).
- [x] Render API service uses Python 3.13.15 and installs `requirements-ocr.txt`; the deploy completed successfully with PaddlePaddle 3.3.1 and PaddleOCR 3.7.0. API health and OpenAPI return HTTP 200, and the React preview returns HTTP 200 (2026-11-03).
- [x] FIXED327 parity API commit `816311fad9ccad868f319b4870e2c6b2ec09dcef` deployed to the Render API service; deployment status is `live`, API OpenAPI reports version `1.1.0`, and the analysis/report endpoints reference `CurrentAnalysisResponse` and `TopKeywordsResponse` (2026-11-03).
- [x] Rebuilt the React frontend after the FIXED327 parity changes with `npm run build`; TypeScript and Vite completed successfully (2026-11-03).
- [x] `git diff --check` completed without whitespace errors (2026-11-03).
- [x] Full local Python suite completed: 101 passed, 9 skipped, 187 subtests passed (2026-11-03). The run exposed and fixed a response-shape inconsistency where legacy v1 analysis retries gained the new v2 catalog-row fields; detailed keyword rows are now added only on the current v2 analysis path.
- [x] Updated the integration assertion to compare matching-engine fields while allowing the intentional detail metadata added to serialized matches (2026-11-03).
- [x] Commit `50c6e694da52bfb3ae1144a0e6fbef9c5ef7d949` is live on the Render API service. Unauthenticated smoke checks for keyword catalog, report, unmatched candidates, and administrator users all returned HTTP 401 (2026-11-03).
- [x] Compared the Streamlit FIXED327 and FIXED329 source files: they differ only in the module description and `APP_VERSION` label, so the FIXED329 screen shown during this review retains the FIXED327 implementation (2026-11-03).
- [x] Reworked the React top-level navigation to use the FIXED327 title and horizontal tab order; React-only catalog, registration review, and normalization pages remain reachable from their corresponding catalog/management areas rather than adding top-level tabs (2026-11-03).
- [x] Aligned React analysis persistence with FIXED327: unmatched-term collection runs independently and may be retried without hiding results; analysis history is written only when at least one keyword matched. The React UI keeps the same analysis ID and input for retry and blocks logout during analysis/save processing or while candidate saving remains pending (2026-11-03).
- [x] Added service and API coverage for no-hit history behavior and candidate-save failure/retry; full Python suite passes with 103 passed, 9 skipped, and 187 subtests. React TypeScript/Vite production build and `git diff --check` pass (2026-11-03).
- [x] Commit `8d828c3ab161e6f1da2208979ae4e8a732cae519` was pushed to `main` and deployed live to the Render API (`dep-dbkuct2jnfac73a030s0`) and React preview (`dep-dbkucu15efls73fn08ag`). Verified API `/healthz`, OpenAPI's `unmatched_collection_pending` response field, unauthenticated keyword API returning HTTP 401, and React preview HTTP 200 with the retry flow in its deployed bundle (2026-11-03).
- [x] React logout protection commit `072f48bd993f6ccba897a146d02e7258ef97a3bb` deployed live to the preview (`dep-dbkuf1nb9u1s738fji90`); verified the active JavaScript bundle contains the pending-save retry flow and logout guard (2026-11-03).

## Remaining before switching the production UI

- [x] User verified admin login, the 2026-10-30–2026-11-05 Top 10 report, and CSV download. The downloaded CSV parses as 10 rows, and its period counts match the live event log (2026-11-05).
- [x] `unmatched_candidates.csv` has a UTF-8 BOM, 6 columns, 5 data rows, and Hangul content; the user confirmed its date and count values are normal.
- [ ] Excel is not installed in this environment; visual rendering of the downloaded report CSV and its 14-column layout remain unverified.
- [x] The user reports progress comparing major React and Streamlit screens.
- [x] User-reported React/Streamlit comparison matched on seven same-data cases (2026-11-05); this is sample coverage only. Continue remaining page-by-page visual and interaction checks.
- [ ] Complete signed-in member and admin UI checks for the catalog, OCR, regulation search, unmatched candidates, inquiries, user management, keyword management, registration review, and normalization settings.
- [ ] Finish the interaction parity review against the Streamlit UI; keep Streamlit as the production interface until this is complete.

The OCR dependency deployment is complete. Authenticated local OCR API inference and candidate persistence have since been exercised; Render OCR behavior and React UI flow remain unverified. The user has verified the report screen and downloaded its CSV. Keep Streamlit as the production UI until the remaining signed-in checks pass.

## Browser access recovery check (2026-11-05)

- The local React production build succeeds (`npm run build`).
- The deployed React preview HTML, API `/healthz`, and API `/openapi.json` all return HTTP 200. The live OpenAPI document reports version `1.1.0` and includes the OCR and period-report routes.
- Unauthenticated requests to the keyword catalog and period-report endpoints return HTTP 401.
- The agent's browser-control inventory still reports `Browsers: Error: The browser access host is unavailable` with no browser sessions, including after the user reported that their browser connection had recovered. Creating a fresh in-app tab fails with the same host error. The user completed the report review in their browser, but agent-controlled visual QA for other pages remains blocked.
- To resume agent-controlled visual/account QA, restore the browser-control host/session and confirm `cua.getState()` lists a browser session, then open the deployed preview and continue with signed-in OCR and member/admin workflows. Do not mark account-based checks complete based on HTTP availability alone.

## Report count reconciliation (2026-11-05)

- A read-only comparison confirmed that the CSV's period counts agree with visible event rows in the inclusive Korea Standard Time date range. The report period calculation and CSV agree with the live event log.
- `기간내_조회수` is counted from visible `kra_hits` in the selected date range. `키워드 조회 수(누적카운트)` is the separate `kra_keywords.hit_count` counter. The admin's **누적 조회수 초기화** sets that counter to zero while preserving event rows; **최근 7일 기록 리포트에서 제외** hides recent event rows from report queries without changing the counter.
- The differing values are consistent with the documented counter-reset behavior and do not by themselves indicate duplicated report hits. The event log remains the source for period reports. The application does not persist a reset audit record, so it cannot prove the exact reset request or time from database state alone.

Render OCR behavior, member/admin page workflows beyond the report, Excel display of the CSV, exhaustive analysis-result parity, and full interaction parity remain required before switching the production UI. Seven same-data comparison cases have since matched; see the latest parity section.

## QA continuation (2026-11-05)

### Environment and safety

- [x] Started from `main` at `030f7436fb7058d2c29bbca4a8c127914d2973da`, the recorded QA commit. The GitHub `main` ref also pointed at this commit; no pull or overwrite was performed. The local `origin/main` tracking ref is stale. Existing user changes in `frontend/.env.example` and the untracked `period_topN_report.csv` were preserved and excluded from this QA change.
- [x] This checkout is `D:\back-up\encore\keyword-risk-analyzer`; the requested `C:\encore\keyword-risk-analyzer` path does not exist in this session.
- [x] Inspected local target configuration without printing credentials: frontend Supabase auth and backend storage point at the production Supabase project; the frontend API base is local. Production writes were not used. OCR was exercised via TestClient with a local CSV backend and in-memory analysis repository. Automated tests ran with CSV storage and an unreachable local Supabase URL override.
- [x] Browser-control inventory still has no browser session and reports that the browser access host is unavailable. The open Chrome window could not be bound through the browser tool. This is a tooling limitation, not an application failure.

### OCR API (direct API, isolated; real inference)

- [x] Actual PaddleOCR 3.7.0 / PaddlePaddle 3.3.1 inference on a synthetic, non-personal Korean image extracted the expected text `안티에이징` exactly. Passing that extracted text to analysis matched B245. No persistent repository writes occurred.
- [x] Blank image returned an empty result without crashing. Unsupported PDF produced a per-file error while the request remained available. A simulated OCR initialization failure returned HTTP 503 with an explanation; a subsequent real inference retry succeeded.
- [ ] React upload controls, extracted text display, keyword analysis interaction, and retry messaging remain visually unverified because the browser tool session is unavailable.
- [x] Authenticated candidate persistence was verified through the local OCR save API using a synthetic candidate; the row was removed afterward. The local catalog is empty again; its revision is now 4 after successive local save/cleanup checks. Do not save OCR candidates in production for QA.
- [ ] React candidate review and save UI remain visually unverified because the browser tool session is unavailable.

### Feature parity and access checks

| Area | Evidence and result | Status |
|---|---|---|
| Script analysis and exact/partial/minimum-character matching | Existing service/API tests and matching implementation; automated suite passed | API/code verified; React/Streamlit screen comparison pending |
| Zero matches, filters, retry | Existing current-analysis tests cover behavior; React keeps analysis ID/input for retry and handles pending candidate-save retry | API/code verified; visual interaction pending |
| Automatic scrolling | No explicit `scrollIntoView`/scroll-to-result behavior found in either React or FIXED327/FIXED329 Streamlit source | No implementation difference identified; screen behavior pending |
| Report and CSV | User verified admin login, 10/30–11/05 Top 10, download; prior parsing and event-count reconciliation passed | User UI/API data verified; Excel display check below |
| OCR | Real isolated inference, blank input, unsupported file, initialization failure and retry tested | API verified; React UI pending |
| Candidate management, inquiries, admin keyword/user management | Existing API/UI tests and role guards reviewed; full Python suite passed | Automated/code verification; signed-in page/API workflow pending |

- [x] Admin-only API role checks are present for administrator endpoints; integration-token access is restricted to analysis/read paths. The automated test suite includes admin/member UI and API authorization tests. No production mutation, role change, delete, or reset was attempted.
- [ ] Prepared member/admin test credentials were not available. The app menus and authenticated API role behavior therefore remain unverified in a live session; no production account was used for speculative writes.
- [ ] React and Streamlit could not both be opened in the current browser-control session. Do not mark visual parity complete; keep Streamlit as production UI until remaining screen QA passes.

### Spreadsheet display

- [x] The report CSV parses as 10 data rows × 14 fields and reconciles with the event counts.
- [ ] Excel is not installed in the current environment, so its visual rendering and 14-column layout remain unverified.
- [ ] If Excel becomes available, import the report CSV with comma as the delimiter and verify all 14 columns and representative Korean cells.

### Report count semantics

- [x] Code and query definitions confirm `기간내_조회수` counts visible `kra_hits` event rows in the selected inclusive KST range. `누적카운트` reads the separate mutable `kra_keywords.hit_count` counter. A counter reset zeros that counter while preserving event rows; report-exclusion settings hide recent events from report queries without changing the counter. Thus 63 versus 22 is consistent with differing measurement windows/semantics. Database state has no reset audit record, so the exact reset time cannot be reconstructed. No counts or records were changed.

### Checks executed

- [x] `npm run build` — TypeScript and Vite production build passed.
- [x] Full Python suite with isolated environment overrides — 103 passed, 9 skipped, 187 subtests passed; one warning. Live reset tests were not enabled.
- [x] Real OCR API inference and error/retry checks — passed in isolated TestClient/in-memory setup as detailed above.

Remaining production-switch gates: Excel comma-delimited visual confirmation; browser-connected React member/admin interaction checks; OCR React UI; and direct React/Streamlit page comparison. Local server-side candidate persistence has been verified, but do not infer UI completion from that backend check.

## QA preparation after b41ee63 (2026-11-05)

This section supersedes the prior OCR/API-only status where newer evidence is listed. No screen checks are marked complete here.

### OCR fixture and direct API verification

- [x] Prepared `docs/qa/ocr_korean_sample.png`, a synthetic image with no personal information; expected text is `안티에이징`. Also prepared `docs/qa/ocr_blank_sample.png` for empty-result behavior. The rendered sample was visually inspected.
- [x] Confirmed `requirements-ocr.txt` pins NumPy 2.3.5, PaddlePaddle 3.3.1, and PaddleOCR 3.7.0. The local `.venv-ocr313` has those versions installed and the Korean PP-OCRv5 models cached. The deployed Render API previously reported the same Paddle versions and OCR dependency installation. A clean machine still needs to install `requirements-ocr.txt` in its supported Python 3.9–3.13 environment; first model use may download model files.
- [x] Ran actual `/api/v1/ocr/extract` via FastAPI TestClient with the prepared Korean image, blank image, and unsupported PDF. HTTP 200; the Korean recognized string matched the expected value exactly; blank count was 0; PDF returned a file-level error. Storage was overridden to local CSV, and this endpoint did not persist data.
- [x] Exercised `/api/v1/ocr/keywords` with an in-memory repository: a member save created a test row/code and counter `0`; duplicate candidate returned HTTP 422; stale revision returned HTTP 409. No database or disk repository was written.
- [x] Role smoke test through TestClient: unauthenticated admin-users GET returned 401, a member returned 403, and the integration token returned 403. Admin users API was not called with an admin bearer because that would require actual account data; admin list rendering remains unverified.
- [x] Authenticated local OCR API upload and candidate persistence succeeded; a synthetic candidate became visible in the filter API and was then removed. The temporary member session was globally signed out and the account deleted.
- [ ] Authenticated React OCR UI and follow-through analysis in the browser remain unverified.

### Next manual session materials

- [x] Added `docs/qa/SCREEN_QA_CHECKLIST.md` with the code-based React/Streamlit comparison, test-account and sandbox fixture requirements, and per-screen `화면 → 조작 → 기대 결과 → 확인할 증거` instructions. It includes a first OCR screen-review procedure and states which operations must remain read-only or run only in an isolated project.
- [ ] The checklist is a prepared procedure, not evidence that a user completed those screen checks. Browser/role-based items remain open until evidence is returned.

### Re-run checks

- [x] React `npm run build` — TypeScript and Vite build passed.
- [x] Full Python suite with CSV storage, unreachable local Supabase URL override, and live-reset flag removed — 103 passed, 9 skipped, 187 subtests passed, one Starlette/httpx deprecation warning.
- [x] Existing user changes `frontend/.env.example` and `period_topN_report.csv` were preserved and excluded from the QA changes. Global `git diff --check` reports the pre-existing extra blank line at EOF in `.env.example`; QA artifact diff is clean when staged alone.

Use `docs/qa/SCREEN_QA_CHECKLIST.md` for the first manual screen review. Production switching remains blocked by the explicitly unverified React/Streamlit visual and account workflows; no unrun checks are marked complete.

## Continued QA verification (2026-11-05)

- [x] Rechecked the connected browser control. Its Node runtime failed to start because a required path was unavailable; no app page, authenticated flow, or browser console was inspected in this run.
- [x] Current `main` React production build passes (`npm run build`). This branch's `frontend/package.json` has no `test` script, so `npm run test` is unavailable here.
- [x] Focused Python analysis and Streamlit approved-matching UI tests passed: 10 tests. Ran with `PYTHONPATH=tests` and a repository-local temporary directory to avoid the Windows temp cleanup permission failure.
- [x] The approved-matching UI test previously attempted unmatched-candidate persistence against its placeholder `example.supabase.co` URL. The test now mocks `SupabaseRepository.collect_unmatched_terms`; rerun passed without a network request.
- [ ] Browser-based React member/admin page checks, OCR upload/result/candidate flow, Excel 14-column display, and direct React/Streamlit visual comparison remain open. No production write was used.

## Local API recovery (2026-11-05)

- [x] Restored the isolated API launcher at `scripts/start_local_test_api.ps1` and created an ignored `.env.test.local` using only the running local Supabase configuration. The file is excluded through `.git/info/exclude`; its key was not printed or passed as a process argument.
- [x] Updated `app_config.py` so an explicitly selected `KRA_ENV_FILE` overrides inherited blank environment values. Updated `repository.py` to allow HTTP only for loopback when `SUPABASE_ALLOW_LOCAL_HTTP=1`.
- [x] Started the API from the isolated launcher. `/healthz` returned HTTP 200. React-origin CORS preflight returned HTTP 200. The unauthenticated filter request returned HTTP 401 with the expected CORS origin; a separate invalid-token request returned HTTP 401.
- [x] An authenticated, read-only local Supabase snapshot request succeeded; the local keyword catalog currently contains 0 rows.
- [x] A temporary local member account logged in and received HTTP 200 from `/api/v2/analysis-filters`; its session was globally signed out and the account deleted.
- [ ] Browser UI refresh, OCR interactions, and visual parity remain unverified because the browser access host is unavailable. Local Supabase contains zero keyword rows; do not copy production catalog data for this check.
## Local OCR inference (2026-11-05)

- [x] Ran PaddleOCR with cached `PP-OCRv5_mobile_det` and `korean_PP-OCRv5_mobile_rec` on `docs/qa/ocr_korean_sample.png`; it recognized the expected Korean sample label at confidence 0.9998558.
- [x] The same pipeline returned no text for `docs/qa/ocr_blank_sample.png`.
- [x] Authenticated OCR API upload and candidate-save persistence were verified against local Supabase; temporary test data was removed.
- [ ] React upload, OCR result rendering, candidate review UI, and browser follow-through remain unverified because the browser access host is unavailable. These local checks do not establish Render OCR behavior.
## Local integration follow-up (2026-11-05)

- [x] Both Vite listeners on `localhost:5173` and `127.0.0.1:5173` serve the local API base `http://127.0.0.1:8000`; this includes the `--mode test` process.
- [x] Focused Python API/authentication test modules passed: 47 tests, 8 skipped. Test-process Supabase configuration pointed to a closed loopback port so no test could contact production.
- [x] React production build passed (`npm run build`). `git diff --check` passed.
- [ ] A real signed-in browser request, filter rendering, and React/Streamlit visual parity remain unverified while the browser access host is unavailable. Local Supabase currently has zero keyword rows.

## Local role API smoke (2026-11-05)

- [x] A temporary local member received HTTP 403 from `/api/v1/admin/users`; a temporary local admin received HTTP 200. The returned user list was not printed.
- [x] Both temporary sessions were globally signed out and both local auth users were deleted.
- [ ] Member/admin React navigation, page-level access controls, and visual rendering remain unverified without the browser access host.
## OCR UI fix verification (2026-11-05)

- [x] `saveOCRKeywords` serializes only `term`, `category`, `risk`, `detail`, `evidence`, and `alternative`; `node frontend/scripts/check-ocr-save-payload.mjs` passed.
- [x] Local authenticated save accepted the whitelisted candidate and reflected it in the keyword ledger. A follow-up request with OCR-only fields returned 422, preserving server-side extra-field rejection. The synthetic row and temporary member were removed after global logout.
- [x] Replaced the administrator email-notification `??` literals with Korean UI copy.
- [x] Frontend build passed; focused OCR/API unit tests passed: 21 run, 6 skipped.
- [ ] Browser retest of OCR save and all three matching modes remains pending. A later same-data React/Streamlit comparison covered seven cases; see the latest parity section.
## Browser QA follow-up (2026-11-05)

- [x] User reports the admin inquiry email notification title, description, checkbox, and save button render in Korean.
- [x] User reports OCR recognized 15 text items and showed 13 deduplicated candidates from the supplied screenshot. Clearing all candidates disabled save; missing required classification blocked save with guidance; preview copied the selected text into analysis input.
- [x] After the OCR payload fix, one synthetic candidate (`피부`, code B001) saved successfully; the prior HTTP 422 did not recur. Its test classification was explicitly synthetic and not used for real advertising review.
- [x] User verified the saved test classification and review basis in keyword management. For input `피부`, exact and partial match each returned B001 once. Character-count matching for `피부관리` with minimum 2 characters returned `피부` once; minimum 3 returned zero. Highlighting and B001 detail expand/collapse worked. These are sample cases, not exhaustive combination coverage.
- [x] Report showed B001 period hits 3 and cumulative hits 3. The downloaded CSV had UTF-8 BOM, 6 columns, 5 data rows, preserved Korean/date strings, and count 1 per row at download time. The CSV snapshot need not equal current cumulative statistics.
- [x] User reports no browser console warnings or errors on the checked screens.
- [x] QA-only local data was removed: B001 keyword row, 3 hit rows, 3 analysis records and their linked candidate/observation records. Existing accounts and unrelated unmatched/analysis data were retained; no account roles changed. Final local DB check: keyword ledger 0 rows, B001 hits 0, target analysis records 0; catalog revision 6. React reload showed an empty ledger.
- [ ] At that point, same-data React/Streamlit result equivalence had not been verified. The later seven-case comparison below supersedes that status. Excel rendering and the 14-column spreadsheet layout remain unverified because Excel is unavailable. Earlier test/build results in this file were reported by VS Code Codex and were not rerun as part of the browser QA session.
## Patch applied to this Windows working copy (2026-11-05)

- [x] Applied `react_parity_fixes.patch` after `git apply --check` succeeded. Existing unrelated working-tree edits were preserved; no commit, push, or deployment was made.
- [x] Re-ran the five read-only empty-catalog API tests: all 5 passed.
- [x] Re-ran the three frontend catalog API tests: all 3 passed. `npm run build` passed.
- [x] `git diff --check` passed. The local Vite server on port 5173 returned the patched `src/App.tsx` module (HTTP 200), including the catalog UI and filtered export code.
- [ ] Visual/browser interaction validation is still pending: the connected browser tool reported that its browser access host is unavailable. The server/source response is not a visual UI check.
- [ ] At the time of this entry, no comparison data had been entered. A later same-data comparison is documented in the latest parity section; remaining tabs and interactions are follow-up work.
- [x] Restarted the local API from `scripts/start_local_test_api.ps1` after the `api.py` change. React, API, Streamlit, local Auth, and the read-only local ledger request returned HTTP 200; the ledger was then empty.
## Unmatched parity follow-up applied locally (2026-11-05)

- [x] Applied `react_unmatched_parity_followup.patch` to the current Windows working copy after its applicability check passed. Prior uncommitted changes and unrelated user files were preserved.
- [x] Added search-wide requestable-candidate selection across result pages, separate clear-selection action, manual normalization-workspace row insertion/removal, and replacement confirmation before generating or loading over an existing workspace.
- [x] In-flight select-all is invalidated on page, account, search, sort, or result-page changes. It rejects count changes, duplicate rows, and incomplete result pages; the paged endpoint does not offer a transactional snapshot, so same-count concurrent reorderings cannot be fully excluded.
- [x] Frontend tests: 9 passed; production build passed; `git diff --check` passed. These tests use mocks and do not write to Supabase.
- [x] User reports live React browser verification of the unmatched UI: selected all 144 requestable candidates, moved to page 2 with selection retained, cleared selection, added a blank row, inserted rows above/below while preserving existing input, confirmed insert controls disable with multiple rows selected, and removed all workspace rows to return to 0.
- [x] The browser exercise used only unsaved UI state. The user reports no draft save, registration request, approval/rejection, permanent candidate deletion, or catalog write. The temporary UI rows were removed.
- [x] Read-only local `kra_snapshot()` after the exercise returned HTTP 200, revision 8, and 0 catalog rows.
- [ ] Saved draft save/reload, replacement confirmation, general-member behavior, search/sort and mixed processed-candidate cases, concurrent candidate changes, and more than 1,000 candidates remain unverified.
- [ ] Drag-fill, recommendation table column tools/CSV/fullscreen, and the remaining tab-parity review are still open.
## Same-data React/Streamlit comparison (2026-11-05)

- [x] User reports both local apps were signed in to the local admin account and used the same local Supabase catalog. The test catalog began empty at revision 6; two synthetic keywords were added for comparison. The test basis was explicitly synthetic and not for real advertising review.
- [x] Seven reported cases matched between React and Streamlit:
  - Exact match, `올인원 안티에이징`: 2 matches (`올인원` → B002, `안티에이징` → B001), with matching highlights and linked codes.
  - Partial match, `안티`: 0 matches in both; both showed the empty-result state.
  - Partial match, `올인원 안티에이징`: 2 matches in both, with matching detected terms, highlights, and linked codes.
  - Character-count match, `인원안티`, minimum 2: 2 matches (`인원` → B002, `안티` → B001), with matching highlights.
  - Character-count match, `인원안티`, minimum 3: 0 matches in both; both showed the empty-result state.
  - Exact match, `안티 에이징`, whitespace matching enabled: 1 match (`안티 에이징` → B001), with matching highlight.
  - Exact match, `안티 에이징`, whitespace matching disabled: 0 matches in both; both showed the empty-result state.
- [x] User reports matching result fields for both keywords: code, keyword, category, synthetic risk grade, alternative, and review criteria. B001 details also showed matching registered expressions, input text, classification, and review criteria.
- [x] Test cleanup was reported complete: B001/B002 rows, 10 analysis records, 18 hit records, 16 collection events, and 8 unmatched observations were removed; other accounts and existing records were preserved, with no role changes. The local `kra_snapshot()` was independently checked read-only after cleanup: HTTP 200, revision 8, 0 rows.
- [ ] Coverage is limited to these seven examples and does not establish parity across all inputs, filters, normalization settings, nested-match combinations, or screens. One React option-change run showed no result area before the user checked state and retried; the retry showed the expected zero-result state, but the timing cause is unknown.
- [ ] Excel visual rendering and the 14-column layout remain unverified. Other tab interactions and recommendation-table drag-fill, column tools, CSV, and fullscreen parity remain open.
## Recommendation draft round-trip precheck (2026-11-05)

- [x] Historical read-only precheck before the draft round-trip test found 0 saved workspaces. The later test saved one intentionally empty workspace; see the latest round-trip section below.
- [ ] At the time of this precheck, browser round-trip verification had not yet run. The subsequent user-reported screen test is documented below; overwrite confirmation with unsaved edits remains unverified.
## Recommendation draft persistence browser QA (2026-11-05)

- [x] User reports saving a temporary two-row draft and verifying page re-entry restored both rows, including exact content, embedded newline, order A→B, and selected state A=false/B=true. The saved test values were `QA_DRAFT_A_20261105` and `QA_DRAFT_B_20261105`; no unrelated workspace rows were present.
- [x] User reports loading the saved draft from an empty workspace and confirming the same two rows, multiline text, ordering, and selection state were restored.
- [x] User removed only the two QA rows from the unsaved workspace and saved the empty workspace. After refresh and re-entry, the UI showed 0 rows and 0 selected. This is an empty saved payload, not deletion of the draft record.
- [x] User reports the 144 accumulated unmatched candidates were preserved; no candidate deletion, registration request, catalog write, role change, or approval/rejection was performed.
- [x] Independent read-only local DB checks: snapshot HTTP 200, revision 8, 0 keywords; unmatched candidate page HTTP 200, total 144; draft table HTTP 200, 1 record with empty recommendations and empty selection.
- [ ] Confirming the overwrite dialog while the current workspace contains unsaved edits remains unverified. Do not infer it from loading the saved draft over an empty screen. Excel display and unrelated parity gaps remain open.
## Remaining parity checks review (2026-11-05)

- [ ] The overwrite-confirmation path was not exercised: the browser access host remains unavailable. No dialog was accepted and no saved work was changed in this check.
- [ ] Windows inspection found no Excel command, Excel App Paths entry, Microsoft Office/365 or spreadsheet application in the uninstall registry, and no LibreOffice command. Excel's actual CSV rendering and 14-column layout remain unverified; no application was installed.
- [x] Code-level option mapping reviewed: React sends mode, partial minimum length, four normalization flags, and category/risk prefilters; Streamlit builds the corresponding `MatchingConfig` and category/risk filters, with both paths calling the shared matching implementation.
- [ ] This source review does not verify additional screen, filter, or option combinations. Existing same-data browser evidence remains limited to the seven cases above; no new test data or DB writes were made.

## Migration progress tracking (2026-11-06)

- [x] Reconciled the current progress against dated browser evidence and the design baseline in `docs/qa/SCREEN_QA_CHECKLIST.md`.
- [x] The current manual screen checklist has 15 workflow groups: 3 have no browser evidence, 12 are partial/sample-only, and none completes every criterion in its group. This count is a scope tracker, not a readiness percentage.
- [x] Clarified that the historical “58-item parity review” reference has no canonical 58-row checklist in this repository; it is not used as a progress metric.
- [x] The unsaved-edit overwrite confirmation was later verified by the user in the browser; see the 2026-11-06 follow-up below. Excel’s real 14-column rendering remains a high-priority blocker, with broader member/admin and screen parity still open.

### Local verification (2026-11-06)

- [x] Read-only HTTP checks returned 200 for React (`127.0.0.1:5173/`), API health (`127.0.0.1:8000/healthz`), Streamlit (`127.0.0.1:8501/`), and the local Supabase REST root (`127.0.0.1:54321/rest/v1/`). These checks establish service reachability only; no authenticated DB query or write was made.
- [x] Frontend automated tests passed: 9/9; OCR save payload contract check passed; `npm run build` passed.
- [x] User-provided screenshot shows the local React page at `127.0.0.1:5173` on the analysis screen with Korean labels and match options; the user reports test-account login completed.
- [ ] The screenshot does not show account identity/role or session persistence, and does not verify further page interactions or saved-draft replacement.
- [ ] Computer Use still reports the browser access host unavailable, so no browser-controlled interaction was performed.
- [x] Backend tests passed in the project `.venv` (Python 3.12.14): 117 tests run, 9 skipped, 0 failures. `KRA_TEST_LIVE_RESET=0`; Supabase environment variables were removed for the test process. The explicitly live reset and legacy UI assertions were not verified.
- [ ] SQL integration scripts and authenticated local DB behavior were not run in this test pass.

### Draft overwrite follow-up (2026-11-06)

- [x] Source review: loading a saved recommendation draft prompts whenever the visible workspace has at least one row. On confirmation it reloads the saved payload and replaces the visible rows and selected IDs. It does not track whether rows are dirty, so the warning also appears for an unchanged non-empty workspace.
- [x] Fixed silent replacement on SPA page re-entry: an account's saved draft is now auto-load attempted once; returning to the page preserves the current workspace. A different account clears the previous account's in-memory rows before loading its own draft. Explicit saved-draft reload remains available through the confirmation button.
- [x] Added state tests for first load, same-account page revisit, explicit refresh, account change, and signed-out state.
- [x] At that initial recheck, the browser access host was unavailable; the confirmation had not been clicked, and no draft was written or replaced. The later user-reported browser result is recorded below.

### User-reported draft overwrite confirmation (2026-11-06)

- [x] After adding an unsaved blank row, the user clicked “저장된 작업본 불러오기”, accepted the overwrite confirmation, and returned to a workspace showing 0 rows and 0 selected. This verifies the confirmation-and-replacement path for the saved empty draft.
- [x] The user-provided screenshots show the transient 1-row/0-selected state and the final 0-row/0-selected state. The user reports accepting the confirmation between them.
- [x] This used the previously saved empty draft and changed only unsaved UI state; no save, registration request, approval/rejection, candidate deletion, or catalog write was reported.
- [ ] The agent could not independently control the browser because its access host remained unavailable. Excel’s actual 14-column rendering and broader interaction parity remain open.

### Streamlit source baseline check (2026-11-06)

- [x] `streamlit_cloud/app.py` selects the highest numbered `keyword_app2_fixed###.py`; the latest source is FIXED329. Comparing FIXED327 with FIXED329 found only the version label/docstring changed.
- [x] Source navigation review found React counterparts for the Streamlit top-level functions. React exposes registration review and normalization as admin subpages; Streamlit places those flows within its tabs.
- [ ] This source comparison does not verify visual or interactive parity. The browser host remains unavailable, so no new screen comparison was performed.

### Report date-range follow-up (2026-11-06)

- [x] Read-only environment check found no Excel/LibreOffice executable or installed Office/spreadsheet suite. CSV screen rendering and the 14-column visual layout remain unverified.
- [x] Added isolated API tests for required date pairs, reversed date rejection, forwarding an inclusive start/end range and limit to the repository, catalog snapshot enrichment, and rolling-days fallback. The report API returns the supplied catalog fields and keyword revision in the expected shape. Tests use a mock repository and do not access Supabase.
- [x] Added a React API client test confirming selected start date, end date, and row limit are sent to `/api/v1/reports/top-keywords`.
- [x] Static SQL review confirms range endpoints are inclusive in Korea Standard Time: timestamps are filtered from the start date through, but not including, midnight after the selected end date.
- [x] Verification: `tests/test_empty_catalog_api.py` — 9 passed; frontend `npm test` — 15 passed. No UI or live DB report request was made.
- [ ] Excel/LibreOffice display, date-range screen interaction, downloaded report CSV visual layout, and remaining member/admin and cross-page parity checks remain open. Browser access host is unavailable.

### OCR regression follow-up (2026-11-06)

- [x] Reviewed React OCR upload limits and result states, per-file error rendering, selected-candidate required fields, analysis handoff, and explicit save-payload field mapping. No new production-code defect was identified in this review.
- [x] Existing isolated OCR suite passed: `python -m unittest discover -s tests -p "test_ocr_*.py"` — 8 passed. This covers mocked OCR/Streamlit preview behavior, text-box geometry in headless Chrome, and existing OCR collection/import behavior; it is not a new PaddleOCR inference or authenticated React browser run.
- [x] `node scripts/check-ocr-save-payload.mjs` — PASS; only the six server-accepted candidate fields are serialized.
- [x] No database writes, live API requests, or OCR model inference were performed in this follow-up. Test-generated temporary files were removed.
- [ ] React OCR upload/result interaction, blank-image and recovery states, and signed-in candidate persistence remain UI checks. The browser access host is unavailable.
