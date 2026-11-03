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

## Remaining before switching the production UI

- [ ] Visually verify that the React report page displays the recorded terms and that its CSV download opens correctly.
- [ ] Complete signed-in member and admin UI checks for the catalog, OCR, regulation search, unmatched candidates, inquiries, user management, keyword management, registration review, and normalization settings.
- [ ] Finish the interaction parity review against the Streamlit UI; keep Streamlit as the production interface until this is complete.
- [ ] Deploy and verify the v1/v2 replay-shape fix on the React preview API after the current changes are pushed.

The OCR dependency deployment is complete, but OCR inference has not yet been exercised with an authenticated user session. The report range API and database function are deployed; the report UI interaction and CSV still need signed-in visual verification. Remaining screens have not been marked complete from backend data alone. During the latest review, the computer-use tool returned `browser access host is unavailable`, so interactive browser checks could not be performed. The local Python suite passes; restore browser access to resume the account-based screen checks. Do not switch the production UI before they pass.
