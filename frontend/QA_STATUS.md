# React transition QA status

## Completed

- [x] React production build (`npm run build`) succeeds.
- [x] Render React and API services are live; API health, CORS, and the React API paths were checked against the deployed OpenAPI document.
- [x] Password recovery email and reset link completed successfully against the live Supabase project.
- [x] Signed-in text analysis matched the sample terms `필러` (B118) and `안티에이징` (B245), recorded the run, and showed each keyword's details.
- [x] The live seven-day Top 10 database function included B245 at rank 2 with 47 hits and B118 at rank 3 with 43 hits when checked on 2026-11-02. Counts change as new analyses are recorded.
- [x] Admin API role checks were reviewed in the API implementation.
- [x] Confirmed production data is available for the catalog, unmatched-candidate review, and inquiry screens: 1,431 keywords, 571 candidates (564 pending, 7 ignored), and 3 inquiry threads with 6 messages on 2026-11-03.

## Remaining before switching the production UI

- [ ] Apply the updated Render Blueprint to the existing API service. The repository now includes OCR dependencies in that service's build, but Render still reports the previous build command (`pip install -r requirements.lock.txt`); OCR is not confirmed live until the Blueprint is synced and a deployment completes.
- [ ] Visually verify that the React report page displays the recorded terms and that its CSV download opens correctly.
- [ ] Complete signed-in member and admin UI checks for the catalog, OCR, regulation search, unmatched candidates, inquiries, user management, keyword management, registration review, and normalization settings.
- [ ] Finish the interaction parity review against the Streamlit UI; keep Streamlit as the production interface until this is complete.

The report UI and remaining screens have not been marked complete from backend data alone. During the latest review, the computer-use tool returned `browser access host is unavailable`, so interactive browser checks could not be performed.
