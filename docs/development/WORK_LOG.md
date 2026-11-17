# 개발 작업 기록

이 파일은 Codex가 이 저장소에서 수행한 작업과 검증 내역을 날짜순으로 남깁니다. 실행하지 않은 명령은 기록하지 않으며, secret·비밀번호·토큰과 무시되는 환경 파일의 값은 기록하지 않습니다.

## 2026-11-17 — LLM 답변 URL 링크 표시

- 요청: LLM 답변의 인터넷 주소를 하이퍼링크로 표시하고 Ctrl+클릭으로 열 수 있게 함.
- 변경 파일: `frontend/src/tabs/ChatTab.tsx`, `frontend/src/styles.css`.
- 실행한 명령과 결과: `npm run build` 성공. `git diff --check` 성공.
- 검증: TypeScript 검사와 Vite 운영 빌드 통과. 공통 답변 렌더러에 적용되어 관리자·일반회원 화면에서 동일하게 표시됨.
- 커밋/푸시: `ff775bb`를 `main`에 push 완료.
- 미해결 항목: 없음.

## 2026-11-17 — 개발 Runbook과 작업 기록 흐름 정리

- 요청: 앞으로의 작업 절차를 저장소에 남기고, 실제 안내 명령을 실행·검증·기록하는 흐름을 마련함.
- 변경 파일: `AGENTS.md`, `README.md`, `.env.example`, `frontend/.env.example`, `frontend/README.md`, `docs/development/README.md`, `docs/development/WORK_LOG.md`.
- 실행한 명령과 결과: Python 3.14.7, Node.js v24.20.0, npm 11.19.0, Git 2.55.0 버전 확인. 문서 상대 링크 검사와 `git diff --check` 통과.
- 검증: GitBook `prerequisite-gap-checker`로 새 Runbook을 다시 읽고 준비사항을 점검함. 도구 설치 링크, Supabase 키·역할·스키마, 일반/격리 포트 쌍, Docker·방화벽 요구사항, 두 역할의 테스트 계정을 안내함. 기존 README의 없는 설계 ZIP 링크도 제거함. 코드 테스트는 수행하지 않음.
- 커밋/푸시: 변경 검토 후 `main`에 커밋·푸시 완료.
- 미해결 항목: GitBook MCP 계정 연결은 하지 않음. 저장소의 문서 diff 검토를 반영 경로로 사용.
