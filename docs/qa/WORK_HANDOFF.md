# React migration QA handoff

Updated: 2026-11-06

Use this short status note when moving the work between PCs. It is a continuation aid, not a
full activity transcript. Record dated verification details and evidence in
[`frontend/QA_STATUS.md`](../../frontend/QA_STATUS.md); use the
[`screen QA checklist`](./SCREEN_QA_CHECKLIST.md) for the page-by-page scope.

## Current state

- Branch: `main`. The previously synced baseline was `fdab4b1`; this session adds OCR regression
  results and QA notes. Before switching PCs, pull the latest `main` and check its status.
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
- Excel and LibreOffice were not found in the latest environment inspection. CSV parsing passed,
  and report date-range client/API behavior now has mock-backed tests; actual spreadsheet rendering
  and the 14-column layout remain unverified.

## Next work, in order

1. The user will verify CSV rendering in an Excel-equipped environment, including all 14 report
   columns, Korean text, dates, and counts. Keep this open until that visual result is reported.
2. Verify the React OCR screen in a signed-in local test session: Korean sample, blank image,
   per-file errors/retry, candidate selection/required fields, analysis handoff, and persistence only
   after confirming the API points at an isolated database. The OCR regression suite passed 8/8 and
   the save-payload contract passed, but neither proves React screen behavior or model inference.
3. Continue the checklist's remaining member/admin UI checks in a confirmed local test environment:
   OCR upload/results and error recovery; keyword inquiries; user and keyword management; unmatched
   candidate search/sort; registration request review; normalization settings.
4. Compare the remaining React and Streamlit screen interactions using the same isolated catalog
   and record each observed case. Existing parity evidence covers seven examples only.
5. Keep operational writes isolated. Do not test by changing production Supabase/Render data or
   settings. Before any local DB mutation, identify the local Supabase URL and test rows; remove only
   QA data created in that test.

The 2026-11-06 report date-range follow-up added isolated tests: backend 9/9 and frontend 15/15.
These checks cover API parameter and response behavior only; no live database, report screen, or
spreadsheet application was used.

The 2026-11-06 OCR follow-up passed the 8-test Python OCR suite and the React OCR save-payload
contract check. The suite uses mocked OCR for extraction/Streamlit tests and headless Chrome for
overlay geometry; the React OCR UI and live model inference were not exercised.

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

## Working-copy caution at this update

The user-data and patch files already present as untracked at the start of this update were left
untouched: `keyword_filtered.csv`, `unmatched_candidates.csv`, `ocr_ui_qa_fixes.patch`,
`react_parity_fixes.patch`, `react_unmatched_parity_followup.patch`, and `supabase/.temp/`.
Inspect each independently before deciding whether it belongs in version control; never add the
temporary Supabase directory or secret material.
