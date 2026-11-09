# Project workflow

The user granted standing authorization on 2026-10-27 to commit and push changes
made for their requested work in this repository without asking for approval
again for each commit.

- Repository: `https://github.com/rlawlsgura-stack/keyword-risk-analyzer.git`
- Branch: `main`
- Review the intended changes and run appropriate checks before committing.
- For every UI change, verify the active app entrypoint in `README.md` and inspect
  role-specific branches for both administrator and member accounts. Keep common
  screens and behavior aligned across roles. The current production/local
  Streamlit entrypoint selects the highest numbered `keyword_app2_fixed###.py`;
  the React frontend is a separate implementation and must not be assumed to be
  the active app. When a requested shared feature exists in both implementations,
  update both or clearly identify which app is active before concluding.
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
