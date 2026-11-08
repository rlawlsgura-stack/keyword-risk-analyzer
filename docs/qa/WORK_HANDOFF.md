# React migration QA handoff

Updated: 2026-11-07

Use this short status note when moving the work between PCs. It is a continuation aid, not a
full activity transcript. Record dated verification details and evidence in
[`legacy_react_QA_STATUS.md`](./legacy_react_QA_STATUS.md) (moved from `frontend/QA_STATUS.md`;
the React screens were rebuilt from FIXED329 on 2026-11-07, see `frontend/README.md`); use the
[`screen QA checklist`](./SCREEN_QA_CHECKLIST.md) for the page-by-page scope.

## Current state

- React release candidate is `0.1.5` in this working change; after the push, use `git pull --ff-only` on the receiving PC. Current package/build validation is recorded below.
- Local QA on 2026-11-07 used React `127.0.0.1:5173`, API `127.0.0.1:8000`, and local Supabase `127.0.0.1:54321`. API-level analysis, OCR, and one intended candidate save completed locally. Synthetic rows `LOCAL001`, `LOCAL002`, and `LOCAL003` are present; retain them and do not delete data.
- React serializer Korean labels were repaired; frontend tests passed 17/17 and the production build passed. The local seed describes 12 report columns.
- Still open: fresh React report-screen CSV download and Excel review; browser-based React member/admin workflow QA; React-Streamlit screen comparison. The UI automation host was unavailable, so API/test results do not count as browser QA.
- Cross-PC startup: update with `git pull --ff-only`, inspect `git status --short --branch`, read this file and the newest dated entry in `frontend/QA_STATUS.md`, then independently verify the receiving PC's active frontend/API/Supabase targets. Do not copy `.env`, credentials, local DB state, or test users between PCs. Record each PC's evidence under its own `LOCAL`/`TEST`/`PRODUCTION` label. Never delete the dataset or local QA rows as cleanup.

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
2. Browser-verify the React text-analysis and OCR upload/result/error-recovery flows on the receiving PC against its confirmed isolated test stack. API-level analysis/OCR and the intended candidate save are already recorded for this PC; they do not prove React interaction behavior.
3. Continue the checklist's remaining member/admin UI checks in a confirmed isolated test environment:
   OCR upload/results and error recovery; keyword inquiries; user and keyword management; unmatched
   candidate search/sort; registration request review; normalization settings.
4. Compare the remaining React and Streamlit screen interactions using the same isolated catalog
   and record each observed case. Existing parity evidence covers seven examples only.
5. Before any live QA action on another PC, verify and record that PC's active environment. Use only its isolated test Supabase for QA writes. Do not delete records or change unrelated catalog, user, role, Supabase, or Render settings. Keep all previous production QA evidence separate from local/test results.

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

## Current verified start point (2026-11-07, DESKTOP-SINFIM6)

- Repository was `main` at `7f31159177a10b8f73ffb6db084c86d8c7cf8310`, aligned with `origin/main`
  before this run. The current code/docs/artifact changes are uncommitted and unpushed.
- The active Vite runtime points to local Supabase Auth `127.0.0.1:54321` and API
  `127.0.0.1:8000`. CLI project status and local Docker containers matched; API `/readyz` passed.
  This is the confirmed isolated LOCAL QA DB for writes on this PC.
- Important correction for this active DB: it began this run empty at revision 14, despite the
  earlier note that three `LOCAL%` rows existed. It now has one retained OCR QA keyword `L001` at
  revision 15 and one recorded test analysis for report output. The 144 accumulated unmatched terms
  were preserved. Do not delete either test record or the unmatched data.
- OCR extraction/save/re-query and API matching/filter/empty-result cases passed. See the latest
  `frontend/QA_STATUS.md` section and `docs/qa/qa_run_20261107_DESKTOP-SINFIM6.md` for exact inputs.
- Report API returned 9 keyword fields. The frontend serializer now fixes the report CSV to 14
  columns. A parsed serializer artifact is at
  `docs/qa/artifacts/local_report_csv_serializer_20261107.csv`; this does not prove a browser
  download or Excel rendering.
- The browser observation supplied by the user is preserved as USER-REPORTED in
  `docs/qa/KRA_QA_HANDOFF_20261107.txt`. The original attachment was not available in this checkout.
- Next: use an accessible browser to verify actual template/report/analysis CSV downloads, unsaved
  draft Cancel/confirm, OCR UI, member/admin screens, candidate/inquiry flows, and same-data
  React/Streamlit interactions. Excel display requires an Excel-installed PC. Per the user's
  2026-11-07 instruction, defer the law-search chatbot; do not test it unless a code or integration
  error is found. A member account exists, but no confirmed member credential/session was used.
- The live frontend's local `node_modules` was partially affected by a failed `npm ci` (`EPERM` on
  the in-use Rolldown binary). A separate clean temporary copy passed install, tests, typecheck, and
  build. Once the current Vite process can be stopped, rerun `npm ci` before starting that frontend
  from this PC. Other clones can use the normal pinned setup workflow.
- Tooling follow-up on 2026-11-07: the first in-place `npm ci` retries failed because Vite PID
  17520 still held the Rolldown binary. After stopping that verified process, in-place `npm ci`
  installed 41 packages (0 audit findings); tests 18/18, TypeScript check, and production build
  passed. The local test frontend was restarted and React/API returned HTTP 200. A fresh in-app
  browser tab failed because the browser access host returned `unavailable`; visual QA remains
  unverified. See the latest dated QA run entry for process IDs and evidence.
- The law-search chatbot is deferred to its own future implementation per the user's instruction;
  it is not an active QA blocker.
- Latest local-only continuation: frontend/API/Supabase are listening on loopback ports 5173, 8000,
  and 54321. Admin read-only API checks passed; this account has no saved recommendation draft,
  no inquiry threads, and the review queue is empty. Full Python/Streamlit regression passed
  121 tests with 9 skips under a sanitized CSV backend. Member-authenticated live flows and browser
  interactions remain unverified; see the latest dated QA run section.
- Latest handoff revalidation (2026-11-07): live API target reconfirmed local; revision 15, L001,
  144 candidates, one report hit on 2026-11-07, exact OCR fixture extraction passed by API with no
  save. Existing CSV search found only older/wrong-condition report files; no template/analysis
  browser CSV. Fresh download, draft UI, member flows are blocked by browser URL-trust failure.
  No DB changes were made. Continue from the newest section in `qa_run_20261107_DESKTOP-SINFIM6.md`.
- A concise HTML overview of migration progress, remaining QA, blockers, and exclusions is available
  at [`react_migration_status_20261107.html`](./react_migration_status_20261107.html). It is a new
  untracked artifact until committed/pushed with the other work.

## Browser recheck and HTML overview (2026-11-07, 11:59 KST)

- Retried browser discovery. Chrome still had the React Preview window, but the browser host
  reported unavailable; native Chrome control again stopped before interaction because URL trust
  could not be established. No clicks, downloads, login, screenshots, or DB actions occurred.
- Created `docs/qa/react_migration_status_20261107.html`, a standalone Korean summary with current
  conversion status, outstanding tasks, browser/member/Excel blockers, excluded law chatbot, and
  links to QA records. UTF-8 HTML parsing and all four local QA links were checked successfully.
- No source, DB, account, or role changes occurred. Existing QA files/data remain untouched.
  Browser UI tasks remain unverified; no commit or push was performed.

## Scope steering and regression follow-up (2026-11-07)

- The user deferred the regulation-evidence search chatbot to a separate future task. Exclude it
  from the remaining QA checklist; only investigate it if a code error or integration problem
  affecting another area is encountered. Earlier key/config notes remain historical and are not
  active blockers for this QA run.
- Focused Python analysis/catalog/inquiry/unmatched tests passed 41/41 with external Supabase
  settings removed and live reset disabled. Streamlit AppTests passed 19/19 with mocked repository
  calls. These do not replace live member auth, React UI, or cross-app browser comparison.

## React report UI follow-up (2026-11-07)

React/API were stopped when the report page showed `Failed to fetch`; local Supabase remained up.
Both services were restarted using the test-only launch scripts and stayed on loopback
(`127.0.0.1:5173`, `127.0.0.1:8000`) with Supabase at `127.0.0.1:54321`.

Using the existing local admin session and preserved L001 fixture, the React report showed 2 hits
for 2026-11-07 and no row for 2026-11-06. The date summary followed the visible native date inputs;
the default 2026-11-01–2026-11-07 range was restored. No report reset or DB write was made. Clicking
the report CSV control did not produce a new file in Downloads, so a fresh browser download and
Excel rendering remain open. Frontend tests passed 18/18 and build passed after sandbox
`spawn EPERM` required approved local execution; `git diff --check` passed. Existing working-copy
changes and QA rows were preserved.

## React OCR upload control follow-up (2026-11-07)

The authenticated React OCR page rendered, but the connected in-app browser could not open a file
chooser from the visible image-selection button. No file was selected and no OCR request was sent.
This is a browser file-selection limitation, not evidence of an OCR failure. No OCR candidate,
analysis record, keyword row, or other database data changed. The OCR upload/result/recovery screen
check remains open; use a browser session that can open the native file chooser to continue.

## Analysis retry source review and progress estimate (2026-11-07)

No completed flow was retested. Source review found that React clears stale results after input/option changes and retains/reuses the pending request ID for a retry when the request payload is unchanged. Unmatched-candidate collection has a separate retry action; the service reuses prior analysis by ID/fingerprint. Existing tests cover candidate-collection retry without duplicate history writes, but were not rerun in this continuation.

The checklist has 14 active workflow groups: 13 have partial or sample-only evidence and 1 remains without browser evidence; none is fully closed across all criteria. A rough evidence-completion estimate using 0.5 credit for each partial/sample-only group and 0 for the open group is 6.5/14, or 46%. This is not a code migration completion percentage. Browser failure/recovery and focus/scroll behavior remain open.
