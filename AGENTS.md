# Project workflow

## Work execution and records

- At the start of each task, read this file, `docs/development/README.md`, and
  the latest entry in `docs/development/WORK_LOG.md` when those files exist.
- Follow the runbook to inspect prerequisites and environment state before
  giving commands or starting services. Execute the requested, non-destructive
  steps when the user asks for the work; report blockers instead of guessing.
- At the end of each task, append a concise entry to
  `docs/development/WORK_LOG.md` with the date, request, files changed, commands
  actually run, results, and commit/push status. Never record secret values,
  passwords, access tokens, or full credential-bearing URLs.
- When changing setup or execution instructions, use the GitBook
  `prerequisite-gap-checker` skill if available and include the review result
  in the work log. Review documentation diffs before committing.
- Use repository review (diff review and the project checks below) for changes
  unless a GitBook change-request workflow is explicitly connected and selected.

The user granted standing authorization on 2026-10-27 to commit and push changes
made for their requested work in this repository without asking for approval
again for each commit.

- Repository: `https://github.com/rlawlsgura-stack/keyword-risk-analyzer.git`
- Branch: `main`
- Review the intended changes and run appropriate checks before committing.
- For every UI change, verify the React production entrypoint in `README.md` and
  inspect role-specific branches for both administrator and member accounts.
  Keep common screens and behavior aligned across roles.
- Before starting or reopening local frontend/API ports, verify the configured
  Supabase URL and client key, confirm frontend/backend Supabase URLs match, and
  check Supabase Auth health. Also confirm API CORS allows the frontend origin
  and that the API health endpoint responds. Report these checks before launch.
- Before changing or restarting any local frontend/API port, check the actual
  listening ports, currently served frontend API URL, API `/healthz`, Supabase
  Auth health, and CORS preflight for the frontend origin. Confirm the intended
  frontend/backend port pairing before editing settings or restarting, and
  report the checks first. Vite may move to the next port when its configured
  port is occupied: after launch, verify the actual frontend port and inspect
  the served module's `VITE_API_BASE_URL`; do not infer it from `.env` alone.
- Select the ordinary push command by the PC's repository location. On the
  D-drive PC, use:

  ```powershell
  cd D:\back-up\encore\keyword-risk-analyzer
  git push https://github.com/rlawlsgura-stack/keyword-risk-analyzer.git main:refs/heads/main
  ```

  On the other PC, where the checkout is on C:, use this exact command without
  extra arguments:

  ```powershell
  git -C C:/encore/keyword-risk-analyzer push https://github.com/rlawlsgura-stack/keyword-risk-analyzer.git main:refs/heads/main
  ```

This command has a project-specific user rule in
`C:/Users/USER/.codex/rules/keyword-risk-analyzer-push.rules`.
Force pushes, branch deletion, other destinations, and unrelated changes are
outside this standing authorization. Existing secret-file protections and
managed approval policies still apply.
