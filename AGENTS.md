# Project workflow

The user granted standing authorization on 2026-10-27 to commit and push changes
made for their requested work in this repository without asking for approval
again for each commit.

- Repository: `https://github.com/rlawlsgura-stack/keyword-risk-analyzer.git`
- Branch: `main`
- Review the intended changes and run appropriate checks before committing.
- For an ordinary push, use this exact command without extra arguments:

  ```powershell
  git -C D:/back-up/encore/keyword-risk-analyzer push https://github.com/rlawlsgura-stack/keyword-risk-analyzer.git main:refs/heads/main
  ```

This command has a project-specific user rule in
`C:/Users/USER/.codex/rules/keyword-risk-analyzer-push.rules`.
Force pushes, branch deletion, other destinations, and unrelated changes are
outside this standing authorization. Existing secret-file protections and
managed approval policies still apply.
