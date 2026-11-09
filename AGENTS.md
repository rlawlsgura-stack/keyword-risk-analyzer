# Project workflow

The user granted standing authorization on 2026-10-27 to commit and push changes
made for their requested work in this repository without asking for approval
again for each commit.

- Repository: `https://github.com/rlawlsgura-stack/keyword-risk-analyzer.git`
- Branch: `main`
- Review the intended changes and run appropriate checks before committing.
- Before starting or reopening local frontend/API ports, verify the configured
  Supabase URL and client key, confirm frontend/backend Supabase URLs match, and
  check Supabase Auth health. Also confirm API CORS allows the frontend origin
  and that the API health endpoint responds. Report these checks before launch.
- Before changing the API port or `VITE_API_BASE_URL`, check the currently
  served frontend API URL, listening API ports, `/healthz`, and CORS preflight
  for the frontend origin. Confirm the intended frontend/backend port pairing
  before editing either setting, then report the checks before restarting.
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
