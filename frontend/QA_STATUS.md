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

- [ ] Visually verify that the React report page displays the recorded terms and that its CSV download opens correctly.
- [ ] Visually compare the updated React shell and each page against Streamlit; the browser control host is unavailable, so this layout change is build-checked but not visually accepted yet.
- [ ] Complete signed-in member and admin UI checks for the catalog, OCR, regulation search, unmatched candidates, inquiries, user management, keyword management, registration review, and normalization settings.
- [ ] Finish the interaction parity review against the Streamlit UI; keep Streamlit as the production interface until this is complete.

The OCR dependency deployment is complete, but OCR inference has not yet been exercised with an authenticated user session. The report range API and database function are deployed; the report UI interaction and CSV still need signed-in visual verification. Remaining screens have not been marked complete from backend data alone. During the latest review, the computer-use tool returned `browser access host is unavailable`, so interactive browser checks could not be performed. The local Python suite passes; restore browser access to resume the account-based screen checks. Do not switch the production UI before they pass.

## Browser access recovery check (2026-11-05)

- The local React production build succeeds (`npm run build`).
- The deployed React preview HTML, API `/healthz`, and API `/openapi.json` all return HTTP 200. The live OpenAPI document reports version `1.1.0` and includes the OCR and period-report routes.
- Unauthenticated requests to the keyword catalog and period-report endpoints return HTTP 401.
- The browser-control inventory currently reports `Browsers: Error: The browser access host is unavailable` with no browser sessions. Creating a fresh in-app browser tab fails with the same host error. This isolates the current blocker to the browser-control service; the public preview and API are reachable from the repository host.
- To resume visual/account QA, restore the browser-control host/session, confirm `cua.getState()` lists a browser session, open the deployed preview in a fresh tab, then continue with the signed-in report/CSV check. If the host remains unavailable, use a separately approved browser automation environment with the project test account; do not mark account-based checks complete based on HTTP availability alone.

The report screen/CSV, OCR inference, member/admin page workflows, and full interaction parity remain unverified and are still required before switching the production UI.
