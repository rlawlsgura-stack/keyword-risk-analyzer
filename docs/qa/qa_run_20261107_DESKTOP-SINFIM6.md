# QA run — 2026-11-07 — DESKTOP-SINFIM6

## Run identity

- Korea Standard Time: 2026-11-07 11:01 (run window; see tool/test timestamps in local console).
- PC label: `DESKTOP-SINFIM6`.
- Repository root observed: `C:/encore/keyword-risk-analyzer`.
- Remote: `https://github.com/rlawlsgura-stack/keyword-risk-analyzer.git`.
- Branch / starting commit: `main` / `7f31159177a10b8f73ffb6db084c86d8c7cf8310`.
- Starting working tree: clean and aligned with `origin/main`. No reset, checkout, stash, or overwrite was used.
- Changes from this run are uncommitted and unpushed.

## Environment classification

- **PASS — isolated local test stack.** The live Vite module reported `MODE=test`, Auth at
  `127.0.0.1:54321`, and API base `127.0.0.1:8000`. The frontend values matched the local Supabase
  CLI `status` output. The API launcher validated `STORAGE_BACKEND=supabase`, a loopback HTTP
  Supabase URL, `SUPABASE_ALLOW_LOCAL_HTTP=1`, and a local-only service key before starting.
- Docker showed the repository's `supabase_*_keyword-risk-analyzer` containers. The authenticated
  local test admin reached API `/readyz`; front, API health, and Supabase Auth returned HTTP 200.
- No production database or Render write was made. Environment and credential values were not
  written here. The local credentials remain in ignored files on this PC only.
- At the first read, this active local database contained 0 catalog rows at revision 14 and 144
  unmatched terms. This differs from the earlier 2026-11-07 handoff that described three `LOCAL%`
  rows. This run verified and used the active CLI/Docker stack; the older count must not be assumed
  for this checkout.

## User-supplied browser handoff

- **USER-REPORTED / current execution UNVERIFIED.** The message's observations are preserved in
  `docs/qa/KRA_QA_HANDOFF_20261107.txt`. The original attachment itself was not available in the
  checkout or the checked Downloads/Desktop locations. Its PC, commit, and target environment were
  not supplied, so those observations are not marked as current-code passes.
- Computer Use could not capture the Chrome window because it could not determine the current URL
  with sufficient confidence. No UI click, sign-in, download, or screenshot was performed in this
  run.

## Law search configuration

- `legislation_source.py::_api_key()` reads `LEGISLATION_API_KEY` from the API process environment
  and sends it as Law.go.kr's `OC` parameter. `app_config.configure()` loads `KRA_ENV_FILE` when set;
  the local API launcher sets it to the ignored `.env.test.local`. Without it, the default is the
  repository `.env`.
- **BLOCKED.** Neither `.env` nor `.env.test.local` had a non-empty `LEGISLATION_API_KEY`. No key
  was found in the frontend configuration, and no production key was copied or exposed.
- Official instructions: sign in at [Law Open Data](https://open.law.go.kr/LSO/usrJoin.do), request
  the needed law/search API access and supply the application name, purpose, domain/IP and data
  categories; wait for approval, then use the approved/user-defined OC value. The guide says review
  generally takes 1–2 days: [usage procedure](https://open.law.go.kr/LSO/information/guide.do).
  Store the test key only as `LEGISLATION_API_KEY` in the local API environment, then restart the
  test API. Do not put it in Vite variables or Git.

## OCR and local catalog

- **PASS — current runtime.** API process was launched by `scripts/start_local_test_api.ps1` using
  `.venv-ocr313`; that environment is Python 3.13.15, Paddle 3.3.1, PaddleOCR 3.7.0, PaddleX 3.7.2.
- **PASS — inference.** Authenticated POST `/api/v1/ocr/extract` with the non-personal fixture
  `docs/qa/ocr_korean_sample.png` returned HTTP 200, one line and one candidate, exactly
  `안티에이징`, confidence `0.9998558163642883`. No package/model initialization error occurred.
- **PASS — save and re-query.** The active test catalog was empty before the operation. The extracted
  candidate was saved through `/api/v1/ocr/keywords` with the unique local category
  `LOCAL QA OCR 20261107`; it received code `L001`. Re-query returned the same term/category at
  revision 15 (from revision 14). The row is intentionally retained as local QA data; no cleanup or
  deletion was performed.
- A single exact analysis was recorded to create report data for the CSV check. It matched only
  `L001`; the report API returned one row with period count 1. This local analysis record is also
  retained. Existing unmatched terms were read as 144; no unmatched deletion or registration was
  performed.

## Matching API checks

Authenticated requests used `/api/v1/analyses` with `record=false`, so these checks did not add
analysis history or unmatched rows. All returned HTTP 200.

| Case | Input / options | Actual result | Status |
|---|---|---|---|
| Exact | `안티에이징`, exact | 1 match, code `L001` | PASS |
| Partial | Korean sentence containing `안티에이징`, minimum fragment 2 | 10 spans, unique code `L001` | PASS for match; PARTIAL for expected span cardinality |
| Similar | `안티에이징`, similar | 1 match, code `L001` | PASS |
| Category + risk filter | Exact input and the QA row's category/risk | 1 match | PASS |
| Wrong risk filter | Same category, non-matching risk | 0 matches | PASS |
| No-result input | `QA_NOT_FOUND_20261107`, exact | 0 matches | PASS |

## Admin/read-only API checks

- **PASS:** admin users endpoint returned role counts only: two admins and one member. No email or
  user identifier was recorded. A member account exists, but this run had no confirmed member login
  credential/session; member UI/API denial remains UNVERIFIED. No account or role was changed.
- **PASS:** normalization settings HTTP 200; keyword-request notification endpoint HTTP 200 with
  `configured=false`, `enabled=false`; registration-review list HTTP 200 with 0 pending requests.
- **PASS:** unmatched list returned 144; an impossible QA search returned 0. No candidates were
  modified or deleted.
- **UNVERIFIED:** unsaved-draft Cancel/confirm behavior and all other browser-only workflows.

## CSV findings and change

- Current report API response contained 9 catalog fields, while the required CSV schema is 12
  catalog fields plus `검색순위` and `기간내_조회수` = 14 columns. The former serializer copied the
  API object's keys, so it could emit only 11 columns when the three optional catalog fields were
  absent.
- Updated `frontend/src/reportCsv.ts` to serialize the canonical 12 catalog columns every time;
  missing optional values are empty cells. Added a regression test using the actual 9-field API
  shape and adjusted the formula/escaping test for fixed column positions.
- **PASS — generated serializer artifact, not a browser download.** Called the local report API and
  the production `buildTopKeywordCsv` function to create
  `docs/qa/artifacts/local_report_csv_serializer_20261107.csv`. UTF-8 BOM present; two records
  (header + one data row); all rows have 14 cells; Korean header/`안티에이징`, `L001`, period count 1,
  and date `2026-11-07 10:56:32` parsed correctly. Optional author/note/registration-date cells were
  blank. The real React download click and Excel rendering remain UNVERIFIED.
- Code review distinguishes the exports: `keyword_template.csv` is a 9-column header-only template;
  `period_topN_report.csv` is the 14-column report export; `analysis_results.csv` is a separate
  match/span export with 7 columns. The template and analysis-result download events were not
  exercised. No Excel or LibreOffice executable was found.

## Verification and local tooling

- **PASS:** `frontend` `npm test` — 18/18.
- **PASS:** isolated temporary copy from the modified frontend source: `npm ci`, `npm test` 18/18,
  TypeScript `tsc --noEmit`, and Vite production build all passed. This avoided interrupting the live
  Vite server.
- **PASS:** isolated OCR regression suite with a deliberately absent env-file path, CSV backend,
  live reset disabled, and Supabase credentials removed — 8 tests passed.
- **PASS:** `git diff --check` before documentation updates.
- **BLOCKED:** `npm ci` in the live frontend folder failed with Windows `EPERM` unlinking the
  Rolldown native binary held by its running Vite process. The clean temporary build copy passed.
  Restarting this PC's frontend may require stopping that process and rerunning `npm ci`.
- The temporary clean build copy remains under Windows `%TEMP%` because its cleanup command was
  rejected; it excluded `.env*` files and `node_modules` from the source copy and is outside the repo.

## Remaining work and next start

- Get/attach the original handoff text and compare it with the preserved transcription.
- Browser-verify the report download, keyword template download, analysis-results download, unsaved
  draft Cancel and confirm, OCR UI, and member/admin UI. Use the active local test stack only.
- Excel display is unavailable on this PC; use an Excel-installed PC for the 14-column visual check.
- A member role exists but no approved member credentials/session were available; do not reset a
  password or change roles to force this check.
- Law search waits for an approved Law.go.kr test OC key stored only in local API configuration.
- Candidate request/review, inquiry conversation, and same-fixture React/Streamlit UI parity remain
  UNVERIFIED. Preserve L001 and the local report analysis; do not clean them up by deletion.
- Current tracked changes are in `frontend/src/reportCsv.ts`,
  `frontend/tests/report-csv.test.mjs`, this log, `frontend/QA_STATUS.md`, and
  `docs/qa/WORK_HANDOFF.md`. The CSV artifact and reconstructed handoff are new files.
- No commit or push was performed. Another PC cannot receive these changes until they are reviewed,
  committed, and pushed under the repository workflow.

## Later scope steering and regression follow-up (2026-11-07, 11:06 KST)

- User instruction: defer the regulation-evidence search chatbot to a separate future task. Do not
  continue API-key/service testing during the remaining QA unless a code error or integration issue
  affecting another area is observed. The earlier missing-key finding is historical and is no
  longer an active blocker for this QA run.
- With external Supabase settings removed and live reset disabled, four focused Python suites
  passed 41/41: current analysis 4, empty catalog/report/normalization 9, keyword inquiry contracts
  20, and unmatched persistence/registration permissions 8. The expected mocked storage retry log
  was emitted; no live DB was used.
- Streamlit AppTests passed 19/19: approved matching 6 and shared unmatched UI 13. These use
  mocked repository calls and do not verify the current live DB or React browser screens. Expected
  Streamlit deprecation/script-context warnings and a mocked offline-save error log appeared; all
  tests passed.
- No new DB rows, accounts, roles, or settings were changed during these regression tests. Live
  member authentication, UI interactions, inquiry conversation, candidate review, and React/
  Streamlit same-data browser comparison remain unverified.

## Frontend tooling and browser access follow-up (2026-11-07, 11:12 KST)

- PC: `DESKTOP-SINFIM6`; branch `main`; HEAD `7f31159177a10b8f73ffb6db084c86d8c7cf8310`;
  worktree has the code/docs/artifact changes listed above and is uncommitted. No reset, checkout,
  stash, commit, or push was performed.
- Environment: local React `http://127.0.0.1:5173/` and API `http://127.0.0.1:8000/healthz`
  each returned HTTP 200 via `curl.exe`; listeners were PIDs 17520 and 18764. No database write or
  authentication action occurred in this follow-up.
- `npm test` in the current frontend directory passed 18/18. TypeScript could not run because
  `frontend/node_modules` lacks `typescript` and `rolldown`; `npx` offered unrelated `tsc@2.0.4`,
  which was not installed into the repository. This is consistent with the previous `npm ci`
  failing with EPERM while Vite held the Rolldown native binary.
- Copied frontend source to
  `%TEMP%/kra-frontend-verify-01b447fb588c4369a69a992e37d31e89`, excluding `.env*`, `node_modules`,
  and `dist`. There `npm ci` installed 41 packages (0 audit vulnerabilities), tests passed 18/18,
  TypeScript `--noEmit` passed, and `npm run build` passed. The copy remains outside the repo.
- Recovery: after stopping Vite with Ctrl+C in its owning terminal, run
  `Set-Location frontend; npm ci; npm run build`, then restart using
  `scripts/start_local_test_frontend.ps1`. Do not run `npm ci` against the active frontend folder
  while Vite is running. Until then, use a clean isolated copy for install/build checks.
- Browser recovery attempt: opening a fresh in-app tab at the local React URL failed because the
  browser access host returned `unavailable`. No click, login, download, or write occurred. Browser
  QA remains UNVERIFIED / BLOCKED by tooling, not an app error.
- Law-search chatbot remains DEFERRED per user instruction and is excluded from active QA.

## In-place dependency repair after user retry (2026-11-07, 11:17 KST)

- PC/environment: `DESKTOP-SINFIM6`, local-only frontend/API configuration; branch `main` at
  `7f31159177a10b8f73ffb6db084c86d8c7cf8310`. Worktree changes remain uncommitted/unpushed.
- User's npm log at `2026-11-07T02_15_50_379Z` recorded `EPERM unlink` for the Rolldown native
  binary. Process inspection confirmed Vite PID 17520 was still listening on loopback port 5173;
  `npm ci` had therefore not completed, leaving `typescript` invalid/missing and causing the
  subsequent `tsc is not recognized` build error. No tracked package files were changed.
- To repair the active test checkout, stopped only the identified Vite PID 17520, confirmed port
  5173 was released, then ran `npm ci`: 41 packages installed, 0 audit vulnerabilities.
- Verification after install: `npm run build` passed (`tsc --noEmit` and Vite production build);
  `npm test` passed 18/18; `npm ls typescript vite --depth=0` reported TypeScript 7.0.2 and Vite
  8.3.5.
- Restarted the local test frontend using `scripts/start_local_test_frontend.ps1` in an active
  tool session. Frontend `http://127.0.0.1:5173/` and API `http://127.0.0.1:8000/healthz` both
  returned HTTP 200. Current listeners are Vite PID 9280 and API PID 18764. No DB/auth action was
  made during repair.
- Status: dependency repair PASS; production build PASS; frontend tests PASS; local frontend/API
  smoke PASS. Browser host remains a separate UI verification blocker as recorded above.

## Local admin read-only QA and full Python regression (2026-11-07, 11:23 KST)

- PC: `DESKTOP-SINFIM6`; branch `main`; HEAD `7f31159177a10b8f73ffb6db084c86d8c7cf8310`; the
  source and QA changes remain uncommitted/unpushed. No reset, checkout, or stash was performed.
- Environment verification before authenticated reads: Supabase CLI `status` API URL matched both
  `.env.test.local` and `frontend/.env.test.local`; all resolved to HTTP loopback `127.0.0.1:54321`.
  Backend reported `STORAGE_BACKEND=supabase`, local HTTP allow flag set, and empty API integration
  token. Docker showed the repository-named local Supabase containers. No secret or key was printed.
- Used the machine-local generated admin credential only against local Supabase Auth. Login and API
  `/readyz` returned 200. Read-only endpoints: `/api/v1/admin/users` 200 (3 users; roles 2 admin,
  1 member), `/api/v1/keyword-requests` 200 (0 threads),
  `/api/v1/admin/unmatched-registration-requests` 200 (0 pending),
  `/api/v1/admin/normalization-settings` 200, and
  `/api/v1/admin/keyword-request-notifications` 200 (`configured=false`, `enabled=false`).
  `/api/v1/unmatched-terms/recommendation-draft` returned 200 with `payload=null` for this admin.
- All checks were reads; there were no DB writes, account or role changes, or deletions. The local
  `L001` OCR QA catalog record, its one report analysis, and 144 unmatched rows remain retained.
- Full Python/Streamlit suite command: `python -m unittest discover -s tests -p "test_*.py" -v`.
  For isolation, `KRA_ENV_FILE` referenced a deliberately absent path, `STORAGE_BACKEND=csv`,
  `KRA_TEST_LIVE_RESET=0`, and Supabase URL/key variables were removed from the test process.
  Result: 121 tests passed, 9 skipped. Skips were the explicitly opt-in live-reset test and legacy
  Streamlit screen assertions; expected Streamlit context/deprecation warnings and mocked offline
  persistence logging appeared. No DB calls were made by this test process.
- Status: local environment attribution PASS; admin read-only endpoints PASS; full regression PASS.
  Live member inquiry, registration submission/review, and draft save/reload remain UNVERIFIED:
  queues are empty, there is no confirmed member login, and the browser automation host is
  unavailable. Do not change a role or create accounts to force these tests. The regulation-search
  chatbot remains deferred by user instruction.

## User handoff revalidation and CSV/OCR follow-up (2026-11-07, 11:50 KST)

### Run identity and environment

- PC: `DESKTOP-SINFIM6`; repository root observed: `C:/encore/keyword-risk-analyzer`; remote:
  `https://github.com/rlawlsgura-stack/keyword-risk-analyzer.git`; branch `main`; HEAD and
  `origin/main` both `7f31159177a10b8f73ffb6db084c86d8c7cf8310`. Worktree has pre-existing code,
  test, log, and artifact changes; it remains uncommitted. No reset, checkout, stash, commit, or
  push was performed.
- Frontend process PID 9280 is served in test mode on `127.0.0.1:5173`. The Vite process
  environment and transformed `src/api.ts` identify Auth at `127.0.0.1:54321` and API base at
  `127.0.0.1:8000`.
- Backend process PID 18764 has `STORAGE_BACKEND=supabase`; its live process environment uses
  `KRA_ENV_FILE=.env.test.local` and `SUPABASE_URL` host `127.0.0.1`, port `54321`. The local
  Supabase CLI API URL matched that file and the frontend auth URL. `API_ACCESS_TOKEN` was empty.
  Secrets and credential contents were not printed or recorded. Local-only target confirmed before
  authenticated reads or OCR; no production host was contacted.
- React `/` and API `/healthz` returned HTTP 200; health body was `{"status":"ok"}` and authenticated
  `/readyz` returned `{"status":"ready"}`.

### Revalidation of supplied UI observations

- PASS (local API recheck): 3 accounts, 2 admin and 1 member; inquiry list 0; registration-review
  queue 0; normalization API returned ignored symbols `/`, `&`, `,`, `*` and 55 default suffixes;
  current local-admin draft was `payload=null`.
- PASS (local API recheck): catalog revision 15, exactly one row `L001` / `안티에이징`, category
  `LOCAL QA OCR 20261107`, risk `4등급(사용가능)`. The matching report query for
  `start_date=end_date=2026-11-07`, `limit=10` returned one row: L001, hit count 1, last search
  `2026-11-07 10:56:32`. The current report table's 11-column layout and keyboard-entered date
  correction remain USER-REPORTED; no current browser view was captured. No date-entry bug is
  inferred.
- PASS (local API recheck): unmatched total 144; page 1 has 100 rows and offset 100 has 44 rows;
  the unique search `KRA_BROWSER_QA_NO_MATCH_20261107` returns 0. Removing that search restored
  page 1 and L001 exists in the catalog API; the actual click/visual restoration remains USER-
  REPORTED. API sort reads returned 100 rows each and were monotonic by `total_occurrences` and
  `first_seen` for occurrence/registered order respectively. This does not independently verify
  the browser control or its visual sort indicator.
- The six-item browser QA completion count remains 2/6, as supplied by the user. API evidence above
  is not counted as a new browser PASS.

### CSV artifact search and parsing

- Searched only `%USERPROFILE%/Downloads`, the repository, and `docs/qa/artifacts` for recent CSV
  names matching `keyword_template*`, `period_topN_report*`, and `analysis_results*`.
- Found three Downloads report candidates: `C:/Users/Playdata/Downloads/period_topN_report.csv`,
  `period_topN_report (1).csv`, and `period_topN_report (2).csv`. Each is 423 bytes, modified
  2026-11-06 between 16:02 and 16:04 KST, UTF-8 with BOM, 2 rows total, 11 columns per row, one
  data row dated 2026-11-06, and no L001. They are not the requested 2026-11-07 report and fail the
  14-column expectation.
- Repository-root `C:/encore/keyword-risk-analyzer/period_topN_report.csv` is 2,513 bytes, modified
  2026-11-07 10:06 KST, UTF-8 with BOM, 11 rows total and 14 columns per row. It contains no L001;
  its last-search dates are 2026-11-04 and 2026-11-05. It is not the requested day/Top 10 report.
- No matching template CSV or analysis-results CSV was found in those locations. The existing
  `docs/qa/artifacts/local_report_csv_serializer_20261107.csv` is a generated serializer artifact,
  not a browser download, and was not substituted for one. The user-reported Save As action is not
  treated as a failed download; its final path/name remains unknown. A fresh download could not be
  triggered because browser automation stopped on URL-trust enforcement. Save dialog was neither
  opened nor completed/cancelled in this run.
- Excel and LibreOffice commands are unavailable. Excel visual rendering is UNVERIFIED.
- Result: actual browser template (9 columns), requested report (14 columns with L001/date/count),
  and analysis-results (7 columns) remain BLOCKED/UNVERIFIED; the older candidates above are
  explicitly not PASS evidence.

### Exact OCR fixture extraction only

- PASS (API extraction only): opened and visually inspected `docs/qa/ocr_korean_sample.png`; the
  12,189-byte file has a valid PNG signature and visibly contains `안티에이징`. Authenticated
  `POST /api/v1/ocr/extract` used this exact file and returned HTTP 200, one line, one candidate,
  exact expected term, confidence `0.9998558163642883`, and no file error.
- The OCR save endpoint was not called. Catalog revision stayed 15; L001 was not duplicated.
  Browser file selection/OCR UI remains BLOCKED: Chrome access was present in the Windows app
  inventory, but Computer Use stopped before interaction because it could not establish the
  current browser URL with sufficient confidence. No screenshot or UI input was made.

### Remaining browser-only workflows and data changes

- BLOCKED: draft Cancel/preserve and confirm/restore. Local generated-admin API precondition read
  was `payload=null`; the browser account/session could not be matched or controlled. No draft was
  written, and no QA draft row was created.
- BLOCKED: member inquiries and registration request/review. A member role exists but there is no
  confirmed member session/credential in this handoff; inbox and review queue are empty. No account,
  password, or role was changed.
- No new analysis was run because it can alter keyword counts/candidate aggregates and the browser
  result/export control was inaccessible. No database writes, candidate saves, deletions, or file
  creations occurred. Existing L001, its one prior report analysis, and 144 unmatched candidates
  were preserved; no cleanup was performed.
- Browser host reported unavailable and native Chrome URL trust check stopped Computer Use. This
  is a tooling block, not an application defect. Law-search chatbot remains excluded per user scope.
- Changed by this follow-up: QA documentation only (`frontend/QA_STATUS.md`, this dated log,
  `docs/qa/WORK_HANDOFF.md`, `docs/qa/SCREEN_QA_CHECKLIST.md`). No application code changed.
  `git diff --check` passed. No tests were rerun in this pass; the latest full Python suite remains
  121 passed / 9 skipped and frontend suite/build remain 18/18 plus successful build from the prior
  documented run.
- Next PC start point: check out/copy the current uncommitted changes on `main` at
  `7f31159177a10b8f73ffb6db084c86d8c7cf8310`, verify the target machine's local Supabase and
  browser session, then read this section and the earlier logs. Browser work remaining: actual
  template/report/analysis downloads, Excel if available, fixture OCR UI, draft Cancel/confirm,
  member workflows if a legitimate session is available, and visual React/Streamlit parity. No
  commit or push was performed.

## Browser retry and HTML overview handoff (2026-11-07, 11:59 KST)

- Rechecked Windows browser inventory. Chrome still showed the React Preview window, but browser
  enumeration returned no browser sessions and reported the browser access host unavailable.
  Binding native Chrome stopped before interaction because current URL confidence could not be
  established. No page controls, downloads, screenshots, or authentication were attempted.
- Created `docs/qa/react_migration_status_20261107.html` to preserve the previous transition
  summary as a standalone Korean HTML file. Standard-library HTML parsing passed; Korean language
  and title markers, required sections, and four relative QA links were verified.
- No data, code, accounts, roles, or settings changed. No database request was made in this retry.
  This adds no browser PASS to the existing 2/6 bundle. The HTML file and this documentation update
  are uncommitted/unpushed.
