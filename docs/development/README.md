# 개발 Runbook

이 문서는 저장소를 처음 받은 개발자가 필요한 도구와 설정을 확인하고 로컬 React·FastAPI를 실행하는 절차, Codex의 작업 기록 방식을 안내합니다. 운영 Supabase를 사용하는 일반 로컬 실행과 운영 DB에서 분리된 테스트 실행은 서로 다른 흐름입니다.

## 작업 시작과 마무리

1. 작업을 시작할 때 `AGENTS.md`, 이 문서, `WORK_LOG.md`의 최신 항목을 읽습니다.
2. 요청한 작업에 필요한 프로그램, 설정 파일, 환경변수, 계정 권한, 포트와 현재 서비스 상태를 확인합니다. 명령을 실행하기 전에 사용자에게 실행 순서를 안내하고, 특히 서비스 시작·재시작 전에는 `AGENTS.md`의 포트·API·Supabase·CORS 점검 결과를 먼저 보고합니다.
3. 요청된 비파괴 작업과 필요한 명령을 실행합니다. 실패하면 실제 오류를 확인하고, 성공한 것처럼 가정하지 않습니다.
4. 적절한 검증을 마친 뒤 `WORK_LOG.md`에 요청, 변경 파일, 실제 실행한 명령, 결과, 커밋·푸시 상태를 기록합니다. 비밀 값·비밀번호·토큰은 기록하지 않습니다.
5. 설치·실행 안내를 변경했으면 사용 가능한 GitBook `prerequisite-gap-checker` 스킬로 사전 요구사항을 다시 점검하고 결과를 작업 기록에 남깁니다.
6. 변경 diff와 프로젝트 지침을 검토한 후 저장소 리뷰를 거쳐 반영합니다. GitBook MCP 변경 요청을 별도로 연결한 경우에는 해당 변경 요청의 미리보기를 검토합니다.

스킬이 없는 Codex 환경에서는 저장소 루트에서 다음 명령으로 GitBook Toolkit의 이 스킬을 설치합니다.

```powershell
npx skills@latest add GitbookIO/docs-skills --skill prerequisite-gap-checker -y
```

## 도구와 계정

일반 React·FastAPI 실행에 필요한 도구:

- Windows PowerShell
- [Python for Windows](https://www.python.org/downloads/windows/) 3.14 및 Python Launcher `py`
- [Node.js for Windows](https://nodejs.org/en/download/) 22.13 이상과 함께 설치되는 npm
- [Git for Windows](https://git-scm.com/download/win)
- 기존 Supabase 프로젝트에 접근할 계정. 서버 secret 키와 브라우저용 publishable 키를 각각 확인할 권한이 필요합니다.

OCR 화면 또는 격리 로컬 테스트 API를 실행하려면 Python 3.13을 별도로 설치하고 `.venv-ocr313` 환경에 OCR 패키지를 설치해야 합니다. 격리 로컬 Supabase를 쓰려면 [Docker Desktop for Windows](https://docs.docker.com/desktop/setup/install/windows-install/)도 설치해야 합니다. 자세한 Python 명령은 [저장소 README](../../README.md) 상단의 “Local OCR” 부분을 참고하세요.

설치 확인:

```powershell
py -3.14 --version
node --version
npm --version
git --version
```

## 일반 로컬 실행: 기존 Supabase에 연결

이 흐름은 로컬 앱을 README에 구성된 Supabase 프로젝트에 연결합니다. 운영 데이터를 바꾸지 않는 검증에는 [격리 테스트 환경](../../frontend/README.md)을 선택하세요.

프로젝트 루트에서 Python 환경과 무시되는 환경 파일을 준비합니다. `.env`나 `frontend/.env.local`이 이미 있으면 복사로 덮어쓰지 않습니다.

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
if (!(Test-Path .env)) { Copy-Item .env.example .env }
if (!(Test-Path frontend/.env.local)) { Copy-Item frontend/.env.example frontend/.env.local }
cd frontend
npm ci
cd ..
```

`.env`에는 `STORAGE_BACKEND=supabase`, `SUPABASE_URL`, `SUPABASE_SECRET_KEY`를 설정합니다. 서버 secret은 Dashboard의 Project Settings → API Keys에서 가져옵니다. `API_ACCESS_TOKEN`은 외부 연동이 공유 토큰을 사용할 때만 필요합니다.

`frontend/.env.local`에는 다음을 설정합니다.

- `VITE_SUPABASE_URL`: `.env`의 `SUPABASE_URL`과 동일한 Supabase URL
- `VITE_SUPABASE_PUBLISHABLE_KEY`: 브라우저용 publishable key. `SUPABASE_SECRET_KEY`나 `service_role` 키는 넣지 않습니다.
- `VITE_API_BASE_URL=http://127.0.0.1:8002`: 아래 FastAPI 포트와 일치해야 합니다.

계정이 없다면 프로젝트 관리자가 Supabase Auth에서 사용자 계정을 만들거나 초대하고 `app_metadata.role`에 `member` 또는 `admin` 역할을 부여해야 합니다. 이를 위해 해당 Supabase 프로젝트의 Authentication 관리 권한이 필요합니다. 새 Supabase 프로젝트를 사용할 때는 SQL Editor 권한이 있는 관리자가 `supabase/schema.sql`을 먼저 적용해야 합니다. 현재 연결 프로젝트의 상태와 역할 관리 방법은 [README의 현재 구축 상태](../../README.md#현재-구축-상태), [계정과 권한](../../README.md#계정과-권한), [DB 업그레이드 안내](../../README.md#shared-unmatched-expression-collection)를 확인하세요.

### 사전 점검과 실행

이 앱의 기본 포트 쌍은 React `127.0.0.1:5173` → API `127.0.0.1:8002`입니다. 프론트엔드를 실행하거나 포트를 바꾸기 전에 실제 listening port, 현재 제공되는 Vite 모듈의 API 주소, API `/healthz`, Supabase Auth health, 프론트엔드 origin에 대한 CORS preflight를 확인합니다. 확인 결과를 먼저 알리고 실행합니다. 처음 API를 띄우는 경우에는 API health가 아직 응답하지 않는 상태도 그대로 보고한 다음 API를 시작하고, 프론트엔드 시작 전에 API health와 CORS를 확인합니다. Vite가 다른 포트로 이동하면 실제 프론트엔드 origin을 `API_CORS_ORIGINS`에 허용하고 API를 다시 시작해야 할 수 있습니다.

API 터미널은 프로젝트 루트에서 실행합니다.

```powershell
.\.venv\Scripts\python.exe -m uvicorn api:app --host 127.0.0.1 --port 8002
```

프론트엔드는 다른 터미널에서 실행합니다.

```powershell
cd D:\back-up\encore\keyword-risk-analyzer\frontend
npm run dev -- --host 127.0.0.1
```

Vite가 다른 포트로 이동할 수 있으므로 실제 주소와 제공 중인 모듈의 API 주소를 다시 확인합니다. 환경변수를 수정했다면 Vite를 중지하고 재시작해야 변경이 반영됩니다.

## 격리 테스트 실행

운영 Supabase와 분리된 로컬 Supabase·API·React 조합은 [프론트엔드 로컬 테스트 절차](../../frontend/README.md)를 따릅니다. 이 절차는 Docker Desktop, Python 3.13 OCR 환경, `npm ci`를 요구합니다. `start_local_test_supabase.ps1`가 `.env.test.local`, `frontend/.env.test.local`, 로컬 전용 관리자 자격 파일을 생성합니다. 이 파일들은 로컬 전용이며 운영 secret이나 데이터를 복사하지 않습니다. UI를 일반회원 역할로도 확인할 때는 테스트 전용 Auth 계정을 만들고 관리자 계정으로 사용자 관리 탭에서 역할을 `member`로 지정합니다.

## 작업 기록 형식

각 작업을 `WORK_LOG.md`에 날짜순으로 추가합니다.

```markdown
## YYYY-MM-DD — 짧은 작업 제목

- 요청:
- 변경 파일:
- 실행한 명령과 결과:
- 검증:
- 커밋/푸시:
- 미해결 항목:
```
