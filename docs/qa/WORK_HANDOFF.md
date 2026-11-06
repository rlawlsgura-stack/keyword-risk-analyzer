# React migration QA handoff

Updated: 2026-11-07

Use this short status note when moving the work between PCs. It is a continuation aid, not a
full activity transcript. Record dated verification details and evidence in
[`frontend/QA_STATUS.md`](../../frontend/QA_STATUS.md); use the
[`screen QA checklist`](./SCREEN_QA_CHECKLIST.md) for the page-by-page scope.

## Current state

- Branch: `main`. The previously synced baseline was `cab245a`; this session adds Streamlit
  AppTest evidence and QA notes. Before switching PCs, pull the latest `main` and check its status.
- React preview package version was advanced from `0.1.1` to `0.1.2` for this QA/documentation
  update. The Streamlit baseline remains FIXED329; this is not a Streamlit code release.
- The React transition remains in QA. Streamlit remains the production UI until the remaining
  signed-in member/admin workflows and interaction parity are complete.
- Latest user-reported UI check: an unsaved blank recommendation row was added, the user accepted
  the **저장된 작업본 불러오기** overwrite confirmation, and the workbench returned to 0 rows / 0
  selected by loading the previously saved empty draft. The user did not report saving during this
  check or submitting a registration request, approving/rejecting, deleting candidates, or changing
  the catalog. This confirms only that overwrite scenario.
- The agent's connected browser host was unavailable at the latest check. Screenshots and the
  user's report supplied the evidence; the agent did not independently control the browser.
- Excel was available for the 2026-11-06 follow-up below. Opening the existing workspace CSV
  confirmed UTF-8 Korean text and 14 fields; the report-screen download path and full visual layout
  still need confirmation from a fresh React export.

## Environment-specific QA and cross-PC continuity (2026-11-06)

- The React page was opened locally at `http://127.0.0.1:5173/` and the API health endpoint at
  `http://127.0.0.1:8000/healthz` returned 200. The API process reported
  `STORAGE_BACKEND=supabase`; its Supabase host was confirmed in the dashboard, whose branch badge
  read `main / PRODUCTION`. Treat this PC's current API target as production, not a test database.
- The user authorized production-backed text analysis, OCR, and candidate saves, and explicitly
  prohibited deleting the full dataset. This authorization does not include unrelated admin
  changes. Do not delete data during this QA, including cleanup of individual test records, unless
  the user separately asks for that cleanup.
- No new analysis, OCR upload, candidate save, or other database write was performed by the agent
  in this handoff session. The browser automation host could not determine the active Chrome URL
  and stopped before any UI action. An analysis result was visible in the user's screenshot, but
  its execution time and whether it wrote to the database were not established here.
- Excel review of the existing `period_topN_report.csv` is recorded in `frontend/QA_STATUS.md`.
  It is a local file inspection, not evidence that the React report download was exercised.
- In the next continuation attempt, local React and API health returned 200. Windows Computer Use
  still could not establish the current Chrome URL, so no React report request/download or live QA
  action was made. Frontend tests passed 15/15 and the production build passed; these are mocked
  client-contract/build checks, not live Supabase or browser evidence.
- A further report-export retry again found the local services healthy but no attachable browser
  session. The report API requires the signed-in bearer token, so no unauthenticated API workaround
  was attempted. The next step needs browser control restored or a CSV downloaded by the user.
- The report CSV row builder is now covered in isolation: 17 frontend tests pass and the production
  build passes, including 14-column order, Korean text, dates, counts, CSV escaping, and formula
  safety. This still does not verify a live browser download or Excel rendering of that download.
- The latest three-track attempt rechecked React/API as healthy but found local Supabase and
  Streamlit unavailable and had no attached second-PC test environment. Mock/local suites passed:
  41 analysis/member API tests, 8 OCR tests, and 19 Streamlit AppTests. PaddleOCR is not installed in
  this `.venv`; no live model inference or database request/write occurred. See the latest
  `frontend/QA_STATUS.md` entry for exact scope. The three live/UI QA items remain open.
- Read-only Supabase project discovery returned only the known production project and no
  development branches. A distinct hosted test project/branch was not available; none was created.
- A second PC may use a separate isolated test Supabase. Record it as a separate environment and
  never imply its data or results are shared with this production project. Do not copy `.env`,
  credentials, or database contents between PCs.
- At the start of each PC session, record the date, PC/environment label, frontend/API origins,
  `STORAGE_BACKEND`, and database classification (`PRODUCTION`, `TEST`, or `LOCAL`) without
  recording keys. Keep QA results and any observed database effects under that environment label.
  Recheck the target after changing terminals, environment files, or machines.
- To hand work off, commit and push only the intended tracked code/docs, then on the receiving PC
  pull `main`, inspect `git status --short --branch`, and read this handoff plus the latest dated
  `frontend/QA_STATUS.md` entry. Local credentials and DB state remain machine-specific.

## Next work, in order

1. In the React report screen, export a fresh CSV and inspect it in Excel. Confirm all 14 fields,
   Korean text, dates, and counts. The existing workspace CSV was readable after selecting UTF-8
   and comma in Excel's import wizard, but that does not verify the React download path.
2. Complete the explicitly authorized React live QA on this PC against the local test stack: run
   text analysis; check OCR with a non-sensitive test image; and save only the intended test
   candidate. Before acting, reconfirm the API target and record it as LOCAL. Do not delete records
   or use unrelated admin actions. The OCR regression suite passed 8/8 and the save-payload
   contract passed, but neither proves React screen behavior or live model inference.
3. Continue the checklist's remaining member/admin UI checks in a confirmed isolated test environment:
   OCR upload/results and error recovery; keyword inquiries; user and keyword management; unmatched
   candidate search/sort; registration request review; normalization settings.
4. Compare the remaining React and Streamlit screen interactions using the same isolated catalog
   and record each observed case. Existing parity evidence covers seven examples only.
5. Before any further live QA action, verify and record the active environment on that PC. On the
   current runtime, use the local Supabase test project for test analysis, OCR, candidate saves, and
   member/admin screens. Do not delete data or change unrelated catalog, user, role, Supabase, or
   Render settings. Keep the earlier production QA authorization separate from this local test data.

The 2026-11-06 report date-range follow-up added isolated tests: backend 9/9 and frontend 15/15.
These checks cover API parameter and response behavior only; no live database, report screen, or
spreadsheet application was used.

The 2026-11-06 OCR follow-up passed the 8-test Python OCR suite and the React OCR save-payload
contract check. The suite uses mocked OCR for extraction/Streamlit tests and headless Chrome for
overlay geometry; the React OCR UI and live model inference were not exercised.

The 2026-11-06 member/admin API follow-up passed 41 tests across analysis, empty-catalog access,
keyword inquiries, and unmatched persistence. These checks use mocks/local test clients, with
external Supabase credentials removed; they do not replace signed-in React screen or DB-persistence
verification.

The 2026-11-06 Streamlit role/unmatched AppTest follow-up passed 19 tests. One approved-matching UI
test uses FIXED329; shared-unmatched tests use older numbered snapshots and mocked repository calls.
This is not evidence for the corresponding React screens or all current Streamlit workflows.

## Environment notes

- Known local addresses: React `http://127.0.0.1:5173/`, API `http://127.0.0.1:8000/`, Streamlit
  `http://127.0.0.1:8501/`, local Supabase `http://127.0.0.1:54321/`. These were reachable in a
  prior read-only check; verify again on the PC being used.
- Never copy `.env`, `.env.test.local`, Supabase secrets, browser credentials, or
  `supabase/.temp/` into a handoff or commit.
- Start each session by reading `AGENTS.md`, checking `git status --short --branch`, and reviewing
  the intended diff. Preserve untracked files; do not blanket-stage the workspace.
- To continue on another PC, sync the intended tracked documentation/code changes through the
  repository. A local uncommitted handoff does not appear on another checkout automatically.

## Local Supabase test environment (2026-11-06)

- This PC now runs the React preview and API against the same local Supabase stack. The frontend
  module reports Supabase Auth at `http://127.0.0.1:54321` and API at `http://127.0.0.1:8000`;
  the running API process has `STORAGE_BACKEND=supabase` and `SUPABASE_URL` on loopback port 54321.
  `/healthz`, local Auth health, local test-admin login, and authenticated `/readyz` returned 200.
- The local DB was initialized from the tracked `supabase/schema.sql` migration and contains only
  two synthetic `LOCAL` keyword rows. Local Auth contains one generated admin account
  (`kra-admin@example.test`). No production users, auth records, or database rows were copied.
  Its generated password is stored only in the ignored `.local-test-credentials.txt` file.
- To recreate on another Windows PC: install/start Docker Desktop, run `npm ci` in `frontend`, then
  run `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/start_local_test_supabase.ps1`.
  In separate terminals, run `scripts/start_local_test_api.ps1` and
  `scripts/start_local_test_frontend.ps1` with the same PowerShell options. The Supabase CLI is
  pinned as a frontend dev dependency; the stack and test account are local to each PC.
- The local stack uses Supabase ports 54321–54324, API port 8000, and React port 5173. The setup
  script requires Windows Firewall enabled with inbound traffic blocked on all profiles. Docker
  publishes Supabase ports through wildcard bindings, so do not add inbound allow rules; use only
  the loopback URLs. No firewall settings were changed during setup.
- `.env.test.local`, `frontend/.env.test.local`, local credentials, and Supabase `.temp` state are
  ignored. The normal `.env` files still contain this PC's prior settings; always launch through
  the test scripts so local values override them. No remote Supabase project was linked or written.

## Working-copy caution at this update

The user-data and patch files already present as untracked at the start of this update were left
untouched: `keyword_filtered.csv`, `unmatched_candidates.csv`, `ocr_ui_qa_fixes.patch`,
`react_parity_fixes.patch`, `react_unmatched_parity_followup.patch`, and `supabase/.temp/`.
Inspect each independently before deciding whether it belongs in version control; never add the
temporary Supabase directory or secret material.

## Local QA continuation (2026-11-07)

- Current local QA environment: React `127.0.0.1:5173`, API `127.0.0.1:8000`, local Supabase `127.0.0.1:54321`. Keep this distinct from the previously documented production-backed PC session.
- Authenticated API-level local QA completed: recorded analysis matched synthetic `LOCAL001`; test-image OCR extracted `안티에이징`; one intended OCR candidate was saved as `LOCAL003`. The local DB has three synthetic `LOCAL%` keywords. No records were deleted, and no production DB was used for these operations.
- Local seed now defines 12 report fields. React report CSV serialization had corrupted Korean literals; those were repaired and the frontend suite passes 17/17 with the production build passing.
- Windows UI automation host is unavailable, so no fresh React report download, Excel inspection, member/admin browser QA, or React-Streamlit interaction comparison was possible. Keep these tasks open; see the dated `frontend/QA_STATUS.md` entry.
- Preserve the local test records; do not clean them up by deletion. The local credential file and environment files remain machine-specific and must not be committed.
