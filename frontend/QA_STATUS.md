# React transition QA status

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
- [ ] Open the downloaded CSV in a spreadsheet application and visually check the displayed columns and values.
- [ ] Visually compare the updated React shell and each page against Streamlit; the user's report review did not cover the other pages.
- [ ] Complete signed-in member and admin UI checks for the catalog, OCR, regulation search, unmatched candidates, inquiries, user management, keyword management, registration review, and normalization settings.
- [ ] Finish the interaction parity review against the Streamlit UI; keep Streamlit as the production interface until this is complete.

The OCR dependency deployment is complete, but OCR inference has not yet been exercised with an authenticated user session. The user has now verified the report screen and downloaded its CSV. Remaining screens have not been marked complete from backend data alone. The local Python suite passes. Keep Streamlit as the production UI until the remaining signed-in checks pass.

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

OCR inference, member/admin page workflows beyond the report, spreadsheet-application display of the CSV, and full interaction parity remain required before switching the production UI.

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
- [ ] Candidate persistence was not tested: the configured project is production, and there is no isolated persistent test account/database available in this session. Do not save OCR candidates in production for QA.

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

- [x] Microsoft Excel is installed and opened the supplied CSV. Excel rendered Korean headers and cell text correctly. In the current Excel import configuration, the entire CSV record appeared in one cell rather than 14 columns, so column/cell layout is not yet verified. The CSV itself still parses as 10 data rows × 14 fields and reconciles with the event counts.
- [ ] Re-open/import through Excel's Text Import Wizard with comma as the delimiter, then verify all 14 columns and representative Korean cells. This result is an Excel import configuration/display check; it does not establish a malformed CSV or app defect.

### Report count semantics

- [x] Code and query definitions confirm `기간내_조회수` counts visible `kra_hits` event rows in the selected inclusive KST range. `누적카운트` reads the separate mutable `kra_keywords.hit_count` counter. A counter reset zeros that counter while preserving event rows; report-exclusion settings hide recent events from report queries without changing the counter. Thus 63 versus 22 is consistent with differing measurement windows/semantics. Database state has no reset audit record, so the exact reset time cannot be reconstructed. No counts or records were changed.

### Checks executed

- [x] `npm run build` — TypeScript and Vite production build passed.
- [x] Full Python suite with isolated environment overrides — 103 passed, 9 skipped, 187 subtests passed; one warning. Live reset tests were not enabled.
- [x] Real OCR API inference and error/retry checks — passed in isolated TestClient/in-memory setup as detailed above.

Remaining production-switch gates: Excel comma-delimited visual confirmation; browser-connected React member/admin interaction checks; OCR React UI and isolated persistent candidate-save check; and direct React/Streamlit page comparison. Do not infer these from backend-only verification.
